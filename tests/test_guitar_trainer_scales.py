"""
Tests for FR-20260517-guitar-trainer-scale-exercises and
FR-20260522-guitar-trainer-multi-key.

Covers:
  - SCALE_POSITIONS structure (C: 12 positions, G: 11 positions)
  - CAGED_POSITIONS backward-compat alias
  - ScaleNote fields validity
  - G major pitch-class validation
  - MIDI_TO_FREQ A440 accuracy
  - get_scale_sequence ascending+descending shape, key='G' variant
  - /api/scale-positions?key=C and ?key=G return 11 positions each
  - /api/scale-positions?key=X returns 400
  - /api/scale-log POST: valid insert, key='G' insert, invalid position, invalid bpm
  - /api/scale-log GET: returns list with key column
  - /api/instructor-audio: returns 204 when ELEVENLABS_API_KEY not set
  - HTML: tab-nav, fretboard SVG, scale-key select, scale-position select present
  - DB: scale_practice_log table exists after init_db schema
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from training.scale_data import SCALE_POSITIONS, CAGED_POSITIONS, MIDI_TO_FREQ, get_scale_sequence
import training.musician_training_ui as ui


# ---------------------------------------------------------------------------
# In-memory DB helpers (same pattern as test_guitar_trainer_db.py)
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS guitar_exercises (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    artist TEXT NOT NULL DEFAULT '',
    song_path TEXT NOT NULL DEFAULT '',
    segments TEXT NOT NULL DEFAULT '[]',
    gradient INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS guitar_training_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exercise_id INTEGER,
    song_path TEXT NOT NULL DEFAULT '',
    seg_start TEXT NOT NULL DEFAULT '',
    seg_end TEXT NOT NULL DEFAULT '',
    repetition INTEGER NOT NULL DEFAULT 1,
    logged_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS scale_practice_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL DEFAULT 'C',
    scale TEXT NOT NULL DEFAULT 'C_major',
    position INTEGER NOT NULL DEFAULT 1,
    bpm INTEGER NOT NULL DEFAULT 60,
    reps INTEGER NOT NULL DEFAULT 1,
    duration_minutes INTEGER NOT NULL DEFAULT 0,
    logged_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class _NoClose:
    def __init__(self, c: sqlite3.Connection) -> None:
        object.__setattr__(self, "_c", c)

    def __getattr__(self, name: str):
        return getattr(object.__getattribute__(self, "_c"), name)

    def close(self) -> None:
        pass

    def __enter__(self):
        return object.__getattribute__(self, "_c").__enter__()

    def __exit__(self, *a):
        return object.__getattribute__(self, "_c").__exit__(*a)


@pytest.fixture
def mem_conn():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    yield conn
    conn.close()


@pytest.fixture
def client(mem_conn):
    wrapper = _NoClose(mem_conn)
    ui.app.config["TESTING"] = True
    with patch("training.musician_training_ui.get_connection", return_value=wrapper):
        with ui.app.test_client() as c:
            yield c


# ---------------------------------------------------------------------------
# scale_data.py — SCALE_POSITIONS and CAGED_POSITIONS
# ---------------------------------------------------------------------------

def test_scale_positions_has_c_and_g() -> None:
    """SCALE_POSITIONS must contain C, G, F, D, Bb, B, Eb, A, F#, and the A#/D# aliases."""
    assert {"C", "G", "F", "D", "Bb", "A#", "B", "Eb", "D#", "A", "F#"}.issubset(set(SCALE_POSITIONS.keys()))


def test_key_sigs_js_quotes_sharp_keys(client) -> None:
    """The rendered Guitar Trainer JS must quote F# in KEY_SIGS to remain valid JS."""
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "'F#': 6" in html
    assert "F#: 6" not in html


