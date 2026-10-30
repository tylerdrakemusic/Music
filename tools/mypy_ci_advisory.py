"""Run pinned mypy checks and write an advisory report for CI."""

from __future__ import annotations

import argparse
import configparser
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path


MYPY_VERSION = "1.18.2"
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40,64}$")
VERSION_PATTERN = re.compile(r"^mypy ([0-9]+\.[0-9]+\.[0-9]+)(?:\s|$)")
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run_command(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            list(command),
            capture_output=True,
            check=False,
            cwd=cwd,
            encoding="utf-8",
            errors="replace",
            text=True,
        )
    except OSError:
        return None


def _read_scope(config_path: Path) -> list[str]:
    config = configparser.ConfigParser(interpolation=None)
    if not config.read(config_path, encoding="utf-8"):
        raise ValueError("mypy configuration could not be read")
    configured_files = config.get("mypy", "files", fallback="")
    scope = [item.strip().replace("\\", "/") for item in configured_files.split(",") if item.strip()]
    if not scope or any(
        not item.startswith("src/")
        or not item.endswith(".py")
        or ".." in Path(item).parts
        for item in scope
    ):
        raise ValueError("mypy configuration must select Python modules under src")
    if len(scope) != len(set(scope)):
        raise ValueError("mypy configuration contains duplicate modules")
    return scope


def _installation_exit_code() -> int | None:
    value = os.environ.get("MYPY_INSTALL_EXIT_CODE")
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _finding_count(stdout: str, returncode: int | None) -> int | None:
    if returncode not in (0, 1):
        return None
    return sum(": error:" in line for line in stdout.splitlines())


