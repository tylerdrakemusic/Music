"""Tests for src/guitar_tech/hlx_catalog.py (FR-20260705-guitar-tech-persona-agent).

Uses the real committed catalog/helix_reference/ snapshot as test fixtures
(these are Line 6 HX Edit reference files copied verbatim into the repo).
"""
from __future__ import annotations

import pytest

from guitar_tech.hlx_catalog import (
    REFERENCE_DIR,
    default_params,
    find_model_category,
    get_model,
    list_categories,
    load_category,
    load_skeleton,
    model_supports_device,
)

HX_STOMP_DEVICE_ID = 2162694


def test_reference_dir_exists():
    assert REFERENCE_DIR.is_dir()


def test_load_category_returns_list_of_models():
    amps = load_category("amp")
    assert isinstance(amps, list)
    assert any(m["symbolicID"] == "HD2_AmpCaliTexasCh1" for m in amps)


def test_load_category_raises_for_unknown_category():
    with pytest.raises(FileNotFoundError):
        load_category("not_a_real_category")


def test_get_model_finds_known_amp():
    model = get_model("amp", "HD2_AmpCaliTexasCh1")
    assert model["name"] == "Cali Texas Ch 1"
    assert model["ircablink"] == "HD2_CabMicIr_2x12Mandarin"


def test_get_model_raises_keyerror_for_unknown_symbolic_id():
    with pytest.raises(KeyError):
        get_model("amp", "HD2_NotARealAmp")


def test_default_params_builds_dict_of_defaults():
    model = get_model("compressor", "HD2_CompressorRedSqueeze")
    params = default_params(model)
    assert params["Sensitivity"] == 0.44
    assert params["Level"] == 5.4
    assert params["@enabled"] is True


def test_model_supports_device_true_when_no_devices_field():
    # amps without a "devices" key are universally compatible
    model = get_model("amp", "HD2_AmpBritPlexiNrm")
    assert model_supports_device(model, HX_STOMP_DEVICE_ID) is True


def test_model_supports_device_true_when_device_listed():
    model = get_model("amp", "HD2_AmpCaliTexasCh1")
    assert model_supports_device(model, HX_STOMP_DEVICE_ID) is True


def test_model_supports_device_false_when_device_excluded():
    fake_model = {"symbolicID": "Fake", "devices": [{"id": 999999}]}
    assert model_supports_device(fake_model, HX_STOMP_DEVICE_ID) is False


def test_load_skeleton_has_expected_top_level_keys():
    skeleton = load_skeleton()
    assert skeleton["version"] == 6
    assert skeleton["schema"] == "L6Preset"
    assert skeleton["data"]["device"] == HX_STOMP_DEVICE_ID


def test_list_categories_includes_known_categories():
    categories = list_categories()
    for expected in ("amp", "distortion", "compressor", "modulation", "reverb", "delay", "cabmicirs", "io"):
        assert expected in categories


def test_find_model_category_finds_amp():
    assert find_model_category("HD2_AmpCaliTexasCh1") == "amp"


def test_find_model_category_finds_routing_primitive_in_io():
    assert find_model_category("HD2_AppDSPFlowJoin") == "io"


def test_find_model_category_returns_none_for_unknown_id():
    assert find_model_category("HD2_TotallyMadeUpModel") is None