def test_scale_positions_counts() -> None:
    """C must have 12 positions; G, D, Bb, B, A must have 11; F must have 12; Eb must have 10."""
    assert len(SCALE_POSITIONS["C"]) == 12, f"SCALE_POSITIONS['C'] has {len(SCALE_POSITIONS['C'])} positions, expected 12"
    assert len(SCALE_POSITIONS["G"]) == 11, f"SCALE_POSITIONS['G'] has {len(SCALE_POSITIONS['G'])} positions, expected 11"
    assert len(SCALE_POSITIONS["F"]) == 12, f"SCALE_POSITIONS['F'] has {len(SCALE_POSITIONS['F'])} positions, expected 12"
    assert len(SCALE_POSITIONS["D"]) == 11, f"SCALE_POSITIONS['D'] has {len(SCALE_POSITIONS['D'])} positions, expected 11"
    assert len(SCALE_POSITIONS["Bb"]) == 11, f"SCALE_POSITIONS['Bb'] has {len(SCALE_POSITIONS['Bb'])} positions, expected 11"
    assert len(SCALE_POSITIONS["B"]) == 11, f"SCALE_POSITIONS['B'] has {len(SCALE_POSITIONS['B'])} positions, expected 11"
    assert len(SCALE_POSITIONS["E"]) == 11, f"SCALE_POSITIONS['E'] has {len(SCALE_POSITIONS['E'])} positions, expected 11"
    assert len(SCALE_POSITIONS["F#"]) == 11, f"SCALE_POSITIONS['F#'] has {len(SCALE_POSITIONS['F#'])} positions, expected 11"
    assert len(SCALE_POSITIONS["Eb"]) == 10, f"SCALE_POSITIONS['Eb'] has {len(SCALE_POSITIONS['Eb'])} positions, expected 10"
    assert len(SCALE_POSITIONS["A"]) == 11, f"SCALE_POSITIONS['A'] has {len(SCALE_POSITIONS['A'])} positions, expected 11"


def test_caged_positions_count() -> None:
    """CAGED_POSITIONS alias must point to the 12 C major positions."""
    assert len(CAGED_POSITIONS) == 12
    assert CAGED_POSITIONS is SCALE_POSITIONS["C"]


def test_caged_positions_schema() -> None:
    """Each position must have the required keys."""
    required = {"label", "root_string", "root_fret", "instructor_phrase", "notes"}
    for i, pos in enumerate(CAGED_POSITIONS):
        missing = required - set(pos.keys())
        assert not missing, f"Position {i + 1} missing keys: {missing}"


def test_caged_notes_have_required_keys() -> None:
    """Every note in every position must have string (1-6), fret (0-24), midi (0-127)."""
    for i, pos in enumerate(CAGED_POSITIONS):
        for j, note in enumerate(pos["notes"]):
            assert "string" in note, f"pos {i+1} note {j} missing 'string'"
            assert "fret" in note, f"pos {i+1} note {j} missing 'fret'"
            assert "midi" in note, f"pos {i+1} note {j} missing 'midi'"
            assert 1 <= note["string"] <= 6, f"pos {i+1} note {j} string out of range"
            assert 0 <= note["fret"] <= 24, f"pos {i+1} note {j} fret out of range"
            assert 0 <= note["midi"] <= 127, f"pos {i+1} note {j} midi out of range"


def test_caged_notes_all_in_c_major() -> None:
    """All notes in all C major positions must belong to the C major scale."""
    C_MAJOR_PCS = {0, 2, 4, 5, 7, 9, 11}
    for i, pos in enumerate(CAGED_POSITIONS):
        for note in pos["notes"]:
            assert note["midi"] % 12 in C_MAJOR_PCS, (
                f"Position {i+1} note midi={note['midi']} not in C major"
            )


def test_g_major_positions_pitch_classes() -> None:
    """All notes in all G major positions must belong to the G major scale."""
    G_MAJOR_PCS = {7, 9, 11, 0, 2, 4, 6}  # G A B C D E F#
    for i, pos in enumerate(SCALE_POSITIONS["G"]):
        for note in pos["notes"]:
            assert note["midi"] % 12 in G_MAJOR_PCS, (
                f"G major Position {i+1} note midi={note['midi']} "
                f"(pc={note['midi'] % 12}) not in G major scale"
            )


def test_f_major_positions_pitch_classes() -> None:
    """All notes in all F major positions must belong to the F major scale."""
    F_MAJOR_PCS = {5, 7, 9, 10, 0, 2, 4}  # F G A Bb C D E
    for i, pos in enumerate(SCALE_POSITIONS["F"]):
        for note in pos["notes"]:
            assert note["midi"] % 12 in F_MAJOR_PCS, (
                f"F major Position {i+1} note midi={note['midi']} "
                f"(pc={note['midi'] % 12}) not in F major scale"
            )


def test_d_major_positions_pitch_classes() -> None:
    """All notes in all D major positions must belong to the D major scale."""
    D_MAJOR_PCS = {2, 4, 6, 7, 9, 11, 1}  # D E F# G A B C#
    for i, pos in enumerate(SCALE_POSITIONS["D"]):
        for note in pos["notes"]:
            assert note["midi"] % 12 in D_MAJOR_PCS, (
                f"D major Position {i+1} note midi={note['midi']} "
                f"(pc={note['midi'] % 12}) not in D major scale"
            )


def test_f_sharp_major_positions_pitch_classes() -> None:
    """All notes in all F# major positions must belong to the F# major scale."""
    F_SHARP_MAJOR_PCS = {6, 8, 10, 11, 1, 3, 5}  # F# G# A# B C# D# E#
    for i, pos in enumerate(SCALE_POSITIONS["F#"]):
        for note in pos["notes"]:
            assert note["midi"] % 12 in F_SHARP_MAJOR_PCS, (
                f"F# major Position {i+1} note midi={note['midi']} "
                f"(pc={note['midi'] % 12}) not in F# major scale"
            )


