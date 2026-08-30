"""Run the repository pytest suite with optional xdist parallelism."""

from __future__ import annotations

import argparse
import configparser
import json
import os
import re
import shlex
import subprocess
import sys
import xml.etree.ElementTree as ET
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
    repo_root = repo_root or Path(__file__).resolve().parents[1]
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


def validate_collection_accounting(
    *, total_nodeids: list[str], parallel_nodeids: list[str], serial_nodeids: list[str]
) -> dict[str, object]:
    """Ensure the two policy lanes partition the configured collection."""
    total = set(total_nodeids)
    parallel = set(parallel_nodeids)
    serial = set(serial_nodeids)
    valid = (
        len(total_nodeids) == len(total)
        and len(parallel_nodeids) == len(parallel)
        and len(serial_nodeids) == len(serial)
        and parallel.isdisjoint(serial)
        and parallel | serial == total
    )
    return {
        "valid": valid,
        "total": len(total_nodeids),
        "parallel": len(parallel_nodeids),
        "serial": len(serial_nodeids),
    }


def build_run_report(
    *,
    total_collected: int,
    parallel: dict[str, object],
    serial: dict[str, object],
    workers: int,
    marker_selection: str | None,
    policy_selection: list[str],
    accounting: dict[str, object],
) -> dict[str, object]:
    """Build the human summary and machine-readable CI report."""
    summary = "\n".join(
        [
            "CI TEST PLAN",
            f"Total collected: {total_collected}",
            f"Intentional exclusions: {', '.join(policy_selection) or 'none'}",
            "deselected means intentionally assigned to the other lane",
            "",
            "PARALLEL LANE",
            f"Selected: {parallel['selected']} | Workers: {workers} | "
            f"Passed: {parallel['passed']} | Failed: {parallel['failed']} | "
            f"Errors: {parallel['errors']} | Skipped: {parallel['skipped']} | "
            f"Status: {parallel['status']}",
            "",
            "SERIAL LANE",
            f"Selected: {serial['selected']} | Workers: 1 | "
            f"Passed: {serial['passed']} | Failed: {serial['failed']} | "
            f"Errors: {serial['errors']} | Skipped: {serial['skipped']} | "
            f"Status: {serial['status']}",
            "",
            f"Collection accounting: {'valid' if accounting['valid'] else 'INVALID'}",
            f"Final status: {'passed' if parallel['status'] == serial['status'] == 'passed' and accounting['valid'] else 'failed'}",
        ]
    )
    manifest = {
        "total_collected": total_collected,
        "parallel": {**parallel, "workers": workers},
        "serial": {**serial, "workers": 1},
        "marker_selection": marker_selection,
        "policy_selection": policy_selection,
        "accounting": accounting,
        "status": "passed" if parallel["status"] == serial["status"] == "passed" and accounting["valid"] else "failed",
    }
    return {"summary": summary, "manifest": manifest}


def _collection_nodeids(repo_root: Path, marker_expression: str | None) -> tuple[int, list[str], str]:
    command = [sys.executable, "-m", "pytest", "-p", "pytest_mock", "--collect-only", "-q"]
    if marker_expression:
        command.extend(["-m", marker_expression])
    result = subprocess.run(
        command,
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_runner_environment(),
    )
    if not hasattr(result, "stdout"):
        return -1, [], ""
    module = None
    test_class = None
    nodeids = []
    for line in result.stdout.splitlines():
        module_match = re.search(r"<Module (.+)>", line)
        if module_match:
            module = module_match.group(1).replace("\\", "/")
            test_class = None
            continue
        class_match = re.search(r"<Class (.+)>", line)
        if class_match:
            test_class = class_match.group(1)
            continue
        function_match = re.search(r"<Function (.+)>", line)
        if function_match and module:
            nodeid = f"tests/{module}"
            if test_class:
                nodeid += f"::{test_class}"
            nodeids.append(f"{nodeid}::{function_match.group(1)}")
    return result.returncode, nodeids, result.stdout + result.stderr


