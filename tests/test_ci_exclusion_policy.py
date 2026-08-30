"""Regression tests for CI exclusion and unavailable-infrastructure policy."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ci_unavailable_marker_is_registered_and_deploy_runs_full_suite():
    pytest_config = (ROOT / "pytest.ini").read_text(encoding="utf-8")
    deploy_workflow = (
        ROOT / ".github" / "workflows" / "deploy-hyperthreat-studio.yml"
    ).read_text(encoding="utf-8")

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
    workflow = (ROOT / ".github" / "workflows" / "test.yml").read_text(
        encoding="utf-8"
    )
    conftest = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")

    assert "python tools/run_tests.py --parallel-junitxml tmp/pytest-parallel-junit.xml --serial-junitxml tmp/pytest-serial-junit.xml" in workflow
    assert "Total skips:" in conftest