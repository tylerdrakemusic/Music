from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_mypy_findings_are_reported_without_gating_ci(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: Any,
) -> None:
    runner_path = ROOT / "tools" / "mypy_ci_advisory.py"
    assert runner_path.is_file(), "advisory mypy runner is missing"
    spec = importlib.util.spec_from_file_location("music_mypy_advisory", runner_path)
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)

    config_path = tmp_path / "mypy.ini"
    config_content = (
        "[mypy]\n"
        "python_version = 3.11\n"
        "files = src/utils/chord_sheet_output.py\n"
    )
    config_path.write_text(config_content, encoding="utf-8")
    local_dir = tmp_path / "mypy-advisory-local" / "run-123-1"
    ci_dir = tmp_path / "mypy-advisory-ci" / "run-123-1"
    step_summary = tmp_path / "step-summary.md"
    raw_finding = "src/utils/chord_sheet_output.py:17: error: wrong return [return-value]\n"
    commands: list[tuple[str, ...]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(tuple(command))
        if command[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(
                command, 0, "1234567890abcdef1234567890abcdef12345678\n", ""
            )
        if command[-1:] == ["--version"]:
            return subprocess.CompletedProcess(command, 0, "mypy 1.18.2 (compiled: yes)\n", "")
        return subprocess.CompletedProcess(
            command, 1, raw_finding + "Found 1 error in 1 file\n", ""
        )

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setenv("GITHUB_REPOSITORY", "tylerdrakemusic/Music")
    monkeypatch.setenv("MYPY_INSTALL_EXIT_CODE", "0")

    exit_code = runner.main(
        [
            "--config-path",
            str(config_path),
            "--local-output-dir",
            str(local_dir),
            "--ci-output-dir",
            str(ci_dir),
            "--step-summary",
            str(step_summary),
        ]
    )

    report_path = ci_dir / "summary.json"
    report_text = report_path.read_text(encoding="utf-8")
    summary_text = step_summary.read_text(encoding="utf-8")
    captured = capsys.readouterr()
    report = json.loads(report_text)
    scope = ["src/utils/chord_sheet_output.py"]

    assert exit_code == 0, "Mypy findings must remain advisory"
    assert report["repository"] == "tylerdrakemusic/Music"
    assert report["commit"] == "1234567890abcdef1234567890abcdef12345678"
    assert report["mypy_version"] == "1.18.2"
    assert report["configuration"] == {
        "path": "mypy.ini",
        "sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
    }
    assert report["scan_scope"] == scope
    assert isinstance(report["elapsed_seconds"], (int, float))
    assert report["elapsed_seconds"] >= 0
    assert report["finding_count"] == 1
    assert report["command_exit_codes"] == {
        "mypy_install": 0,
        "mypy_version": 0,
        "mypy_check": 1,
    }
    assert report["tool_errors"] == {
        "mypy_install": False,
        "mypy_version": False,
        "mypy_check": False,
    }
    mypy_command = next(command for command in commands if "--config-file" in command)
    assert mypy_command[-len(scope) :] == tuple(scope)
    assert "--show-error-codes" in mypy_command
    assert "Repository: `tylerdrakemusic/Music`" in summary_text
    assert "Scanned commit: `1234567890abcdef1234567890abcdef12345678`" in summary_text
    assert "Mypy version: `1.18.2`" in summary_text
    assert "Findings: `1`" in summary_text
    assert "Advisory only" in summary_text

    local_output = "\n".join(
        path.read_text(encoding="utf-8") for path in local_dir.iterdir() if path.is_file()
    )
    assert raw_finding.strip() in local_output
    for ci_output in (report_text, summary_text, captured.out, captured.err):
        assert raw_finding.strip() not in ci_output


def test_mypy_exit_one_without_diagnostics_is_reported_as_tool_error(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    runner_path = ROOT / "tools" / "mypy_ci_advisory.py"
    spec = importlib.util.spec_from_file_location("music_mypy_advisory_empty", runner_path)
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)

    config_path = tmp_path / "mypy.ini"
    config_path.write_text(
        "[mypy]\npython_version = 3.11\nfiles = src/utils/chord_sheet_output.py\n",
        encoding="utf-8",
    )
    ci_dir = tmp_path / "mypy-advisory-ci"

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(
                command, 0, "1234567890abcdef1234567890abcdef12345678\n", ""
            )
        if command[-1:] == ["--version"]:
            return subprocess.CompletedProcess(command, 0, "mypy 1.18.2 (compiled: yes)\n", "")
        return subprocess.CompletedProcess(command, 1, "", "")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setenv("GITHUB_REPOSITORY", "tylerdrakemusic/Music")
    monkeypatch.setenv("MYPY_INSTALL_EXIT_CODE", "0")

    runner.main(
        [
            "--config-path",
            str(config_path),
            "--local-output-dir",
            str(tmp_path / "mypy-advisory-local"),
            "--ci-output-dir",
            str(ci_dir),
            "--step-summary",
            str(tmp_path / "step-summary.md"),
        ]
    )

    report = json.loads((ci_dir / "summary.json").read_text(encoding="utf-8"))

    assert report["finding_count"] is None
    assert report["tool_errors"]["mypy_check"] is True


def test_mypy_advisory_workflow_preserves_pytest_as_the_required_gate() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["test"]["steps"]
    mypy_steps = [step for step in steps if step.get("name") == "Run advisory mypy checks"]

    assert len(mypy_steps) == 1, "CI must run one mypy advisory report step"
    assert mypy_steps[0]["if"] == "always()"
    assert mypy_steps[0]["continue-on-error"] is True
    assert "tools/mypy_ci_advisory.py" in mypy_steps[0]["run"]

    pytest_step = next(
        step for step in steps if step.get("name") == "Run bounded parallel and serial pytest lanes"
    )
    upload_steps = [step for step in steps if step.get("name") == "Upload advisory mypy report"]
    assert len(upload_steps) == 1
    assert upload_steps[0]["continue-on-error"] is True
    assert steps.index(mypy_steps[0]) < steps.index(pytest_step) < steps.index(upload_steps[0])
    assert pytest_step["run"].startswith("python tools/run_tests.py ")
    assert upload_steps[0]["if"] == "always()"
    assert upload_steps[0]["uses"] == "actions/upload-artifact@v4"
    assert upload_steps[0]["with"]["path"] == (
        "tmp/mypy-advisory-ci/${{ github.run_id }}-${{ github.run_attempt }}/summary.json"
    )