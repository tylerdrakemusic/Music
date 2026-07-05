"""Tests for src/guitar_tech/hlx_generator.py (FR-20260705-guitar-tech-persona-agent).

Verifies generate_preset() produces a well-formed, valid HX Stomp preset
dict for each of the 5 primary personas reachable from the persona rubric,
grounded against the real committed catalog/helix_reference/ snapshot.
"""
from __future__ import annotations

import json

import pytest

from guitar_tech.hlx_catalog import HX_STOMP_DEVICE_ID, get_model
from guitar_tech.hlx_generator import RECIPES, generate_preset
from guitar_tech.persona_rubric import EVH, HENDRIX, MAYER, PRINCE, SRV, PersonaMatch


@pytest.mark.parametrize("primary", [SRV, HENDRIX, PRINCE, EVH, MAYER])
def test_generate_preset_has_required_top_level_shape(primary):
    match = PersonaMatch([primary], "test rationale")
    preset = generate_preset(title="Test Song", artist="Test Artist", bpm=100, persona_match=match)

    assert preset["version"] == 6
    assert preset["schema"] == "L6Preset"
    assert preset["data"]["device"] == HX_STOMP_DEVICE_ID
    assert "Test Song" in preset["data"]["meta"]["name"]
    dsp0 = preset["data"]["tone"]["dsp0"]
    for routing_key in ("inputA", "inputB", "join", "outputA", "outputB", "split", "cab0"):
        assert routing_key in dsp0


@pytest.mark.parametrize("primary", [SRV, HENDRIX, PRINCE, EVH, MAYER])
def test_generate_preset_blocks_reference_real_models(primary):
    match = PersonaMatch([primary], "test rationale")
    preset = generate_preset(title="Test Song", artist="Test Artist", bpm=100, persona_match=match)
    dsp0 = preset["data"]["tone"]["dsp0"]

    recipe = RECIPES[primary]
    for i, spec in enumerate(recipe):
        block = dsp0[f"block{i}"]
        assert block["@model"] == spec.symbolic_id
        assert block["@position"] == i
        assert block["@path"] == 0
        assert block["@enabled"] is True
        # cross-check the model actually exists in the catalog
        get_model(spec.category, spec.symbolic_id)


@pytest.mark.parametrize("primary", [SRV, HENDRIX, PRINCE, EVH, MAYER])
def test_generate_preset_amp_block_has_cab_and_matching_cab_entry(primary):
    match = PersonaMatch([primary], "test rationale")
    preset = generate_preset(title="Test Song", artist="Test Artist", bpm=100, persona_match=match)
    dsp0 = preset["data"]["tone"]["dsp0"]

    recipe = RECIPES[primary]
    amp_specs = [s for s in recipe if s.role == "amp"]
    assert len(amp_specs) == 1
    amp_index = recipe.index(amp_specs[0])
    amp_block = dsp0[f"block{amp_index}"]
    assert amp_block["@cab"] == "cab0"

    amp_model = get_model("amp", amp_specs[0].symbolic_id)
    assert dsp0["cab0"]["@model"] == amp_model["ircablink"]


def test_generate_preset_unknown_primary_persona_raises():
    match = PersonaMatch(["Nobody Famous"], "test rationale")
    with pytest.raises(KeyError):
        generate_preset(title="Test Song", artist="Test Artist", bpm=100, persona_match=match)


def test_generate_preset_uses_song_bpm_as_tempo():
    match = PersonaMatch([MAYER], "test rationale")
    preset = generate_preset(title="Test Song", artist="Test Artist", bpm=110, persona_match=match)
    assert preset["data"]["tone"]["global"]["@tempo"] == 110.0


def test_generate_preset_defaults_tempo_when_bpm_missing():
    match = PersonaMatch([MAYER], "test rationale")
    preset = generate_preset(title="Test Song", artist="Test Artist", bpm=None, persona_match=match)
    assert preset["data"]["tone"]["global"]["@tempo"] == 120.0


def test_generate_preset_has_three_snapshots_with_all_blocks_enabled():
    match = PersonaMatch([HENDRIX], "test rationale")
    preset = generate_preset(title="Test Song", artist="Test Artist", bpm=100, persona_match=match)
    tone = preset["data"]["tone"]
    block_count = len(RECIPES[HENDRIX])
    for key in ("snapshot0", "snapshot1", "snapshot2"):
        snap = tone[key]
        assert snap["@valid"] is True
        enabled = snap["blocks"]["dsp0"]
        assert len(enabled) == block_count
        assert all(enabled.values())


def test_generate_preset_is_json_serializable_round_trip():
    match = PersonaMatch([SRV, "Albert King", "B.B. King"], "test rationale")
    preset = generate_preset(title="The Letter", artist="Joe Cocker", bpm=91, persona_match=match)
    dumped = json.dumps(preset)
    reloaded = json.loads(dumped)
    assert reloaded == preset
