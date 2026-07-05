"""Tests for src/guitar_tech/persona_rubric.py (FR-20260705-guitar-tech-persona-agent).

Verifies the persona-matching rubric against real catalog_songs rows
(key_sig + bpm + artist -> blended guitar-legend persona), plus the
boundary conditions of each rule.

Hand-verified pilot cases (from catalog_songs, ids in comments):
  - id35 The Letter / Joe Cocker      (Bbm, 91)  -> slow blues trio
  - id27 Pick Up the Pieces / AWB     (Fm, 108)  -> funk duo
  - id14 25 or 6 to 4 / Chicago       (A, 148)   -> Eddie Van Halen
  - id13 I Can't Go for That / H&O    (F, 110)   -> John Mayer (default)
  - id20 Black Magic Woman / Santana  (Dm, 120)  -> Jimi Hendrix (artist hint)
"""
from __future__ import annotations

from guitar_tech.persona_rubric import (
    ALBERT_KING,
    BB_KING,
    EVH,
    FRUSCIANTE,
    HENDRIX,
    MAYER,
    PRINCE,
    SRV,
    is_minor_key,
    score_persona,
)


def test_is_minor_key_detects_trailing_m():
    assert is_minor_key("Am") is True
    assert is_minor_key("F#m") is True
    assert is_minor_key("Bbm") is True


def test_is_minor_key_rejects_major_keys():
    assert is_minor_key("A") is False
    assert is_minor_key("Ab") is False
    assert is_minor_key("F#") is False


def test_is_minor_key_handles_missing_key():
    assert is_minor_key(None) is False
    assert is_minor_key("") is False


def test_the_letter_joe_cocker_is_slow_blues_trio():
    match = score_persona(artist="Joe Cocker", key_sig="Bbm", bpm=91)
    assert match.personas == [SRV, ALBERT_KING, BB_KING]


def test_pick_up_the_pieces_average_white_band_is_funk_duo():
    match = score_persona(artist="Average White Band", key_sig="Fm", bpm=108)
    assert match.personas == [PRINCE, FRUSCIANTE]


def test_25_or_6_to_4_chicago_is_eddie_van_halen():
    match = score_persona(artist="Chicago", key_sig="A", bpm=148)
    assert match.personas == [EVH]


def test_i_cant_go_for_that_hall_and_oates_defaults_to_mayer():
    match = score_persona(artist="Hall & Oates", key_sig="F", bpm=110)
    assert match.personas == [MAYER]


def test_black_magic_woman_santana_is_hendrix_via_artist_hint():
    match = score_persona(artist="Santana", key_sig="Dm", bpm=120)
    assert match.personas == [HENDRIX]
    assert "Santana" in match.rationale


def test_santana_hint_matches_featuring_credit():
    # id32 "Smooth" / Santana feat. Rob Thomas — substring match on artist field
    match = score_persona(artist="Santana feat. Rob Thomas", key_sig="Am", bpm=115)
    assert match.personas == [HENDRIX]


def test_major_key_excludes_slow_blues_and_funk_rules():
    # Major key at slow tempo must NOT hit the slow-blues rule (minor-key gated)
    match = score_persona(artist="Kenny Loggins", key_sig="D", bpm=95)
    assert match.personas == [MAYER]


def test_bpm_130_boundary_is_hard_rock():
    match = score_persona(artist="Some Artist", key_sig="C", bpm=130)
    assert match.personas == [EVH]


def test_bpm_129_boundary_is_not_hard_rock():
    match = score_persona(artist="Some Artist", key_sig="C", bpm=129)
    assert match.personas == [MAYER]


def test_bpm_99_is_slow_blues_when_minor():
    match = score_persona(artist="Some Artist", key_sig="Em", bpm=99)
    assert match.personas == [SRV, ALBERT_KING, BB_KING]


def test_bpm_100_is_funk_when_minor():
    match = score_persona(artist="Some Artist", key_sig="Em", bpm=100)
    assert match.personas == [PRINCE, FRUSCIANTE]


def test_bpm_112_is_funk_when_minor():
    match = score_persona(artist="Some Artist", key_sig="Em", bpm=112)
    assert match.personas == [PRINCE, FRUSCIANTE]


def test_bpm_113_minor_falls_through_to_default():
    # Between funk (<=112) and hard rock (>=130) bands, minor key alone isn't enough
    match = score_persona(artist="Some Artist", key_sig="Em", bpm=113)
    assert match.personas == [MAYER]


def test_missing_bpm_defaults_to_mayer():
    match = score_persona(artist="Unknown Artist", key_sig="Am", bpm=None)
    assert match.personas == [MAYER]


def test_label_property_joins_personas():
    match = score_persona(artist="Joe Cocker", key_sig="Bbm", bpm=91)
    assert match.label == "Stevie Ray Vaughan + Albert King + B.B. King"
