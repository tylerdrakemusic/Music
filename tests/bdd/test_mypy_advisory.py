"""BDD coverage for the advisory mypy report contract."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from pytest_bdd import given, scenario, then, when


@dataclass
class _MypyContext:
    runner: ModuleType
    config_path: Path
    local_dir: Path
    ci_dir: Path
    step_summary: Path
    raw_finding: str
    report: dict[str, Any] | None = None
    captured_output: str = ""


@scenario("mypy_advisory.feature", "Existing type findings are reported without failing CI")
def test_mypy_findings_are_reported_without_failing_ci(tmp_path: Path) -> None:
    pass


@given(
    "the Music mypy scope contains one selected source module",
    target_fixture="mypy_context",
)
def selected_mypy_scope(tmp_path: Path) -> _MypyContext:
    runner_path = Path(__file__).resolve().parents[2] / "tools" / "mypy_ci_advisory.py"
    spec = importlib.util.spec_from_file_location("music_mypy_advisory_bdd", runner_path)
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    config_path = tmp_path / "mypy.ini"
    config_path.write_text(
        "[mypy]\npython_version = 3.11\nfiles = src/utils/chord_sheet_output.py\n",
        encoding="utf-8",
    )
    return _MypyContext(
        runner=runner,
        config_path=config_path,
        local_dir=tmp_path / "local",
        ci_dir=tmp_path / "ci",
        step_summary=tmp_path / "step-summary.md",
        raw_finding="src/utils/chord_sheet_output.py:17: error: wrong return [return-value]\n",
    )


@given("mypy reports one existing type finding")
def one_existing_finding(
    mypy_context: _MypyContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(
                command, 0, "1234567890abcdef1234567890abcdef12345678\n", ""
            )
        if command[-1:] == ["--version"]:
            return subprocess.CompletedProcess(command, 0, "mypy 1.18.2 (compiled: yes)\n", "")
        return subprocess.CompletedProcess(
            command, 1, mypy_context.raw_finding + "Found 1 error in 1 file\n", ""
        )

    monkeypatch.setattr(mypy_context.runner.subprocess, "run", fake_run)
    monkeypatch.setenv("GITHUB_REPOSITORY", "tylerdrakemusic/Music")
    monkeypatch.setenv("MYPY_INSTALL_EXIT_CODE", "0")


@when("the advisory report is generated")
def generate_advisory_report(mypy_context: _MypyContext, capsys: pytest.CaptureFixture[str]) -> None:
    assert mypy_context.runner.main(
        [
            "--config-path",
            str(mypy_context.config_path),
            "--local-output-dir",
            str(mypy_context.local_dir),
            "--ci-output-dir",
            str(mypy_context.ci_dir),
            "--step-summary",
            str(mypy_context.step_summary),
        ]
    ) == 0
    mypy_context.report = json.loads(
        (mypy_context.ci_dir / "summary.json").read_text(encoding="utf-8")
    )
    mypy_context.captured_output = capsys.readouterr().out


@then("the report identifies the repository revision and selected scope")
def report_has_metadata(mypy_context: _MypyContext) -> None:
    assert mypy_context.report is not None
    assert mypy_context.report["repository"] == "tylerdrakemusic/Music"
    assert mypy_context.report["commit"] == "1234567890abcdef1234567890abcdef12345678"
    assert mypy_context.report["mypy_version"] == "1.18.2"
    assert mypy_context.report["configuration"]["sha256"] == hashlib.sha256(
        mypy_context.config_path.read_bytes()
    ).hexdigest()
    assert mypy_context.report["scan_scope"] == ["src/utils/chord_sheet_output.py"]
    assert mypy_context.report["finding_count"] == 1


@then("the finding remains in local output but not the CI summary")
def finding_is_confined_to_local_output(mypy_context: _MypyContext) -> None:
    local_output = "\n".join(
        path.read_text(encoding="utf-8")
        for path in mypy_context.local_dir.iterdir()
        if path.is_file()
    )
    ci_summary = (mypy_context.ci_dir / "summary.json").read_text(encoding="utf-8")
    step_summary = mypy_context.step_summary.read_text(encoding="utf-8")
    assert mypy_context.raw_finding.strip() in local_output
    assert mypy_context.raw_finding.strip() not in ci_summary
    assert mypy_context.raw_finding.strip() not in step_summary
    assert mypy_context.raw_finding.strip() not in mypy_context.captured_output