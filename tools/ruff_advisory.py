"""Run pinned Ruff checks and write advisory CI evidence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

RUFF_VERSION = "0.17.2"
SCAN_SCOPE = (
    "All non-ignored Python files under the Music repository root, using ruff.toml. "
    "The config excludes .worktrees, tmp, and output; Git-ignored paths and all "
    "non-Python files, including audio/catalog data, are not scanned."
)
CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def _run_command(
    command: list[str],
    repo_root: Path,
    command_runner: CommandRunner,
) -> dict[str, Any]:
    try:
        result = command_runner(
            command,
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        return {"returncode": None, "stdout": "", "stderr": str(error)}
    return {
        "returncode": result.returncode,
        "stdout": result.stdout or "",
        "stderr": result.stderr or "",
    }


def _format_count(result: dict[str, Any]) -> int | None:
    output = f"{result['stdout']}\n{result['stderr']}"
    match = re.search(r"(?m)^(\d+) files? would be reformatted\b", output)
    if match:
        return int(match.group(1))
    if result["returncode"] == 0:
        return 0
    return None


def _write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _safe_ci_summary(report: dict[str, Any]) -> dict[str, Any]:
    errors = report["command_errors"]
    error_categories = {
        "ruff_install": "ruff_install_failed",
        "ruff_version": "ruff_version_unavailable",
        "ruff_check": "ruff_check_failed",
        "ruff_format_check": "ruff_format_check_failed",
        "git_rev_parse": "commit_unavailable",
        "config": "config_unavailable",
    }
    error_flags = {name: bool(errors.get(name)) for name in error_categories}
    config_hash = report["config"]["sha256"]
    repository = report["repository"]
    commit = report["commit"]
    version = report["ruff_version"]
    return {
        "repo": (
            repository
            if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
            else "unavailable"
        ),
        "commit": commit if re.fullmatch(r"[0-9a-fA-F]{6,64}", commit) else "unavailable",
        "ruff_version": version if version == f"ruff {RUFF_VERSION}" else "unavailable",
        "config_hash": config_hash,
        "config_revision": "unavailable"
        if config_hash == "unavailable"
        else f"sha256:{config_hash}",
        "scope": SCAN_SCOPE,
        "elapsed_seconds": report["elapsed_seconds"],
        "finding_counts": report["finding_counts"],
        "exit_codes": report["command_exit_codes"],
        "errors": error_flags,
        "error_categories": [
            category for name, category in error_categories.items() if error_flags[name]
        ],
    }


def _summary_markdown(summary: dict[str, Any]) -> str:
    counts = summary["finding_counts"]
    codes = summary["exit_codes"]
    check_count = "unavailable" if counts["ruff_check"] is None else counts["ruff_check"]
    format_count = "unavailable" if counts["ruff_format"] is None else counts["ruff_format"]
    error_categories = ", ".join(summary["error_categories"]) or "none"
    return "\n".join(
        [
            "## Ruff advisory summary",
            "",
            f"- Repository: `{summary['repo']}`",
            f"- Scanned commit: `{summary['commit']}`",
            f"- Ruff: `{summary['ruff_version']}`",
            f"- Config hash: `{summary['config_hash']}`",
            f"- Config revision: `{summary['config_revision']}`",
            f"- Scope: {summary['scope']}",
            f"- Elapsed: {summary['elapsed_seconds']:.3f} seconds",
            f"- Findings: `ruff check` {check_count}; `ruff format --check` {format_count}",
            f"- Command exit codes: install `{codes['ruff_install']}`, version `"
            f"{codes['ruff_version']}`, check `{codes['ruff_check']}`, format `"
            f"{codes['ruff_format_check']}`.",
            f"- Error categories: `{error_categories}`",
            "",
        ]
    )


def run_advisory(
    repo_root: Path,
    output_dir: Path,
    *,
    ci_output_dir: Path | None = None,
    repository: str | None = None,
    commit: str | None = None,
    step_summary_path: Path | None = None,
    command_runner: CommandRunner = subprocess.run,
) -> dict[str, Any]:
    """Run pinned advisory checks and persist machine-readable evidence."""
    repo_root = Path(repo_root)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if ci_output_dir is not None:
        ci_output_dir = Path(ci_output_dir)
        ci_output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()

    if repository is None:
        repository = os.environ.get("GITHUB_REPOSITORY", "local")
    commit_result = None
    if commit is None:
        commit_result = _run_command(["git", "rev-parse", "HEAD"], repo_root, command_runner)
        commit = commit_result["stdout"].strip() or "unavailable"

    install_result = _run_command(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            f"ruff=={RUFF_VERSION}",
        ],
        repo_root,
        command_runner,
    )
    version_result = _run_command(
        [sys.executable, "-m", "ruff", "--version"], repo_root, command_runner
    )
    expected_version = f"ruff {RUFF_VERSION}"
    version_matches = (
        version_result["returncode"] == 0 and version_result["stdout"].strip() == expected_version
    )
    if version_matches:
        check_result = _run_command(
            [sys.executable, "-m", "ruff", "check", "--output-format=json", "."],
            repo_root,
            command_runner,
        )
        format_result = _run_command(
            [sys.executable, "-m", "ruff", "format", "--check", "--diff", "."],
            repo_root,
            command_runner,
        )
    else:
        reason = f"Skipped: expected {expected_version}; pinned Ruff is unavailable."
        check_result = {"returncode": None, "stdout": "", "stderr": reason}
        format_result = {"returncode": None, "stdout": "", "stderr": reason}

    check_findings = None
    if check_result["returncode"] is not None:
        try:
            check_data = json.loads(check_result["stdout"])
            if isinstance(check_data, list):
                check_findings = len(check_data)
        except json.JSONDecodeError:
            pass
    format_findings = _format_count(format_result)
    elapsed_seconds = round(time.perf_counter() - started, 3)

    config_path = repo_root / "ruff.toml"
    try:
        config_hash = hashlib.sha256(config_path.read_bytes()).hexdigest()
        config_error = None
    except OSError as error:
        config_hash = "unavailable"
        config_error = str(error)

    command_results = {
        "ruff_install": install_result,
        "ruff_version": version_result,
        "ruff_check": check_result,
        "ruff_format_check": format_result,
    }
    if commit_result is not None:
        command_results["git_rev_parse"] = commit_result
    command_errors: dict[str, str | None] = {}
    for name, result in command_results.items():
        returncode = result["returncode"]
        stderr = result["stderr"].strip()
        if returncode is None:
            command_errors[name] = stderr or "command could not be executed"
        elif name in {"ruff_install", "ruff_version", "git_rev_parse"} and returncode:
            command_errors[name] = stderr or f"command exited with {returncode}"
        elif name == "ruff_check" and (returncode not in {0, 1} or check_findings is None):
            command_errors[name] = stderr or "Ruff check did not return valid JSON findings"
        elif name == "ruff_format_check" and (returncode not in {0, 1} or format_findings is None):
            command_errors[name] = stderr or "Ruff format check did not report a result"
        else:
            command_errors[name] = None
    if not version_matches:
        command_errors["ruff_version"] = (
            version_result["stderr"].strip()
            or f"Expected {expected_version}; received {version_result['stdout'].strip() or 'no version'}"
        )
    if config_error:
        command_errors["config"] = config_error

    report = {
        "fr_id": "FR-20261025-ruff-advisory-lint-rollout",
        "repository": repository,
        "commit": commit,
        "ruff_version": version_result["stdout"].strip() or "unavailable",
        "config": {
            "path": "ruff.toml",
            "sha256": config_hash,
            "revision": f"sha256:{config_hash}",
        },
        "scan_scope": SCAN_SCOPE,
        "elapsed_seconds": elapsed_seconds,
        "finding_counts": {
            "ruff_check": check_findings,
            "ruff_format": format_findings,
        },
        "command_exit_codes": {
            name: result["returncode"] for name, result in command_results.items()
        },
        "command_errors": command_errors,
        "command_stderr": {
            name: result["stderr"].strip() or None for name, result in command_results.items()
        },
    }

    artifacts = {
        "ruff-install.stdout.txt": install_result["stdout"],
        "ruff-install.stderr.txt": install_result["stderr"],
        "ruff-version.stdout.txt": version_result["stdout"],
        "ruff-version.stderr.txt": version_result["stderr"],
        "ruff-check.json": check_result["stdout"],
        "ruff-check.stderr.txt": check_result["stderr"],
        "ruff-format.diff.txt": format_result["stdout"],
        "ruff-format.stderr.txt": format_result["stderr"],
    }
    for filename, contents in artifacts.items():
        _write_text(output_dir / filename, contents)
    _write_text(
        output_dir / "summary.json",
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
    )

    ci_summary = _safe_ci_summary(report)
    if ci_output_dir is not None:
        _write_text(
            ci_output_dir / "summary.json",
            json.dumps(ci_summary, indent=2, ensure_ascii=False) + "\n",
        )

    markdown = _summary_markdown(ci_summary)
    if step_summary_path is not None:
        step_summary_path = Path(step_summary_path)
        with step_summary_path.open("a", encoding="utf-8") as summary_file:
            summary_file.write(markdown)
    print(markdown, end="")
    return report


def main() -> int:
    """Run CI advisory checks from the Music repository root."""
    repo_root = Path(__file__).resolve().parents[1]
    summary_value = os.environ.get("GITHUB_STEP_SUMMARY")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    run_attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "")
    ci_output_dir = None
    if run_id.isdecimal() and run_attempt.isdecimal():
        ci_output_dir = repo_root / "tmp" / "ruff-advisory-ci" / f"{run_id}-{run_attempt}"
    run_advisory(
        repo_root,
        repo_root / "tmp" / "ruff-advisory-local",
        ci_output_dir=ci_output_dir,
        step_summary_path=Path(summary_value) if summary_value else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