def test_bb_major_positions_pitch_classes() -> None:
    """All notes in all Bb major positions must belong to the Bb major scale."""
    BB_MAJOR_PCS = {10, 0, 2, 3, 5, 7, 9}  # Bb C D Eb F G A
    for i, pos in enumerate(SCALE_POSITIONS["Bb"]):
        for note in pos["notes"]:
            assert note["midi"] % 12 in BB_MAJOR_PCS, (
                f"Bb major Position {i+1} note midi={note['midi']} "
                f"(pc={note['midi'] % 12}) not in Bb major scale"
            )


def test_a_sharp_alias_matches_bb() -> None:
    """SCALE_POSITIONS['A#'] must be the identical list object as SCALE_POSITIONS['Bb']."""
    assert SCALE_POSITIONS["A#"] is SCALE_POSITIONS["Bb"]


def test_d_sharp_alias_matches_eb() -> None:
    """SCALE_POSITIONS['D#'] must be the identical list object as SCALE_POSITIONS['Eb']."""
    assert SCALE_POSITIONS["D#"] is SCALE_POSITIONS["Eb"]


def test_b_major_positions_pitch_classes() -> None:
    """All notes in all B major positions must belong to the B major scale."""
    B_MAJOR_PCS = {11, 1, 3, 4, 6, 8, 10}  # B C# D# E F# G# A#
    for i, pos in enumerate(SCALE_POSITIONS["B"]):
        for note in pos["notes"]:
            assert note["midi"] % 12 in B_MAJOR_PCS, (
                f"B major Position {i+1} note midi={note['midi']} "
                f"(pc={note['midi'] % 12}) not in B major scale"
            )


def test_b_major_max_fret() -> None:
    """No note in any B major position may exceed fret 22."""
    for i, pos in enumerate(SCALE_POSITIONS["B"]):
        for note in pos["notes"]:
            assert note["fret"] <= 22, (
                f"B major Position {i+1} note fret={note['fret']} exceeds 22"
            )

def test_e_major_positions_pitch_classes() -> None:
    """All notes in all E major positions must belong to the E major scale."""
    E_MAJOR_PCS = {4, 6, 8, 9, 11, 1, 3}  # E F# G# A B C# D#
    for i, pos in enumerate(SCALE_POSITIONS["E"]):
        for note in pos["notes"]:
            assert note["midi"] % 12 in E_MAJOR_PCS, (
                f"E major Position {i+1} note midi={note['midi']} "
                f"(pc={note['midi'] % 12}) not in E major scale"
            )

def test_e_major_max_fret() -> None:
    """No note in any E major position may exceed fret 22."""
    for i, pos in enumerate(SCALE_POSITIONS["E"]):
        for note in pos["notes"]:
            assert note["fret"] <= 22, (
                f"E major Position {i+1} note fret={note['fret']} exceeds 22"
            )


def test_eb_major_positions_pitch_classes() -> None:
    """All notes in all Eb major positions must belong to the Eb major scale."""
    EB_MAJOR_PCS = {3, 5, 7, 8, 10, 0, 2}  # Eb F G Ab Bb C D
    for i, pos in enumerate(SCALE_POSITIONS["Eb"]):
        for note in pos["notes"]:
            assert note["midi"] % 12 in EB_MAJOR_PCS, (
                f"Eb major Position {i+1} note midi={note['midi']} "
                f"(pc={note['midi'] % 12}) not in Eb major scale"
            )


def test_eb_major_max_fret() -> None:
    """No note in any Eb major position may exceed fret 22."""
    for i, pos in enumerate(SCALE_POSITIONS["Eb"]):
        for note in pos["notes"]:
            assert note["fret"] <= 22, (
                f"Eb major Position {i+1} note fret={note['fret']} exceeds 22"
            )


def test_caged_positions_have_instructor_phrases() -> None:
    """Each instructor phrase must be non-empty and mention a fret number."""
    for i, pos in enumerate(CAGED_POSITIONS):
        phrase = pos["instructor_phrase"]
        assert phrase, f"Position {i+1} has empty instructor phrase"
        assert any(c.isdigit() for c in phrase), (
            f"Position {i+1} instructor phrase has no fret number: {phrase!r}"
        )


# ---------------------------------------------------------------------------
# scale_data.py — MIDI_TO_FREQ
# ---------------------------------------------------------------------------

