"""Tests for src/guitar_tech/pilot_selector.py (FR-20260705-guitar-tech-persona-agent).

Verifies the token-based fuzzy matcher correctly identifies which
catalog_songs already have a dedicated .hlx preset in HelixFiles/, and
correctly leaves genuine gap songs (including the 5 hand-verified pilots)
unmatched.
"""
from __future__ import annotations

from guitar_tech.pilot_selector import (
    find_gap_songs,
    has_dedicated_preset,
    tokenize,
)

# Real HelixFiles/ filenames at the time this FR was authored (excluding
# generic non-song-named presets like BluesRythRock.hlx, Cool.hlx, etc.,
# which are intentionally NOT tied to any specific catalog song).
EXISTING_FILENAMES = [
    "80sRythRock.hlx",
    "Acoustic_Smooth_Warm.hlx",
    "Ambient_Swells_Everything_I_Need.hlx",
    "Barracuda_Heart.hlx",
    "BluesRythRock.hlx",
    "Call_Me_Shinedown.hlx",
    "CarnivalLeadTone.hlx",
    "Change The World.hlx",
    "ClassRythRock.hlx",
    "Cool.hlx",
    "Go_Your_Own_Way_Fleetwood_Mac.hlx",
    "HeartBreakerCupid.hlx",
    "Heart_of_Rock_n_Roll_Huey_Lewis.hlx",
    "Heartbreaker.hlx",
    "Hit_The_Road_Jack.hlx",
    "Jump.hlx",
    "LifeFastLane.hlx",
    "More Than A Feel.hlx",
    "More_than_a_feeling.hlx",
    "Mr_Brightside_The_Killers.hlx",
    "Our_Lips_Are_Sealed_Go_Gos.hlx",
    "Rhiannon_Fleetwood_Mac.hlx",
    "Rocky_Mountain_Way_Joe_Walsh.hlx",
    "SmoothRythRock.hlx",
    "Thrill Is Gone.hlx",
]


def test_tokenize_splits_camel_case_and_underscores():
    assert tokenize("CarnivalLeadTone") == {"carnival", "lead", "tone"}
    assert tokenize("Rhiannon_Fleetwood_Mac") == {"rhiannon", "fleetwood", "mac"}


def test_tokenize_drops_stopwords_and_single_chars():
    assert tokenize("Heart of Rock & Roll") == {"heart", "rock", "roll"}


def test_tokenize_handles_none_and_empty():
    assert tokenize(None) == set()
    assert tokenize("") == set()


def test_rhiannon_fleetwood_mac_has_dedicated_preset():
    assert has_dedicated_preset("Rhiannon", "Fleetwood Mac", EXISTING_FILENAMES) is True


def test_change_the_world_has_dedicated_preset():
    assert has_dedicated_preset("Change The World", "Eric Clapton", EXISTING_FILENAMES) is True


def test_thrill_is_gone_has_dedicated_preset():
    assert has_dedicated_preset("Thrill Is Gone", "BB King", EXISTING_FILENAMES) is True


def test_rocky_mountain_way_has_dedicated_preset():
    assert has_dedicated_preset("Rocky Mountain Way", "Joe Walsh", EXISTING_FILENAMES) is True


def test_heart_of_rock_and_roll_has_dedicated_preset():
    assert has_dedicated_preset("Heart of Rock & Roll", "Huey Lewis and the News", EXISTING_FILENAMES) is True


def test_carnival_has_dedicated_preset():
    assert has_dedicated_preset("Carnival", "Natalie Merchant", EXISTING_FILENAMES) is True


def test_the_letter_joe_cocker_is_a_gap():
    assert has_dedicated_preset("The Letter", "Joe Cocker", EXISTING_FILENAMES) is False


def test_pick_up_the_pieces_is_a_gap():
    assert has_dedicated_preset("Pick Up the Pieces", "Average White Band", EXISTING_FILENAMES) is False


def test_25_or_6_to_4_is_a_gap():
    assert has_dedicated_preset("25 or 6 to 4", "Chicago", EXISTING_FILENAMES) is False


def test_i_cant_go_for_that_is_a_gap():
    assert has_dedicated_preset("I Can't Go for That", "Hall & Oates", EXISTING_FILENAMES) is False


def test_black_magic_woman_is_a_gap():
    assert has_dedicated_preset("Black Magic Woman", "Santana", EXISTING_FILENAMES) is False


def test_find_gap_songs_filters_rows():
    rows = [
        {"id": 5, "title": "Rhiannon", "artist": "Fleetwood Mac", "key_sig": "Am", "bpm": 129},
        {"id": 35, "title": "The Letter", "artist": "Joe Cocker", "key_sig": "Bbm", "bpm": 91},
        {"id": 41, "title": "Change The World", "artist": "Eric Clapton", "key_sig": "A", "bpm": 98},
    ]
    gaps = find_gap_songs(rows, EXISTING_FILENAMES)
    assert [g.id for g in gaps] == [35]
    assert gaps[0].title == "The Letter"