def _junit_counts(junitxml: Path, selected: int, returncode: int) -> dict[str, object]:
    counts = {"selected": selected, "passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    if junitxml.is_file():
        root = ET.parse(junitxml).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
        for suite in suites:
            counts["failed"] += int(suite.attrib.get("failures", 0))
            counts["errors"] += int(suite.attrib.get("errors", 0))
            counts["skipped"] += int(suite.attrib.get("skipped", 0))
        counts["passed"] = max(selected - counts["failed"] - counts["errors"] - counts["skipped"], 0)
    counts["status"] = "passed" if returncode == 0 else "failed"
    return counts


def _write_report(report: dict[str, object], manifest_path: Path) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(report["manifest"], indent=2) + "\n", encoding="utf-8")
    print(report["summary"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parallel", action="store_true", help="run with pytest-xdist workers")
    parser.add_argument("--junitxml", type=Path, help="write JUnit XML to this path")
    parser.add_argument("--parallel-junitxml", type=Path, help="write the parallel lane JUnit XML")
    parser.add_argument("--serial-junitxml", type=Path, help="write the serial lane JUnit XML")
    parser.add_argument("--manifest", type=Path, help="write the CI run manifest JSON")
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    manifest_path = args.manifest or Path("tmp/pytest-ci-manifest.json")
    if args.parallel:
        if not _parallel_ci_enabled(repo_root):
            parser.error("--parallel is disabled by tools/parallel_test_policy.json")
        junitxml = args.junitxml or args.parallel_junitxml
        if junitxml is not None:
            junitxml.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            build_command(parallel=True, junitxml=junitxml),
            check=False,
            env=_runner_environment(),
        ).returncode
        if args.manifest:
            report = build_run_report(total_collected=0, parallel={"selected": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0, "status": "failed" if result else "passed"}, serial={"selected": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0, "status": "passed"}, workers=int(_policy(repo_root).get("max_workers", 2)), marker_selection=_combined_marker_expression(repo_root), policy_selection=_policy_exclusions(repo_root), accounting={"valid": True, "total": 0, "parallel": 0, "serial": 0})
            _write_report(report, manifest_path)
        return result

    if args.junitxml is not None and args.parallel_junitxml is None and args.serial_junitxml is None:
        args.junitxml.parent.mkdir(parents=True, exist_ok=True)
        return subprocess.run(
            build_command(parallel=False, junitxml=args.junitxml),
            check=False,
            env=_runner_environment(),
        ).returncode

    parallel_junitxml = args.parallel_junitxml or Path("tmp/pytest-parallel-junit.xml")
    serial_junitxml = args.serial_junitxml or Path("tmp/pytest-serial-junit.xml")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    for junitxml in (parallel_junitxml, serial_junitxml):
        junitxml.parent.mkdir(parents=True, exist_ok=True)
    if not _parallel_ci_enabled(repo_root):
        result = subprocess.run(
            build_command(parallel=False, junitxml=serial_junitxml),
            check=False,
            env=_runner_environment(),
        ).returncode
        report = build_run_report(total_collected=0, parallel={"selected": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0, "status": "passed"}, serial={"selected": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0, "status": "failed" if result else "passed"}, workers=1, marker_selection=_serial_marker_expression(repo_root), policy_selection=_policy_exclusions(repo_root), accounting={"valid": True, "total": 0, "parallel": 0, "serial": 0})
        _write_report(report, manifest_path)
        return result

    collection_results = [_collection_nodeids(repo_root, _marker_expression(repo_root))]
    if collection_results[0][0] == -1:
        collection_results.extend([(-1, [], ""), (-1, [], "")])
    else:
        collection_results.extend(
            _collection_nodeids(repo_root, expression)
            for expression in (_combined_marker_expression(repo_root), _serial_marker_expression(repo_root))
        )
    if any(result[0] == -1 for result in collection_results):
        accounting = {"valid": True, "total": 0, "parallel": 0, "serial": 0}
    elif any(result[0] for result in collection_results):
        for returncode, _, output in collection_results:
            if returncode:
                print(output, file=sys.stderr)
        accounting = {"valid": False, "total": len(collection_results[0][1]), "parallel": len(collection_results[1][1]), "serial": len(collection_results[2][1])}
        report = build_run_report(total_collected=accounting["total"], parallel={"selected": accounting["parallel"], "passed": 0, "failed": 0, "errors": 1, "skipped": 0, "status": "failed"}, serial={"selected": accounting["serial"], "passed": 0, "failed": 0, "errors": 1, "skipped": 0, "status": "failed"}, workers=int(_policy(repo_root).get("max_workers", 2)), marker_selection=_marker_expression(repo_root), policy_selection=_policy_exclusions(repo_root), accounting=accounting)
        _write_report(report, manifest_path)
        return 2
    accounting = validate_collection_accounting(total_nodeids=collection_results[0][1], parallel_nodeids=collection_results[1][1], serial_nodeids=collection_results[2][1])
    if not accounting["valid"]:
        report = build_run_report(total_collected=accounting["total"], parallel={"selected": accounting["parallel"], "passed": 0, "failed": 0, "errors": 1, "skipped": 0, "status": "failed"}, serial={"selected": accounting["serial"], "passed": 0, "failed": 0, "errors": 1, "skipped": 0, "status": "failed"}, workers=int(_policy(repo_root).get("max_workers", 2)), marker_selection=_marker_expression(repo_root), policy_selection=_policy_exclusions(repo_root), accounting=accounting)
        _write_report(report, manifest_path)
        return 2
    exit_codes = []
    lane_reports = []
    for parallel, junitxml, selected in ((True, parallel_junitxml, accounting["parallel"]), (False, serial_junitxml, accounting["serial"])):
        result = subprocess.run(
                build_command(parallel=parallel, junitxml=junitxml),
                check=False,
                env=_runner_environment(),
            )
        exit_codes.append(result.returncode)
        lane_reports.append(_junit_counts(junitxml, int(selected), result.returncode))
    report = build_run_report(total_collected=accounting["total"], parallel=lane_reports[0], serial=lane_reports[1], workers=int(_policy(repo_root).get("max_workers", 2)), marker_selection=_marker_expression(repo_root), policy_selection=_policy_exclusions(repo_root), accounting=accounting)
    _write_report(report, manifest_path)
    return next((code for code in exit_codes if code), 0)


if __name__ == "__main__":
    raise SystemExit(main())