"""Regression tests for CI exclusion and unavailable-infrastructure policy."""

import importlib.util
import json
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_ci_unavailable_marker_is_registered_and_deploy_runs_full_suite():
    pytest_config = (ROOT / "pytest.ini").read_text(encoding="utf-8")
    deploy_workflow = (ROOT / ".github" / "workflows" / "deploy-hyperthreat-studio.yml").read_text(
        encoding="utf-8"
    )

    assert "ci_unavailable:" in pytest_config
    assert "run: pytest -q" in deploy_workflow
    assert "tests/test_hyperthreat_studio_app.py" not in deploy_workflow


def test_skip_bearing_modules_explicitly_classify_unavailable_infrastructure():
    skip_bearing_modules = (
        "test_band_mgmt_catalog_export.py",
        "test_band_mgmt_http_file_serve.py",
        "test_band_mgmt_playback_sheets.py",
        "test_band_mgmt_playwright.py",
        "test_cc_charts_sync.py",
        "test_gig_inventory.py",
        "test_guitar_trainer_db.py",
        "test_guitar_trainer_metronome.py",
        "test_scale_trainer_feature_flags.py",
        "test_scale_trainer_playwright.py",
        "test_sheet_music_ingest.py",
    )

    for module_name in skip_bearing_modules:
        source = (ROOT / "tests" / module_name).read_text(encoding="utf-8")
        assert "pytest.mark.ci_unavailable" in source, module_name


def test_ci_workflow_reports_skip_reasons():
    workflow = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    conftest = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")

    assert (
        "python tools/run_tests.py --parallel-junitxml tmp/pytest-parallel-junit.xml --serial-junitxml tmp/pytest-serial-junit.xml --manifest tmp/pytest-ci-manifest.json"
        in workflow
    )
    assert "Total skips:" in conftest