def test_midi_to_freq_a440() -> None:
    """MIDI 69 (A4) must be 440.0 Hz (±0.01)."""
    assert abs(MIDI_TO_FREQ[69] - 440.0) < 0.01


def test_midi_to_freq_middle_c() -> None:
    """MIDI 60 (C4) must be ~261.63 Hz (±0.1)."""
    assert abs(MIDI_TO_FREQ[60] - 261.6256) < 0.1


def test_midi_to_freq_all_128() -> None:
    """MIDI_TO_FREQ must contain all 128 entries (0-127)."""
    assert len(MIDI_TO_FREQ) == 128
    assert 0 in MIDI_TO_FREQ and 127 in MIDI_TO_FREQ


# ---------------------------------------------------------------------------
# scale_data.py — get_scale_sequence
# ---------------------------------------------------------------------------

def test_get_scale_sequence_length() -> None:
    """Sequence must be > 1 note (ascending + descending)."""
    for i in range(5):
        seq = get_scale_sequence(i)
        assert len(seq) > 1, f"Position {i+1} sequence too short"


def test_get_scale_sequence_ascending_first_half() -> None:
    """First half of sequence must be non-decreasing (ascending)."""
    for i in range(5):
        seq = get_scale_sequence(i)
        mid = len(seq) // 2
        asc = seq[:mid + 1]
        assert asc == sorted(asc), f"Position {i+1} first half not ascending: {asc}"


def test_get_scale_sequence_descending_second_half() -> None:
    """Second half must be non-increasing (descending)."""
    for i in range(5):
        seq = get_scale_sequence(i)
        mid = len(seq) // 2
        desc = seq[mid:]
        assert desc == sorted(desc, reverse=True), (
            f"Position {i+1} second half not descending: {desc}"
        )


def test_get_scale_sequence_invalid_index() -> None:
    """Out-of-range index must raise ValueError."""
    with pytest.raises(ValueError):
        get_scale_sequence(12)  # 0-11 are valid for C
    with pytest.raises(ValueError):
        get_scale_sequence(-1)


def test_get_scale_sequence_g_key() -> None:
    """get_scale_sequence with key='G' must return a valid ascending+descending sequence."""
    for i in range(11):
        seq = get_scale_sequence(i, key="G")
        assert len(seq) > 1
        mid = len(seq) // 2
        asc = seq[:mid + 1]
        assert asc == sorted(asc), f"G Pos {i+1} first half not ascending"


def test_get_scale_sequence_invalid_key() -> None:
    """Unknown key must raise ValueError."""
    with pytest.raises(ValueError):
        get_scale_sequence(0, key="X")


# ---------------------------------------------------------------------------
# /api/scale-positions route
# ---------------------------------------------------------------------------

def test_api_scale_positions_returns_12(client) -> None:
    """GET /api/scale-positions must return a list of exactly 12 positions (default key=C)."""
    resp = client.get("/api/scale-positions")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) == 12


def test_api_scale_positions_g_returns_11(client) -> None:
    """GET /api/scale-positions?key=G must return a list of exactly 11 G major positions."""
    resp = client.get("/api/scale-positions?key=G")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) == 11
    assert all("G major" in p["instructor_phrase"] for p in data)


def test_api_scale_positions_f_returns_12(client) -> None:
    """GET /api/scale-positions?key=F must return a list of exactly 12 F major positions."""
    resp = client.get("/api/scale-positions?key=F")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) == 12
    assert all("F major" in p["instructor_phrase"] for p in data)


def test_api_scale_positions_f_sharp_returns_11(client) -> None:
    """GET /api/scale-positions?key=F%23 must return a list of exactly 11 F# major positions."""
    resp = client.get("/api/scale-positions?key=F%23")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) == 11
    assert all("F# major" in p["instructor_phrase"] for p in data)


def test_api_scale_positions_d_returns_11(client) -> None:
    """GET /api/scale-positions?key=D must return a list of exactly 11 D major positions."""
    resp = client.get("/api/scale-positions?key=D")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) == 11
    assert all("D major" in p["instructor_phrase"] for p in data)


def test_api_scale_positions_bb_returns_11(client) -> None:
    """GET /api/scale-positions?key=Bb must return a list of exactly 11 B-flat major positions."""
    resp = client.get("/api/scale-positions?key=Bb")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) == 11
    assert all("B-flat major" in p["instructor_phrase"] for p in data)


def test_api_scale_positions_a_sharp_alias_returns_11(client) -> None:
    """GET /api/scale-positions?key=A%23 must return the same 11 A Sharp positions via alias."""
    resp = client.get("/api/scale-positions?key=A%23")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) == 11


def test_api_scale_positions_b_returns_11(client) -> None:
    """GET /api/scale-positions?key=B must return a list of exactly 11 B major positions."""
    resp = client.get("/api/scale-positions?key=B")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) == 11
    assert all("B major" in p["instructor_phrase"] for p in data)


