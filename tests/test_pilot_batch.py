"""Tests for src/guitar_tech/pilot_batch.py (FR-20260705-guitar-tech-persona-agent).

Pure orchestration layer: given song rows + existing filenames, returns one
PilotResult (persona match + generated preset + validation + filename) per
genuine gap song, skipping songs that already have a dedicated preset. No
DB or file I/O -- those live in tools/generate_guitar_tech_pilot.py.
"""
from __future__ import annotations

from guitar_tech.pilot_batch import build_pilot_results, safe_filename_stub

EXISTING_FILENAMES = ["Rhiannon_Fleetwood_Mac.hlx"]

ROWS = [
    {"id": 5, "title": "Rhiannon", "artist": "Fleetwood Mac", "key_sig": "Am", "bpm": 129},
    {"id": 35, "title": "The Letter", "artist": "Joe Cocker", "key_sig": "Bbm", "bpm": 91},
    {"id": 20, "title": "Black Magic Woman", "artist": "Santana", "key_sig": "Dm", "bpm": 120},
]


def test_build_pilot_results_skips_songs_with_dedicated_presets():
    results = build_pilot_results(ROWS, EXISTING_FILENAMES)
    titles = [r.song["title"] for r in results]
    assert "Rhiannon" not in titles
    assert "The Letter" in titles
    assert "Black Magic Woman" in titles
    assert len(results) == 2


def test_build_pilot_results_all_pass_validation():
    results = build_pilot_results(ROWS, EXISTING_FILENAMES)
    assert all(r.validation.ok for r in results)


def test_build_pilot_results_preserves_input_order():
    results = build_pilot_results(ROWS, EXISTING_FILENAMES)
    assert [r.song["id"] for r in results] == [35, 20]


def test_build_pilot_results_assigns_expected_personas():
    results = build_pilot_results(ROWS, EXISTING_FILENAMES)
    by_id = {r.song["id"]: r for r in results}
    assert by_id[35].persona_match.personas[0] == "Stevie Ray Vaughan"
    assert by_id[20].persona_match.personas[0] == "Jimi Hendrix"


def test_safe_filename_stub_replaces_non_alnum():
    assert safe_filename_stub("The Letter") == "The_Letter"
    assert safe_filename_stub("25 or 6 to 4") == "25_or_6_to_4"
    assert safe_filename_stub("I Can't Go for That") == "I_Can_t_Go_for_That"


def test_build_pilot_results_filenames_have_hlx_extension():
    results = build_pilot_results(ROWS, EXISTING_FILENAMES)
    assert all(r.filename.endswith(".hlx") for r in results)