def _build_report(
    config_path: Path,
    scope: list[str],
    repository: str,
    commit: str,
    elapsed_seconds: float,
    installation_exit_code: int | None,
    version_result: subprocess.CompletedProcess[str] | None,
    check_result: subprocess.CompletedProcess[str] | None,
) -> dict[str, object]:
    version_stdout = version_result.stdout.strip() if version_result else ""
    version_match = VERSION_PATTERN.match(version_stdout)
    observed_version = version_match.group(1) if version_match else "unavailable"
    version_ok = bool(
        version_result
        and version_result.returncode == 0
        and observed_version == MYPY_VERSION
    )
    try:
        config_hash: str | None = hashlib.sha256(config_path.read_bytes()).hexdigest()
    except OSError:
        config_hash = None
    safe_repository = repository if REPOSITORY_PATTERN.fullmatch(repository) else "local"
    safe_commit = commit if COMMIT_PATTERN.fullmatch(commit) else "unavailable"
    check_stdout = check_result.stdout if check_result else ""
    check_returncode = check_result.returncode if check_result else None

    return {
        "repository": safe_repository,
        "commit": safe_commit,
        "mypy_version": observed_version,
        "configuration": {"path": config_path.name, "sha256": config_hash},
        "scan_scope": scope,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "finding_count": _finding_count(check_stdout, check_returncode),
        "command_exit_codes": {
            "mypy_install": installation_exit_code,
            "mypy_version": version_result.returncode if version_result else None,
            "mypy_check": check_returncode,
        },
        "tool_errors": {
            "mypy_install": installation_exit_code not in (None, 0),
            "mypy_version": not version_ok,
            "mypy_check": check_returncode not in (0, 1)
            or _finding_count(check_stdout, check_returncode) is None,
        },
    }


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as output_file:
            temporary_path = Path(output_file.name)
            output_file.write(content)
            output_file.flush()
            os.fsync(output_file.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _render_step_summary(report: dict[str, object]) -> str:
    configuration = report["configuration"]
    exit_codes = report["command_exit_codes"]
    tool_errors = report["tool_errors"]
    assert isinstance(configuration, dict)
    assert isinstance(exit_codes, dict)
    assert isinstance(tool_errors, dict)
    config_hash = configuration["sha256"] or "unavailable"
    finding_count = report["finding_count"]
    finding_text = "unavailable" if finding_count is None else str(finding_count)
    elapsed_seconds = report["elapsed_seconds"]
    assert isinstance(elapsed_seconds, (int, float))

    return "\n".join(
        [
            "## Mypy advisory baseline",
            "",
            f"- Repository: `{report['repository']}`",
            f"- Scanned commit: `{report['commit']}`",
            f"- Mypy version: `{report['mypy_version']}`",
            f"- Config: `{configuration['path']}` SHA-256 `{config_hash}`",
            f"- Scope: {', '.join(report['scan_scope'])}",
            f"- Elapsed: {elapsed_seconds:.3f} seconds",
            f"- Findings: `{finding_text}`",
            "- Command exit codes: "
            f"install={exit_codes['mypy_install']}, "
            f"version={exit_codes['mypy_version']}, check={exit_codes['mypy_check']}",
            "- Tool errors: "
            f"install={tool_errors['mypy_install']}, "
            f"version={tool_errors['mypy_version']}, check={tool_errors['mypy_check']}",
            "- Advisory only: mypy findings and tool errors do not gate CI; pytest remains required.",
            "",
        ]
    )


def _append_step_summary(path: Path, content: str) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    _write_atomic(path, existing + content)


def _run_id() -> str:
    github_run_id = os.environ.get("GITHUB_RUN_ID")
    github_run_attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    if github_run_id:
        return f"{github_run_id}-{github_run_attempt}"
    return f"local-{os.getpid()}-{time.time_ns()}"


def main(argv: Sequence[str] | None = None) -> int:
    """Run pinned mypy checks and write the advisory CI report."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-path", default="mypy.ini")
    parser.add_argument("--local-output-dir")
    parser.add_argument("--ci-output-dir")
    parser.add_argument("--step-summary")
    args = parser.parse_args(argv)

    run_id = _run_id()
    local_output_dir = Path(
        args.local_output_dir
        or os.environ.get("MYPY_ADVISORY_LOCAL_DIR")
        or PROJECT_ROOT / "tmp" / "mypy-advisory-local" / run_id
    )
    ci_output_dir = Path(
        args.ci_output_dir
        or os.environ.get("MYPY_ADVISORY_CI_DIR")
        or PROJECT_ROOT / "tmp" / "mypy-advisory-ci" / run_id
    )
    config_path = Path(args.config_path)
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    summary_path_value = args.step_summary or os.environ.get("GITHUB_STEP_SUMMARY")

    try:
        scope = _read_scope(config_path)
        mypy_command = [sys.executable, "-m", "mypy"]
        started = time.perf_counter()
        version_result = _run_command(mypy_command + ["--version"], PROJECT_ROOT)
        check_result = _run_command(
            mypy_command
            + ["--config-file", str(config_path), "--no-error-summary", "--show-error-codes"]
            + scope,
            PROJECT_ROOT,
        )
        elapsed_seconds = time.perf_counter() - started
        git_result = _run_command(["git", "rev-parse", "HEAD"], PROJECT_ROOT)
        commit = git_result.stdout.strip() if git_result and git_result.returncode == 0 else "unavailable"
        report = _build_report(
            config_path=config_path,
            scope=scope,
            repository=os.environ.get("GITHUB_REPOSITORY", "local"),
            commit=commit,
            elapsed_seconds=elapsed_seconds,
            installation_exit_code=_installation_exit_code(),
            version_result=version_result,
            check_result=check_result,
        )
        for filename, result in {
            "mypy-version.stdout.txt": version_result,
            "mypy-check.stdout.txt": check_result,
        }.items():
            _write_atomic(local_output_dir / filename, result.stdout if result else "")
        for filename, result in {
            "mypy-version.stderr.txt": version_result,
            "mypy-check.stderr.txt": check_result,
        }.items():
            _write_atomic(local_output_dir / filename, result.stderr if result else "")
        _write_atomic(
            local_output_dir / "summary.json",
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        )
        _write_atomic(
            ci_output_dir / "summary.json",
            json.dumps(report, indent=2, sort_keys=True) + "\n",
        )
        step_summary = _render_step_summary(report)
        if summary_path_value:
            _append_step_summary(Path(summary_path_value), step_summary)
        print(step_summary, end="")
    except (OSError, ValueError, configparser.Error):
        print("Mypy advisory report generation failed; CI remains advisory.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())