def test_api_scale_positions_eb_returns_10(client) -> None:
    """GET /api/scale-positions?key=Eb must return a list of exactly 10 E-flat major positions."""
    resp = client.get("/api/scale-positions?key=Eb")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) == 10
    assert all("E-flat major" in p["instructor_phrase"] for p in data)


def test_api_scale_positions_d_sharp_alias_returns_10(client) -> None:
    """GET /api/scale-positions?key=D%23 must return same 10 positions as Eb via alias."""
    resp = client.get("/api/scale-positions?key=D%23")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) == 10


def test_api_scale_positions_invalid_key_400(client) -> None:
    """GET /api/scale-positions?key=X must return 400."""
    resp = client.get("/api/scale-positions?key=X")
    assert resp.status_code == 400


def test_api_scale_positions_schema(client) -> None:
    """Each entry must contain required keys."""
    resp = client.get("/api/scale-positions")
    data = resp.get_json()
    required = {"label", "root_string", "root_fret", "instructor_phrase", "notes"}
    for pos in data:
        assert required.issubset(set(pos.keys()))


# ---------------------------------------------------------------------------
# /api/scale-log POST — validation
# ---------------------------------------------------------------------------

def test_scale_log_valid_insert(client, mem_conn) -> None:
    """POST /api/scale-log with valid data must return {ok: true} and insert a row."""
    resp = client.post(
        "/api/scale-log",
        data=json.dumps({"scale": "C_major", "position": 2, "bpm": 80, "reps": 4, "key": "C"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    j = resp.get_json()
    assert j["ok"] is True
    row = mem_conn.execute("SELECT * FROM scale_practice_log").fetchone()
    assert row is not None
    assert row["position"] == 2
    assert row["bpm"] == 80
    assert row["reps"] == 4
    assert row["key"] == "C"


def test_scale_log_g_major_insert(client, mem_conn) -> None:
    """POST /api/scale-log with key='G' must insert a row with key='G'."""
    resp = client.post(
        "/api/scale-log",
        data=json.dumps({"scale": "G_major", "position": 3, "bpm": 100, "reps": 2, "key": "G"}),
        content_type="application/json",
    )
    assert resp.get_json()["ok"] is True
    row = mem_conn.execute("SELECT * FROM scale_practice_log").fetchone()
    assert row["key"] == "G"
    assert row["position"] == 3


def test_scale_log_invalid_key(client) -> None:
    """POST /api/scale-log with unknown key must be rejected."""
    resp = client.post(
        "/api/scale-log",
        data=json.dumps({"scale": "X_major", "position": 1, "bpm": 60, "reps": 1, "key": "X"}),
        content_type="application/json",
    )
    j = resp.get_json()
    assert j["ok"] is False


def test_scale_log_invalid_position_zero(client) -> None:
    """Position 0 must be rejected."""
    resp = client.post(
        "/api/scale-log",
        data=json.dumps({"scale": "C_major", "position": 0, "bpm": 60, "reps": 1, "key": "C"}),
        content_type="application/json",
    )
    j = resp.get_json()
    assert j["ok"] is False


def test_scale_log_invalid_position_thirteen(client) -> None:
    """Position 13 must be rejected (max is 12 for C, 11 for G)."""
    resp = client.post(
        "/api/scale-log",
        data=json.dumps({"scale": "C_major", "position": 13, "bpm": 60, "reps": 1, "key": "C"}),
        content_type="application/json",
    )
    j = resp.get_json()
    assert j["ok"] is False


def test_scale_log_invalid_bpm_low(client) -> None:
    """BPM below 40 must be rejected."""
    resp = client.post(
        "/api/scale-log",
        data=json.dumps({"scale": "C_major", "position": 1, "bpm": 10, "reps": 1, "key": "C"}),
        content_type="application/json",
    )
    j = resp.get_json()
    assert j["ok"] is False


def test_scale_log_invalid_bpm_high(client) -> None:
    """BPM above 200 must be rejected."""
    resp = client.post(
        "/api/scale-log",
        data=json.dumps({"scale": "C_major", "position": 1, "bpm": 300, "reps": 1, "key": "C"}),
        content_type="application/json",
    )
    j = resp.get_json()
    assert j["ok"] is False


# ---------------------------------------------------------------------------
# /api/scale-log GET
# ---------------------------------------------------------------------------

def test_scale_log_get_returns_list(client, mem_conn) -> None:
    """GET /api/scale-log must return a list (empty or populated)."""
    resp = client.get("/api/scale-log")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)


# ---------------------------------------------------------------------------
# /api/instructor-audio — graceful degradation
# ---------------------------------------------------------------------------

def test_instructor_audio_204_when_no_key(client) -> None:
    """GET /api/instructor-audio?position=1 must return 204 when no API key is set."""
    import os
    env_backup = os.environ.pop("ELEVENLABS_API_KEY", None)
    try:
        resp = client.get("/api/instructor-audio?position=1")
        assert resp.status_code == 204
    finally:
        if env_backup is not None:
            os.environ["ELEVENLABS_API_KEY"] = env_backup


def test_instructor_audio_400_invalid_position(client) -> None:
    """Invalid position must return 400 (max 12 for C, 11 for G)."""
    resp = client.get("/api/instructor-audio?position=13")
    assert resp.status_code == 400


def test_instructor_audio_400_invalid_key(client) -> None:
    """Unknown key must return 400."""
    resp = client.get("/api/instructor-audio?position=1&key=X")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# HTML structure — tab nav and scales panel
# ---------------------------------------------------------------------------

@pytest.fixture
def html(client) -> str:
    resp = client.get("/")
    assert resp.status_code == 200
    return resp.data.decode("utf-8")


def test_html_has_tab_nav(html: str) -> None:
    """Rendered HTML must contain the tab navigation."""
    assert 'id="tab-nav"' in html


def test_html_has_exercises_tab_btn(html: str) -> None:
    """Exercises tab button must be present and active by default."""
    assert 'id="tab-btn-exercises"' in html
    assert "active" in html  # default active class


def test_html_has_scales_tab_btn(html: str) -> None:
    """Scales tab button must be present."""
    assert 'id="tab-btn-scales"' in html


def test_html_has_fretboard_svg(html: str) -> None:
    """Rendered HTML must contain the fretboard SVG element."""
    assert 'id="fretboard-svg"' in html


def test_html_has_scale_key_select(html: str) -> None:
    """Rendered HTML must contain the scale key dropdown."""
    assert 'id="scale-key"' in html


def test_html_key_select_has_b_option(html: str) -> None:
    """HTML key dropdown must include a B major option."""
    assert 'value="B"' in html


def test_html_key_select_has_eb_option(html: str) -> None:
    """HTML key dropdown must include an Eb/D# major option."""
    assert 'value="Eb"' in html


def test_html_key_pc_map_has_eb(html: str) -> None:
    """KEY_PC JavaScript map must have an Eb entry (pitch class 3) for correct root coloring."""
    assert "Eb:3" in html


def test_html_key_pc_map_has_dsharp(html: str) -> None:
    """KEY_PC JavaScript map must have a D# entry (pitch class 3) for correct root coloring."""
    assert "'D#':3" in html

def test_html_key_pc_map_has_e(html: str) -> None:
    """KEY_SIGS JavaScript map must have an E entry (4 sharps) for correct staff key signatures."""
    assert "E: 4" in html


def test_html_has_scale_position_select(html: str) -> None:
    """Rendered HTML must contain the scale position dropdown."""
    assert 'id="scale-position"' in html


def test_html_has_instructor_phrase_div(html: str) -> None:
    """Rendered HTML must contain the instructor phrase display."""
    assert 'id="instructor-phrase"' in html


def test_html_has_scale_bpm_input(html: str) -> None:
    """Rendered HTML must contain the scale BPM input."""
    assert 'id="scale-bpm"' in html


def test_html_has_scale_play_btn(html: str) -> None:
    """Rendered HTML must contain the scale play/stop button."""
    assert 'id="scale-play-btn"' in html


def test_html_has_tap_tempo_btn(html: str) -> None:
    """Rendered HTML must contain scaleTap() tap-tempo button."""
    assert "scaleTap()" in html


# ---------------------------------------------------------------------------
# A major — FR-20260531-guitar-trainer-a-major
# ---------------------------------------------------------------------------

def test_a_major_positions_pitch_classes() -> None:
    """All notes in all A major positions must belong to the A major scale (pitch classes {9,11,1,2,4,6,8})."""
    A_MAJOR_PC = {9, 11, 1, 2, 4, 6, 8}  # A B C# D E F# G#
    for i, pos in enumerate(SCALE_POSITIONS["A"]):
        for note in pos["notes"]:
            assert note["midi"] % 12 in A_MAJOR_PC, (
                f"A major pos {i+1} has invalid pitch class {note['midi'] % 12} (fret {note['fret']})"
            )


def test_a_major_max_fret() -> None:
    """No note in any A major position may exceed fret 22."""
    for i, pos in enumerate(SCALE_POSITIONS["A"]):
        for note in pos["notes"]:
            assert note["fret"] <= 22, (
                f"A major pos {i+1} has fret {note['fret']} > 22"
            )


def test_api_scale_positions_a_returns_11(client) -> None:
    """GET /api/scale-positions?key=A must return a list of exactly 11 A major positions."""
    resp = client.get("/api/scale-positions?key=A")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) == 11
    assert all("A major" in p["instructor_phrase"] for p in data)

def test_api_scale_positions_e_returns_11(client) -> None:
    """GET /api/scale-positions?key=E must return a list of exactly 11 E major positions."""
    resp = client.get("/api/scale-positions?key=E")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) == 11
    assert all("E major" in p["instructor_phrase"] for p in data)


