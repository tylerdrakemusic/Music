"""Tests for src/guitar_tech/hlx_validator.py (FR-20260705-guitar-tech-persona-agent).

Covers: JSON validity, top-level skeleton conformance, @model id existence,
declared-param range compliance, device-compatibility (best-effort), and
single-file vs. batch validation.
"""
from __future__ import annotations

import json

from guitar_tech.hlx_generator import generate_preset
from guitar_tech.hlx_validator import validate_batch, validate_preset_dict, validate_preset_file
from guitar_tech.persona_rubric import MAYER, PersonaMatch


def _valid_preset() -> dict:
    match = PersonaMatch([MAYER], "test rationale")
    return generate_preset(title="Test Song", artist="Test Artist", bpm=100, persona_match=match)


def test_valid_generated_preset_passes():
    result = validate_preset_dict(_valid_preset())
    assert result.ok is True
    assert result.issues == []


def test_missing_top_level_key_fails():
    preset = _valid_preset()
    del preset["schema"]
    result = validate_preset_dict(preset)
    assert result.ok is False
    assert any("schema" in issue.location for issue in result.issues)


def test_wrong_schema_value_fails():
    preset = _valid_preset()
    preset["schema"] = "NotL6Preset"
    result = validate_preset_dict(preset)
    assert result.ok is False


def test_missing_dsp0_fails():
    preset = _valid_preset()
    del preset["data"]["tone"]["dsp0"]
    result = validate_preset_dict(preset)
    assert result.ok is False
    assert any("dsp0" in issue.location for issue in result.issues)


def test_unknown_model_id_fails():
    preset = _valid_preset()
    preset["data"]["tone"]["dsp0"]["block0"]["@model"] = "HD2_TotallyMadeUpModel"
    result = validate_preset_dict(preset)
    assert result.ok is False
    assert any("block0" in issue.location for issue in result.issues)


def test_out_of_range_declared_param_fails():
    preset = _valid_preset()
    # block1 is the reverb (HD2_Reverb63Spring) for the Mayer recipe; Decay's
    # declared range is [0.0, 1.0].
    preset["data"]["tone"]["dsp0"]["block1"]["Decay"] = 5.0
    result = validate_preset_dict(preset)
    assert result.ok is False
    assert any("Decay" in issue.location for issue in result.issues)


def test_device_incompatible_model_flagged(monkeypatch):
    import guitar_tech.hlx_validator as validator_mod

    monkeypatch.setattr(validator_mod, "model_supports_device", lambda model, device_id=None: False)
    result = validate_preset_dict(_valid_preset())
    assert result.ok is False
    assert any("device" in issue.message.lower() for issue in result.issues)


def test_validate_preset_file_handles_invalid_json(tmp_path):
    bad_file = tmp_path / "broken.hlx"
    bad_file.write_text("{not valid json", encoding="utf-8")
    result = validate_preset_file(bad_file)
    assert result.ok is False
    assert any("json" in issue.message.lower() for issue in result.issues)


def test_validate_preset_file_valid_round_trip(tmp_path):
    good_file = tmp_path / "good.hlx"
    good_file.write_text(json.dumps(_valid_preset()), encoding="utf-8")
    result = validate_preset_file(good_file)
    assert result.ok is True


def test_validate_batch_returns_one_result_per_file(tmp_path):
    good_file = tmp_path / "good.hlx"
    bad_file = tmp_path / "bad.hlx"
    good_file.write_text(json.dumps(_valid_preset()), encoding="utf-8")
    bad_file.write_text("nope", encoding="utf-8")

    results = validate_batch([good_file, bad_file])
    assert len(results) == 2
    assert results[0].ok is True
    assert results[1].ok is False