def test_ruff_advisory_runner_records_findings_and_tool_errors(
    tmp_path: Path,
    capsys,
) -> None:
    runner_path = ROOT / "tools" / "ruff_advisory.py"
    assert runner_path.is_file(), "advisory Ruff runner is missing"
    spec = importlib.util.spec_from_file_location("music_ruff_advisory", runner_path)
    assert spec is not None and spec.loader is not None
    runner_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner_module)

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "ruff.toml").write_text("line-length = 100\n", encoding="utf-8")
    source_sentinel = "SENTINEL_SOURCE_SNIPPET"
    path_sentinel = "src/private-sentinel.py"
    secret_sentinel = "sentinel-secret-value"
    url_sentinel = (
        "https://user:sentinel-secret-value@private.example/path?token=sentinel-secret-value"
    )
    check_json = json.dumps(
        [
            {
                "code": "F401",
                "filename": path_sentinel,
                "message": f"{source_sentinel} token={secret_sentinel} {url_sentinel}",
                "source": source_sentinel,
            }
        ]
    )
    format_diff = (
        f"--- a/{path_sentinel}\n+++ b/{path_sentinel}\n"
        f"+{source_sentinel} token={secret_sentinel} {url_sentinel}\n"
        "1 file would be reformatted\n"
    )
    command_results = iter(
        (
            subprocess.CompletedProcess(
                [],
                1,
                f"installer output {source_sentinel}\n",
                f"pip network failure at {path_sentinel}: token={secret_sentinel} {url_sentinel}",
            ),
            subprocess.CompletedProcess(
                [], 0, "ruff 0.17.2\n", f"version detail token={secret_sentinel}\n"
            ),
            subprocess.CompletedProcess(
                [], 1, check_json, f"check detail {source_sentinel} {url_sentinel}\n"
            ),
            subprocess.CompletedProcess(
                [], 1, format_diff, f"format detail token={secret_sentinel}\n"
            ),
        )
    )
    invoked_commands: list[list[str]] = []

    def command_runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        invoked_commands.append(command)
        return next(command_results)

    summary_path = tmp_path / "step-summary.md"
    local_output_dir = tmp_path / "ruff-advisory-local"
    ci_output_dir = tmp_path / "ruff-advisory-ci" / "1234-2"
    report = runner_module.run_advisory(
        repo_root=repo_root,
        output_dir=local_output_dir,
        ci_output_dir=ci_output_dir,
        repository="tylerdrakemusic/Music",
        commit="abc123",
        step_summary_path=summary_path,
        command_runner=command_runner,
    )

    assert report["repository"] == "tylerdrakemusic/Music"
    assert report["commit"] == "abc123"
    assert report["ruff_version"] == "ruff 0.17.2"
    assert report["config"]["sha256"]
    assert report["finding_counts"] == {"ruff_check": 1, "ruff_format": 1}
    assert report["command_exit_codes"] == {
        "ruff_install": 1,
        "ruff_version": 0,
        "ruff_check": 1,
        "ruff_format_check": 1,
    }
    assert len(invoked_commands) == 4
    assert "--check" in invoked_commands[3]

    local_check = (local_output_dir / "ruff-check.json").read_text(encoding="utf-8")
    local_diff = (local_output_dir / "ruff-format.diff.txt").read_text(encoding="utf-8")
    local_install_stdout = (local_output_dir / "ruff-install.stdout.txt").read_text(
        encoding="utf-8"
    )
    local_stderr = (local_output_dir / "ruff-install.stderr.txt").read_text(encoding="utf-8")
    local_check_stderr = (local_output_dir / "ruff-check.stderr.txt").read_text(encoding="utf-8")
    local_format_stderr = (local_output_dir / "ruff-format.stderr.txt").read_text(encoding="utf-8")
    local_summary = (local_output_dir / "summary.json").read_text(encoding="utf-8")
    assert {path.name for path in local_output_dir.iterdir()} == {
        "ruff-install.stdout.txt",
        "ruff-install.stderr.txt",
        "ruff-version.stdout.txt",
        "ruff-version.stderr.txt",
        "ruff-check.json",
        "ruff-check.stderr.txt",
        "ruff-format.diff.txt",
        "ruff-format.stderr.txt",
        "summary.json",
    }
    assert source_sentinel in local_check and path_sentinel in local_check
    assert secret_sentinel in local_check and url_sentinel in local_check
    assert source_sentinel in local_diff and path_sentinel in local_diff
    assert secret_sentinel in local_diff and url_sentinel in local_diff
    assert source_sentinel in local_install_stdout
    assert secret_sentinel in local_stderr and url_sentinel in local_stderr
    assert source_sentinel in local_check_stderr and url_sentinel in local_check_stderr
    assert secret_sentinel in local_format_stderr
    assert source_sentinel in local_summary and secret_sentinel in local_summary
    assert (local_output_dir / "ruff-version.stdout.txt").read_text(encoding="utf-8") == (
        "ruff 0.17.2\n"
    )
    assert (local_output_dir / "ruff-version.stderr.txt").read_text(encoding="utf-8") == (
        f"version detail token={secret_sentinel}\n"
    )

    ci_files = sorted(path.name for path in ci_output_dir.iterdir())
    assert ci_files == ["summary.json"]
    ci_summary_text = (ci_output_dir / "summary.json").read_text(encoding="utf-8")
    ci_summary = json.loads(ci_summary_text)
    assert set(ci_summary) == {
        "repo",
        "commit",
        "ruff_version",
        "config_hash",
        "config_revision",
        "scope",
        "elapsed_seconds",
        "finding_counts",
        "exit_codes",
        "errors",
        "error_categories",
    }
    assert ci_summary["repo"] == "tylerdrakemusic/Music"
    assert ci_summary["commit"] == "abc123"
    assert ci_summary["ruff_version"] == "ruff 0.17.2"
    assert ci_summary["finding_counts"] == {"ruff_check": 1, "ruff_format": 1}
    assert ci_summary["exit_codes"]["ruff_install"] == 1
    assert ci_summary["errors"]["ruff_install"] is True
    assert ci_summary["error_categories"] == ["ruff_install_failed"]

    summary_text = summary_path.read_text(encoding="utf-8")
    captured = capsys.readouterr()
    for sentinel in (source_sentinel, path_sentinel, secret_sentinel, url_sentinel):
        assert sentinel not in ci_summary_text
        assert sentinel not in summary_text
        assert sentinel not in captured.out
        assert sentinel not in captured.err
    assert "tylerdrakemusic/Music" in summary_text
    assert "tylerdrakemusic/Music" in captured.out


def test_ruff_advisory_workflow_is_nonblocking_and_uploads_report() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["test"]["steps"]
    ruff_steps = [step for step in steps if step.get("name") == "Run advisory Ruff checks"]

    assert len(ruff_steps) == 1, "CI must run one advisory Ruff report step"
    assert ruff_steps[0]["if"] == "always()"
    assert ruff_steps[0]["continue-on-error"] is True
    assert ruff_steps[0]["run"] == "python tools/ruff_advisory.py"

    test_step = next(
        step for step in steps if step.get("name") == "Run bounded parallel and serial pytest lanes"
    )
    upload_steps = [step for step in steps if step.get("name") == "Upload advisory Ruff report"]
    assert len(upload_steps) == 1
    assert steps.index(ruff_steps[0]) < steps.index(test_step) < steps.index(upload_steps[0])
    assert upload_steps[0]["if"] == "always()"
    assert upload_steps[0]["uses"] == "actions/upload-artifact@v4"
    assert upload_steps[0]["with"]["path"] == (
        "tmp/ruff-advisory-ci/${{ github.run_id }}-${{ github.run_attempt }}/summary.json"
    )