def test_html_key_select_has_a_option(html: str) -> None:
    """HTML key dropdown must include an A major option."""
    assert '<option value="A">A major</option>' in html

def test_html_key_select_has_e_option(html: str) -> None:
    """HTML key dropdown must include an E major option."""
    assert '<option value="E">E major</option>' in html


def test_html_sharp_treble_y_positions_for_key_signature(html: str) -> None:
    """Treble clef sharp key signature positions must use the correct staff Y coordinates."""
    compact = html.replace(" ", "")
    assert "constSHARP_TREBLE_Y=[30,45,60,40,55,35,50]" in compact


# ---------------------------------------------------------------------------
# TTS normalization — hash→sharp bugfix
# ---------------------------------------------------------------------------

def test_tts_normalize_hash_to_sharp() -> None:
    """_normalize_phrase must replace # with ' sharp' so TTS says 'sharp' not 'hash'."""
    from training.scale_tts import _normalize_phrase  # noqa: PLC0415

    assert _normalize_phrase("A major A shape (F#, C#, G#).") == \
        "Ay major Ay shape (F sharp, C sharp, G sharp)."


def test_tts_normalize_a_major_pronunciation() -> None:
    """_normalize_phrase must replace 'A major' with 'Ay major' for hard A pronunciation."""
    from training.scale_tts import _normalize_phrase  # noqa: PLC0415

    assert _normalize_phrase("Start on the open A string — A major A shape.") == \
        "Start on the open A string — Ay major Ay shape."


