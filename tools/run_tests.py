"""Run the repository pytest suite with optional xdist parallelism."""

from __future__ import annotations

import argparse
import configparser
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path


def _marker_expression(repo_root: Path) -> str | None:
    config = configparser.ConfigParser(interpolation=None)
    config.read(repo_root / "pytest.ini", encoding="utf-8")
    addopts = shlex.split(config.get("pytest", "addopts", fallback=""))
    try:
        return addopts[addopts.index("-m") + 1]
    except (ValueError, IndexError):
        return None


def _policy(repo_root: Path) -> dict[str, object]:
    with (repo_root / "tools" / "parallel_test_policy.json").open(encoding="utf-8") as policy_file:
        return json.load(policy_file)


def _policy_exclusions(repo_root: Path) -> list[str]:
    return list(_policy(repo_root).get("excluded_markers", []))


def _parallel_ci_enabled(repo_root: Path) -> bool:
    return bool(_policy(repo_root).get("parallel_ci", False))


def _runner_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    environment.pop("PYTEST_PLUGINS", None)
    return environment


def _combined_marker_expression(repo_root: Path) -> str:
    configured = _marker_expression(repo_root)
    exclusions = [f"not {marker}" for marker in _policy_exclusions(repo_root)]
    policy_expression = " and ".join(exclusions)
    if configured and policy_expression:
        return f"({configured}) and ({policy_expression})"
    return configured or policy_expression


def _serial_marker_expression(repo_root: Path) -> str:
    configured = _marker_expression(repo_root)
    markers = _policy_exclusions(repo_root)
    serial_expression = " or ".join(markers)
    if configured and serial_expression:
        return f"({configured}) and ({serial_expression})"
    return configured or serial_expression


def build_command(*, parallel: bool, junitxml: Path | None, repo_root: Path | None = None) -> list[str]:
    """Build a pytest command while preserving repository configuration."""
    repo_root = repo_root or Path(__file__).parents[1]
    if parallel and not _parallel_ci_enabled(repo_root):
        raise RuntimeError("parallel CI is disabled by tools/parallel_test_policy.json")
    command = [sys.executable, "-m", "pytest", "-p", "pytest_mock", "--quiet", "--tb=short", "-rs"]
    command.extend(["-m", _combined_marker_expression(repo_root) if parallel else _serial_marker_expression(repo_root)])
    if parallel:
        workers = int(_policy(repo_root).get("max_workers", 2))
        command.extend(["-p", "xdist.plugin", "-n", str(workers)])
    if junitxml is not None:
        command.append(f"--junitxml={junitxml}")
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parallel", action="store_true", help="run with pytest-xdist workers")
    parser.add_argument("--junitxml", type=Path, help="write JUnit XML to this path")
    parser.add_argument("--parallel-junitxml", type=Path, help="write the parallel lane JUnit XML")
    parser.add_argument("--serial-junitxml", type=Path, help="write the serial lane JUnit XML")
    args = parser.parse_args()
    repo_root = Path(__file__).parents[1]
    if args.parallel:
        if not _parallel_ci_enabled(repo_root):
            parser.error("--parallel is disabled by tools/parallel_test_policy.json")
        junitxml = args.junitxml or args.parallel_junitxml
        if junitxml is not None:
            junitxml.parent.mkdir(parents=True, exist_ok=True)
        return subprocess.run(
            build_command(parallel=True, junitxml=junitxml),
            check=False,
            env=_runner_environment(),
        ).returncode

    if args.junitxml is not None and args.parallel_junitxml is None and args.serial_junitxml is None:
        args.junitxml.parent.mkdir(parents=True, exist_ok=True)
        return subprocess.run(
            build_command(parallel=False, junitxml=args.junitxml),
            check=False,
            env=_runner_environment(),
        ).returncode

    parallel_junitxml = args.parallel_junitxml or Path("tmp/pytest-parallel-junit.xml")
    serial_junitxml = args.serial_junitxml or Path("tmp/pytest-serial-junit.xml")
    for junitxml in (parallel_junitxml, serial_junitxml):
        junitxml.parent.mkdir(parents=True, exist_ok=True)
    if not _parallel_ci_enabled(repo_root):
        return subprocess.run(
            build_command(parallel=False, junitxml=serial_junitxml),
            check=False,
            env=_runner_environment(),
        ).returncode

    exit_codes = []
    for parallel, junitxml in ((True, parallel_junitxml), (False, serial_junitxml)):
        exit_codes.append(
            subprocess.run(
                build_command(parallel=parallel, junitxml=junitxml),
                check=False,
                env=_runner_environment(),
            ).returncode
        )
    return next((code for code in exit_codes if code), 0)


if __name__ == "__main__":
    raise SystemExit(main())