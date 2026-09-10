from __future__ import annotations

from pathlib import Path


MUSIC_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = MUSIC_ROOT / "src" / "analysis" / "music_dashboard.py"
ROOT_DASHBOARD = MUSIC_ROOT / "dashboard.json"
STARTUP = MUSIC_ROOT / "AGENT_STARTUP.md"
SONGDLC_PIPELINE = MUSIC_ROOT / "docs" / "concepts" / "SONGDLC_PIPELINE.md"
STANDALONE_RADIO_REPORT = MUSIC_ROOT / "reports" / "tjd_radio_phase_alpha_player.html"


ACTIVE_RADIO_MARKERS = (
    "tjd radio",
    "icecast",
    "self-hosted radio",
    "radio tab",
    "start_tjd_radio",
    "start_icecast",
    "8100",
)
RETIRED_PHASE_TOOLS = (
    "radio_phase_alpha_wsl_verify.sh",
    "radio_phase_alpha_wsl_stop.sh",
    "radio_phase_alpha_wsl_start.sh",
    "radio_phase_alpha_wsl_stability.sh",
    "radio_phase_alpha_wsl_setup.sh",
    "radio_phase_alpha_verify.ps1",
    "radio_phase_alpha_stop.ps1",
    "radio_phase_alpha_start.ps1",
    "radio_phase_alpha_setup.ps1",
    "radio_phase_alpha_poc.py",
)
RETIRED_RADIO_TESTS = (
    "test_radio_phase_alpha_poc.py",
    "test_tjd_radio.py",
    "test_recently_played_stub.py",
)


def test_retired_radio_phase_tools_are_absent() -> None:
    assert all(
        not (MUSIC_ROOT / "tools" / filename).exists()
        for filename in RETIRED_PHASE_TOOLS
    )


def test_retired_radio_tests_are_absent() -> None:
    assert all(
        not (MUSIC_ROOT / "tests" / filename).exists()
        for filename in RETIRED_RADIO_TESTS
    )


def test_radio_runtime_and_launch_artifacts_are_removed() -> None:
    radio_root = MUSIC_ROOT / "src" / "radio"
    assert not any(radio_root.glob("*.py"))
    assert not (MUSIC_ROOT / "tools" / "icecast_wsl_bridge.py").exists()
    radio_output = MUSIC_ROOT / "output" / "radio_phase_alpha"
    assert not any(radio_output.rglob("*"))


def test_standalone_radio_report_is_absent() -> None:
    assert not STANDALONE_RADIO_REPORT.exists()


def test_songdlc_pipeline_has_no_active_radio_markers() -> None:
    pipeline_text = SONGDLC_PIPELINE.read_text(encoding="utf-8").lower()

    assert not any(marker in pipeline_text for marker in ACTIVE_RADIO_MARKERS)


def test_music_dashboard_has_no_radio_surface_or_proxy() -> None:
    dashboard_text = DASHBOARD.read_text(encoding="utf-8").lower()

    assert "tab-radio" not in dashboard_text
    assert "api/radio" not in dashboard_text
    assert "localhost:8100" not in dashboard_text
    assert "icecast" not in dashboard_text


def test_music_dashboard_registration_and_startup_contract_have_no_radio_surface() -> None:
    contract_text = "\n".join(
        (
            ROOT_DASHBOARD.read_text(encoding="utf-8"),
            STARTUP.read_text(encoding="utf-8"),
        )
    ).lower()

    assert not any(marker in contract_text for marker in ACTIVE_RADIO_MARKERS)


def test_music_architecture_docs_have_no_active_radio_registrations() -> None:
    paths = (
        MUSIC_ROOT / "diagrams" / "diagram-manifest.json",
        MUSIC_ROOT / "diagrams" / "music-architecture.mmd",
        MUSIC_ROOT / "diagrams" / "music-icecast-primary-architecture.mmd",
        MUSIC_ROOT / "diagrams" / "music-tech-stack.mmd",
        MUSIC_ROOT / "docs" / "mermaid-diagrams.md",
        MUSIC_ROOT / "docs" / "protocols" / "self-hosted-radio-phase-alpha-runbook.md",
        MUSIC_ROOT / "docs" / "protocols" / "tjd-radio-icecast-primary-architecture.md",
        MUSIC_ROOT / "docs" / "protocols" / "IP_STRATEGY.md",
    )

    for path in paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").lower()
        assert not any(marker in text for marker in ACTIVE_RADIO_MARKERS), path


def test_neighboring_music_dashboard_surfaces_remain() -> None:
    dashboard_text = DASHBOARD.read_text(encoding="utf-8")

    assert "Release Signatures" in dashboard_text
    assert "Release Ops" in dashboard_text
    assert "/links" in dashboard_text