def test_tts_normalize_a_shape_pronunciation() -> None:
    """_normalize_phrase must replace 'A shape' with 'Ay shape' for hard A pronunciation."""
    from training.scale_tts import _normalize_phrase  # noqa: PLC0415

    assert _normalize_phrase("A major A shape one octave up.") == \
        "Ay major Ay shape one octave up."


def test_tts_normalize_no_sharps_unchanged() -> None:
    """_normalize_phrase must leave phrases without # unmodified."""
    from training.scale_tts import _normalize_phrase  # noqa: PLC0415

    phrase = "Start on the 3rd fret of the A string — C major C shape."
    assert _normalize_phrase(phrase) == phrase


def test_html_freq_table_injected(html: str) -> None:
    """Rendered HTML must contain the MIDI frequency table (440 Hz for A4)."""
    assert "440" in html


# ---------------------------------------------------------------------------
# FR-20260525-fretboard-interval-colors — visual enhancement tests
# ---------------------------------------------------------------------------

def test_fretboard_svg_viewbox_height_220(html: str) -> None:
    """Fretboard SVG viewBox must be 1320x240 (50% taller than original 160px CSS height)."""
    assert 'viewBox="0 0 1320 240"' in html


def test_fretboard_interval_colors_present(html: str) -> None:
    """Rendered HTML must contain root, 3rd, and 5th interval color definitions."""
    assert "#ff0080" in html   # root = vivid electric pink
    assert "#fb5607" in html   # 3rd = vivid red-orange
    assert "#00e5cc" in html   # 5th = hot teal


def test_fretboard_pc_names_present(html: str) -> None:
    """Rendered HTML must contain the PC_NAMES pitch-class name array."""
    assert "PC_NAMES" in html


def test_fretboard_standard_fret_markers(html: str) -> None:
    """Rendered HTML must reference standard guitar fret marker positions (3,5,7,9,12)."""
    assert "FRET_MARKERS" in html
    # Standard positions must all appear; non-standard 6 and 18 must not drive the display
    assert "3, 5, 7, 9, 12" in html or "3,5,7,9,12" in html


def test_fretboard_note_labels_logic(html: str) -> None:
    """Rendered HTML must contain per-dot note-name text rendering."""
    assert "noteName" in html
    assert "noteNames[pc]" in html


# ---------------------------------------------------------------------------
# FR-20260530-guitar-trainer-staff-notation — Staff SVG tests
# ---------------------------------------------------------------------------

