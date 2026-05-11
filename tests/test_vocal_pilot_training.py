"""Tests for FR-20260511-vocal-pilot-mp3-training (❤Music side)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from training import vocal_pilot_training as mod


def test_default_templates_cover_required_scales() -> None:
    templates = mod.build_default_templates()
    assert set(templates.keys()) == {"major", "natural_minor", "harmonic_minor"}


def test_generate_bundle_writes_manifest_and_tracks(tmp_path: Path) -> None:
    output_root = tmp_path / "vocal_pilots"
    manifest_path = mod.generate_vocal_pilot_bundle(
        output_root=output_root,
        single_keys=["C"],
        commute_keys=["C", "D"],
        template_names=["major", "natural_minor", "harmonic_minor"],
        workout_name="commute_test",
    )

    assert manifest_path.exists()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    tracks = payload["tracks"]

    single_tracks = [t for t in tracks if t["kind"] == "single_key"]
    commute_tracks = [t for t in tracks if t["kind"] == "commute"]

    assert len(single_tracks) == 3
    assert len(commute_tracks) == 3

    for track in tracks:
        file_path = output_root / track["relative_path"]
        assert file_path.exists()
        assert file_path.suffix == ".wav"
        assert len(track["sha256"]) == 64


def test_smoke_check_detects_missing_file(tmp_path: Path) -> None:
    output_root = tmp_path / "vocal_pilots"
    manifest_path = mod.generate_vocal_pilot_bundle(
        output_root=output_root,
        single_keys=["C"],
        commute_keys=["C"],
        template_names=["major"],
        workout_name="smoke_missing",
    )

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    first_rel = payload["tracks"][0]["relative_path"]
    (output_root / first_rel).unlink()

    result = mod.smoke_check_manifest(manifest_path)
    assert result.failed == 1
    assert any(item.startswith("missing:") for item in result.failures)