def test_staff_svgs_present_before_fretboard(html: str) -> None:
    """staff-treble-svg and staff-bass-svg must appear before fretboard-svg in HTML."""
    assert 'id="staff-treble-svg"' in html, "staff-treble-svg must be present in HTML"
    assert 'id="staff-bass-svg"' in html, "staff-bass-svg must be present in HTML"
    treble_idx = html.index('id="staff-treble-svg"')
    bass_idx = html.index('id="staff-bass-svg"')
    fretboard_idx = html.index('id="fretboard-svg"')
    assert treble_idx < fretboard_idx, "staff-treble-svg must appear before fretboard-svg"
    assert bass_idx < fretboard_idx, "staff-bass-svg must appear before fretboard-svg"


def test_staff_svgs_below_key_dropdown(html: str) -> None:
    """Staff SVGs must appear after the scale-key and scale-position dropdowns in HTML."""
    key_dropdown_idx = html.index('id="scale-key"')
    treble_idx = html.index('id="staff-treble-svg"')
    bass_idx = html.index('id="staff-bass-svg"')
    assert key_dropdown_idx < treble_idx, "staff-treble-svg must appear after scale-key dropdown"
    assert key_dropdown_idx < bass_idx, "staff-bass-svg must appear after scale-key dropdown"


def test_no_external_notation_libraries(html: str) -> None:
    """HTML must not reference vexflow, abcjs, or cdn.jsdelivr — pure inline SVG only."""
    assert "vexflow" not in html.lower()
    assert "abcjs" not in html.lower()
    assert "cdn.jsdelivr" not in html.lower()


def test_staff_js_generates_eight_note_circles(html: str) -> None:
    """JS must use 8-interval major scale array and data-staff attribute for note circles."""
    assert "MAJOR_INTERVALS" in html, "MAJOR_INTERVALS constant must be defined in JS"
    # Remove whitespace variants to match [0,2,4,5,7,9,11,12]
    html_compact = html.replace(" ", "").replace("\n", "")
    assert "[0,2,4,5,7,9,11,12]" in html_compact, \
        "MAJOR_INTERVALS must contain exactly the 8 diatonic intervals [0,2,4,5,7,9,11,12]"
    assert "data-staff=" in html, "note circles must have data-staff attribute"


def test_staff_keysig_attributes_present(html: str) -> None:
    """JS must render key signature elements with data-keysig attribute on both clefs."""
    assert "data-keysig=" in html, "key signature elements must use data-keysig attribute"


def test_staff_note_colors_other_matches_fretboard(html: str) -> None:
    """Staff note circles must use #555555 for non-root/3rd/5th degrees, matching fretboard gray."""
    assert "#555555" in html.lower(), \
        "Staff must define #555555 as the color for non-root/3rd/5th interval degrees (matches fretboard)"


def test_on_key_change_calls_draw_staves(html: str) -> None:
    """onKeyChange() JS function must call drawStaves to update staves when key changes."""
    assert "drawStaves" in html, "drawStaves function must be defined in JS"
    # Locate the onKeyChange function body (between window.onKeyChange and its closing };)
    fn_start = html.index("window.onKeyChange")
    fn_end = html.index("};", fn_start)
    fn_body = html[fn_start:fn_end]
    assert "drawStaves" in fn_body, "drawStaves must be called inside onKeyChange"


def test_playback_loop_calls_draw_staves(html: str) -> None:
    """The scale playback loop must call drawStaves alongside drawFretboard for staff sync."""
    playback_marker = "allAsc.indexOf(sequence[i])"
    assert playback_marker in html, "playback loop marker not found in HTML"
    loop_idx = html.index(playback_marker)
    # drawStaves must be within 400 chars of the drawFretboard call inside the loop
    window = html[max(0, loop_idx - 400):loop_idx + 400]
    assert "drawStaves" in window, \
        "drawStaves must be called inside the playback loop near drawFretboard"


def test_staff_container_flex_layout(html: str) -> None:
    """Staff container must use display:flex and flex-wrap:wrap for responsive layout."""
    assert 'id="staff-container"' in html, "staff-container div must be present"
    container_idx = html.index('id="staff-container"')
    # Check the surrounding HTML for the flex styles (within the opening tag)
    window = html[max(0, container_idx - 10):container_idx + 300]
    compact = window.replace(" ", "").replace('"', "").replace("'", "")
    assert "display:flex" in compact, "staff-container must use display:flex"
    assert "flex-wrap:wrap" in compact, "staff-container must use flex-wrap:wrap"


def test_fretboard_old_wrong_fret_logic_removed(html: str) -> None:
    """Old fret number logic (f===1||f%3===0) must be gone."""
    assert "f === 1 || f % 3 === 0" not in html


def test_fretboard_dot_radius_increased(html: str) -> None:
    """Non-active dot radius must be 9 (was 7)."""
    # The radius assignment for non-active dots
    assert ": 9;" in html or "? 10 : 9" in html
