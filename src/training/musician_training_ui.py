"""
❤Music — Focused Musician Training UI
Flask web interface for managing and launching lead guitar training sessions.
Exercise cards + practice log stored in heartmusic.db (guitar_exercises, guitar_training_log tables).
Scales & Arpeggios tab added in FR-20260517-guitar-trainer-scale-exercises.
"""

import argparse
import json
import os
import re
import subprocess  # nosec B404
import sys
from pathlib import Path
from flask import Flask, jsonify, render_template_string, request, Response, abort, send_from_directory

# Ensure src/ on path so utils.init_db is importable when run directly
_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
from utils.init_db import get_connection  # noqa: E402
from training.practice_stats import get_practice_stats  # noqa: E402
from training.scale_data import (  # noqa: E402
    SCALE_POSITIONS, CAGED_POSITIONS, MIDI_TO_FREQ, get_scale_sequence,
    PENTATONIC_POSITIONS, _MINOR_PENTA_POSITIONS, BOX_PENTA_POSITIONS,
)

# FR-20260806: CAGED-derived pentatonic shapes are deferred until design is settled.
# Flip to True to re-enable the CAGED optgroup in the position dropdown.
PENTA_CAGED_ENABLED: bool = False
from training.scale_tts import get_instructor_audio  # noqa: E402
from training.mode_spec import (  # noqa: E402
    MODE_SPEC,
    DEGREE_COLORS,
    DEGREE_TEXT,
    DEGREE_STROKE,
    build_mode_phrase as buildModePhrase,
)
from training.pentatonic_spec import (  # noqa: E402
    PENTATONIC_SPEC,
    PENTATONIC_DEGREE_COLORS,
    PENTATONIC_DEGREE_TEXT,
    PENTATONIC_DEGREE_STROKE,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Keep TRAINING_DIR for the ephemeral _run_*.json temp files used by focused_musician_training.py
TRAINING_DIR = PROJECT_ROOT / "tools" / "tyJson" / "exercises" / "musicTraining"
CLICK_DIR = PROJECT_ROOT / "click"
TTS_CACHE_DIR = PROJECT_ROOT / "output" / "tts" / "scale_instructor"
TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
PYTHON_EXE = r"C:\G\python.exe"
TRAINING_SCRIPT = PROJECT_ROOT / "tools" / "focused_musician_training.py"

MUZIC_DIR = Path(r"G:\Muzic")
AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".flac"}

# Security: allowed roots for album-art path requests.
# Any resolved path that does not start with one of these is rejected (403).
_ART_ALLOWED_ROOTS: tuple[Path, ...] = (
    MUZIC_DIR.resolve(),
    PROJECT_ROOT.resolve(),
)

def _scan_muzic() -> list[dict]:
    """Return all audio files under G:\\Muzic as {name, path} sorted by name."""
    if not MUZIC_DIR.exists():
        return []
    results = []
    for f in sorted(MUZIC_DIR.rglob("*")):
        if f.is_file() and f.suffix.lower() in AUDIO_EXTS:
            results.append({"name": f.name, "path": str(f)})
    return results


app = Flask(__name__)


def _flag_enabled(env_var: str) -> bool:
    """Read a boolean feature-flag env var; defaults to enabled when unset."""
    return os.environ.get(env_var, "true").lower() != "false"


# FR-20260808: cloud (Fly.io) deploys can disable the exercise-card workflow
# and/or the scale practice log via env vars — routes are structurally
# removed from app.url_map (not just hidden), see registration block below.
ENABLE_EXERCISE_CARDS: bool = _flag_enabled("ENABLE_EXERCISE_CARDS")
ENABLE_SCALE_LOG: bool = _flag_enabled("ENABLE_SCALE_LOG")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _list_sessions() -> list[dict]:
    """Return all exercise cards from guitar_exercises table."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, title, artist, song_path, segments, gradient FROM guitar_exercises ORDER BY id"
    ).fetchall()
    conn.close()
    sessions = []
    for r in rows:
        try:
            segs = json.loads(r["segments"] or "[]")
        except Exception:
            segs = []
        sessions.append({
            "id": r["id"],
            "title": r["title"],
            "artist": r["artist"] or "",
            "song_path": r["song_path"] or "",
            "gradient": r["gradient"] or 0,
            "segment_count": len(segs),
            "segments": segs,
        })
    return sessions


def _load_log() -> list[dict]:
    """Return practice log entries as dicts (newest-first)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT song_path, seg_start, seg_end, repetition, logged_at "
        "FROM guitar_training_log ORDER BY id DESC LIMIT 200"
    ).fetchall()
    conn.close()
    return [
        {
            "timestamp": r["logged_at"],
            "songPath": r["song_path"],
            "segment": {
                "start": r["seg_start"],
                "end": r["seg_end"],
                "repetition": r["repetition"],
            },
        }
        for r in rows
    ]


def _append_log(
    exercise_id: int | None,
    song_path: str,
    seg_start: str,
    seg_end: str,
    repetition: int,
    duration_minutes: int = 0,
    key: str | None = None,
    position: int | None = None,
    exercise_name: str | None = None,
) -> None:
    """Append a practice log entry to guitar_training_log."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO guitar_training_log "
        "(exercise_id, song_path, seg_start, seg_end, repetition, duration_minutes, key, position, exercise_name) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (exercise_id, song_path, seg_start, seg_end, repetition, duration_minutes, key, position, exercise_name),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

HTML = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>🎸 Lead Guitar Trainer</title>
<style>
  :root{--bg:#0d0d0d;--card:#1a1a1a;--accent:#e8003d;--muted:#888;--text:#eee;--border:#333}
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--text);font-family:'Segoe UI',sans-serif;padding:24px}
  h1{color:var(--accent);font-size:1.6rem;margin-bottom:4px}
  .sub{color:var(--muted);font-size:.85rem;margin-bottom:24px}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px}
  .card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px;position:relative}
  .card-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px}
  .card-header .meta h2{font-size:1rem;color:#fff;margin-bottom:2px}
  .card-header .meta .artist{font-size:.8rem;color:var(--muted)}
  .album-art{width:200px;height:200px;object-fit:cover;border-radius:4px;display:block;margin-bottom:10px}
  .card-controls{display:flex;align-items:center;gap:6px;flex-shrink:0}
  .lock-label{font-size:.7rem;color:var(--muted);cursor:pointer;user-select:none;display:flex;align-items:center;gap:3px}
  .lock-label input{cursor:pointer}
  .btn-del-card{background:transparent;border:none;color:#444;cursor:pointer;font-size:1rem;padding:2px 4px;line-height:1;transition:color .15s}
  .btn-del-card.unlocked{color:#e8003d}
  .btn-del-card:not(.unlocked){pointer-events:none;opacity:.25}
  table{width:100%;border-collapse:collapse;font-size:.8rem;margin-bottom:12px}
  th{color:var(--muted);text-align:left;padding:4px 6px;border-bottom:1px solid var(--border)}
  td{padding:4px 6px;border-bottom:1px solid #222}
  td input{background:#111;border:1px solid var(--border);color:#fff;padding:2px 4px;width:100%;border-radius:3px}
  .btn-del{background:transparent;border:none;color:#555;cursor:pointer;font-size:.9rem;padding:0 4px;line-height:1}
  .btn-del:hover{color:#e8003d}
  .btn{display:inline-block;padding:7px 16px;border-radius:5px;border:none;cursor:pointer;font-size:.85rem;font-weight:600}
  .btn-red{background:var(--accent);color:#fff}
  .btn-ghost{background:transparent;border:1px solid var(--border);color:#ccc}
  .btn-ghost:hover{border-color:var(--accent);color:var(--accent)}
  .btn-add{background:#1e3a1e;color:#6fdc6f;border:1px solid #3a6a3a}
  .actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
  .log-section{margin-top:32px}
  .log-section summary{cursor:pointer;color:var(--accent);font-weight:600;font-size:1rem;padding:6px 0;list-style:none;user-select:none}
  .log-section summary::-webkit-details-marker{display:none}
  .log-section summary::before{content:'▶  ';font-size:.7rem;margin-right:2px}
  .log-section details[open] summary::before{content:'▼  '}
  .log-scroll{max-height:320px;overflow-y:auto;margin-top:8px;padding-right:4px}
  .log-entry{font-size:.8rem;color:#aaa;padding:6px 0;border-bottom:1px solid #222}
  .log-entry span{color:#fff}
  .new-card{border:1px dashed var(--border)}
  .new-card input{width:100%;background:#111;border:1px solid var(--border);color:#fff;padding:6px 8px;border-radius:4px;margin-bottom:8px;font-size:.85rem}
  .tag{display:inline-block;background:#222;border-radius:3px;padding:1px 6px;font-size:.75rem;color:var(--muted);margin-right:4px}
  .status{font-size:.75rem;color:#6fdc6f;margin-top:4px;min-height:16px}
  .catalog-item{padding:6px 10px;font-size:.8rem;cursor:pointer;color:#ccc;border-bottom:1px solid #222}
  .catalog-item:hover{background:#2a2a2a;color:#fff}
  /* Metronome */
  .metronome{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:14px 16px;margin-bottom:24px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
  .metro-title{font-size:.8rem;font-weight:700;color:var(--accent);letter-spacing:.05em;text-transform:uppercase;white-space:nowrap}
  .metro-bpm-wrap{display:flex;align-items:center;gap:6px}
  .metro-bpm{font-size:1.4rem;font-weight:700;color:#fff;width:60px;background:#111;border:1px solid var(--border);border-radius:4px;text-align:center;padding:2px 0}
  .metro-bpm::-webkit-inner-spin-button{display:none}
  .metro-label{font-size:.7rem;color:var(--muted)}
  .metro-tap{padding:5px 12px;background:#111;border:1px solid var(--border);color:#ccc;border-radius:4px;cursor:pointer;font-size:.8rem;font-weight:600}
  .metro-tap:active{background:#2a2a2a}
  .metro-sig{padding:5px 10px;background:#111;border:1px solid var(--border);color:#ccc;border-radius:4px;font-size:.8rem;cursor:pointer}
  .metro-play{padding:6px 20px;background:var(--accent);color:#fff;border:none;border-radius:4px;font-size:.9rem;font-weight:700;cursor:pointer;min-width:64px}
  .metro-play:hover{filter:brightness(1.15)}
  .metro-beat-row{display:flex;gap:5px;align-items:center}
  .metro-dot{width:10px;height:10px;border-radius:50%;background:#333;transition:background .07s}
  .metro-dot.active-accent{background:#e8003d;box-shadow:0 0 6px #e8003d}
  .metro-dot.active-beat{background:#6fdc6f;box-shadow:0 0 4px #6fdc6f}
  /* Scales tab (FR-20260517-guitar-trainer-scale-exercises) */
  .tab-nav{display:flex;gap:8px;margin-bottom:20px}
  .tab-btn{padding:8px 22px;border:1px solid var(--border);background:#111;color:var(--muted);border-radius:5px;cursor:pointer;font-weight:600;font-size:.9rem;transition:background .15s,color .15s}
  .tab-btn.active{background:var(--accent);color:#fff;border-color:var(--accent)}
  .tab-panel{}
  .scales-header{margin-bottom:18px}
  .scales-header h2{color:var(--accent);font-size:1.2rem;margin-bottom:4px}
  .scales-header .sub{color:var(--muted);font-size:.82rem}
  .scale-row{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:14px}
  .scale-row label{font-size:.8rem;color:var(--muted);display:flex;align-items:center;gap:6px}
  .scale-legend{display:flex;gap:14px;align-items:center;margin-left:8px;padding:5px 12px;background:rgba(255,255,255,.04);border:1px solid var(--border);border-radius:20px}
  .legend-item{display:flex;align-items:center;gap:5px;font-size:.78rem;color:#ccc;white-space:nowrap}
  .scale-select{background:#111;border:1px solid var(--border);color:#fff;padding:6px 10px;border-radius:4px;font-size:.85rem;min-width:260px}
  .instructor-box{padding:10px 14px;background:var(--card);border:1px solid var(--border);border-radius:6px;color:#fff;font-size:.88rem;margin-bottom:14px;min-height:38px;line-height:1.5}
  #fretboard-svg{width:100%;max-width:1320px;height:240px;display:block;margin:0 0 16px 0;background:#111;border:1px solid var(--border);border-radius:6px}
  .scale-controls{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:14px}
  .scale-ctrl-label{font-size:.75rem;color:var(--muted);display:flex;align-items:center;gap:5px}
  .scale-ctrl-input{background:#111;border:1px solid var(--border);color:#fff;padding:4px 6px;border-radius:4px;font-size:.9rem;width:64px;text-align:center}
  .scale-ctrl-input::-webkit-inner-spin-button{display:none}
  .btn-scale-tap{padding:5px 12px;background:#111;border:1px solid var(--border);color:#ccc;border-radius:4px;cursor:pointer;font-size:.8rem;font-weight:600}
  .btn-scale-tap:active{background:#2a2a2a}
  .btn-scale-play{padding:8px 28px;background:var(--accent);color:#fff;border:none;border-radius:5px;font-size:1rem;font-weight:700;cursor:pointer;min-width:80px}
  .btn-scale-play:disabled{opacity:.4;cursor:default}
  .scale-status{font-size:.8rem;color:#6fdc6f;min-height:18px;margin-bottom:10px}
  .scale-log-table{width:100%;border-collapse:collapse;font-size:.78rem;margin-top:8px}
  .scale-log-table th{color:var(--muted);text-align:left;padding:4px 8px;border-bottom:1px solid var(--border)}
  .scale-log-table td{padding:4px 8px;border-bottom:1px solid #222;color:#aaa}
  /* Pentatonic family pill toggle (FR-20260806) */
  .family-btn{padding:6px 13px;background:#111;color:#ccc;border:none;cursor:pointer;font-size:.8rem;font-weight:600;transition:background .12s,color .12s}
  .family-btn:first-child{border-right:1px solid var(--border)}
  .family-btn-active{background:var(--accent);color:#fff}</style>
</style>
</head>
<body>
<div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px">
  <div>
    <h1>🎸 Lead Guitar Trainer</h1>
    <p class="sub">Focused interval training — loop lead parts, control speed, build muscle memory</p>
  </div>
  {% if enable_scale_log %}
  <div class="streak-badge" style="background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.15);border-radius:10px;padding:10px 16px;font-size:0.85rem;text-align:center;min-width:160px;flex-shrink:0">
    <div style="font-size:1.4rem;font-weight:700;">🔥 {{ stats.streak_days }} day{{ 's' if stats.streak_days != 1 else '' }}</div>
    <div style="opacity:0.7;margin-top:2px;">{{ stats.week_minutes }} min this week</div>
    <div style="opacity:0.5;margin-top:2px;font-size:0.75rem;">Last: {{ stats.last_practiced or 'never' }}</div>
  </div>
  {% endif %}
</div>

<!-- Tab navigation (FR-20260517-guitar-trainer-scale-exercises) -->
<div class="tab-nav" id="tab-nav">
  {% if enable_exercise_cards %}<button class="tab-btn active" id="tab-btn-exercises" onclick="switchTab('exercises')">🎸 Exercises</button>{% endif %}
  <button class="tab-btn{% if not enable_exercise_cards %} active{% endif %}" id="tab-btn-scales" onclick="switchTab('scales')">🎵 Scales</button>
</div>

{% if enable_exercise_cards %}
<div id="tab-exercises" class="tab-panel">
<!-- Metronome (FR-20260425-guitar-trainer-metronome) -->
<div class="metronome" id="metro-panel">
  <span class="metro-title">🥁 Metro</span>
  <div class="metro-bpm-wrap">
    <input class="metro-bpm" id="metro-bpm" type="number" value="120" min="20" max="300" oninput="metroBpmChange(this.value)">
    <span class="metro-label">BPM</span>
  </div>
  <button class="metro-tap" onclick="metroTap()">Tap</button>
  <select class="metro-sig" id="metro-sig" onchange="metroSigChange(this.value)">
    <option value="4">4/4</option>
    <option value="3">3/4</option>
    <option value="6">6/8</option>
  </select>
  <div class="metro-beat-row" id="metro-beat-row">
    <span class="metro-dot" id="mdot-0"></span>
    <span class="metro-dot" id="mdot-1"></span>
    <span class="metro-dot" id="mdot-2"></span>
    <span class="metro-dot" id="mdot-3"></span>
  </div>
  <button class="metro-play" id="metro-play-btn" onclick="metroToggle()">▶</button>
</div>

<div class="grid" id="sessions-grid">
  {% for s in sessions %}
  <div class="card" id="card-{{ s.id }}">
    {% if s.song_path %}
    <img class="album-art" src="/art?path={{ s.song_path | urlencode }}" onerror="this.style.display='none'" alt="">
    {% endif %}
    <div class="card-header">
      <div class="meta"><h2>{{ s.title }}</h2><div class="artist">{{ s.artist }}</div></div>
      <div class="card-controls">
        <label class="lock-label" title="Unlock to delete this exercise">
          <input type="checkbox" onchange="toggleCardLock({{ s.id }},this)"> 🔒
        </label>
        <button class="btn-del-card" id="del-card-{{ s.id }}" onclick="deleteCard({{ s.id }})" title="Delete exercise">🗑</button>
      </div>
    </div>
    <table>
      <thead><tr><th>Start</th><th>End</th><th>Speed%</th><th>Reps</th><th></th></tr></thead>
      <tbody id="tbody-{{ s.id }}">
      {% for seg in s.segments %}
        <tr>
          <td><input value="{{ seg.start }}" data-field="start" style="width:70px" oninput="scheduleAutosave({{ s.id }})"></td>
          <td><input value="{{ seg.end }}" data-field="end" style="width:70px" oninput="scheduleAutosave({{ s.id }})"></td>
          <td><input type="number" value="{{ seg.get('speed',100) }}" data-field="speed" style="width:60px" min="10" max="200" oninput="scheduleAutosave({{ s.id }})"></td>
          <td><input type="number" value="{{ seg.get('repetition',1) }}" data-field="repetition" style="width:50px" min="0" oninput="scheduleAutosave({{ s.id }})"></td>
          <td><button class="btn-del" onclick="deleteRow(this,{{ s.id }})" title="Delete row">&times;</button></td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
    <div class="actions" style="align-items:center">
      <button class="btn btn-add" onclick="addRow({{ s.id }})">+ Row</button>
      <label style="font-size:.75rem;color:var(--muted);display:flex;align-items:center;gap:4px">
        Gradient
        <input type="number" id="gradient-{{ s.id }}" value="{{ s.gradient }}"
               style="width:52px;background:#111;border:1px solid var(--border);color:#fff;padding:2px 4px;border-radius:3px;font-size:.8rem"
               min="0" max="50" step="1"
               oninput="scheduleAutosave({{ s.id }})">
      </label>
      <button class="btn btn-red" onclick="launchSession({{ s.id }})">&#9654; Launch</button>
    </div>
    <div class="status" id="status-{{ s.id }}"></div>
  </div>
  {% endfor %}

  <!-- New session card -->
  <div class="card new-card">
    <h2 style="margin-bottom:12px">➕ New Training File</h2>
    <div style="position:relative;margin-bottom:8px">
      <input id="new-path" placeholder="🔍 Search songs…" oninput="filterCatalog(this.value)" onfocus="showCatalog()" autocomplete="off" style="width:100%">
      <div id="catalog-dropdown" style="display:none;position:absolute;top:100%;left:0;right:0;background:#1a1a1a;border:1px solid var(--border);border-radius:0 0 5px 5px;max-height:220px;overflow-y:auto;z-index:100">
        <div id="catalog-list"></div>
      </div>
    </div>
    <div id="new-selected" style="display:none;font-size:.8rem;color:#aaa;margin-bottom:8px;padding:6px 8px;background:#111;border-radius:4px;border:1px solid var(--border)">
      <span id="new-selected-text"></span>
    </div>
    <button class="btn btn-ghost" onclick="createSession()" style="width:100%">Create Exercise Card</button>
    <div class="status" id="status-new"></div>
  </div>
</div>

<div class="log-section">
  <details>
    <summary>Practice Log{% if log %} <span style="font-weight:400;font-size:.8rem;color:var(--muted)">— {{ log|length }} session{{ 's' if log|length != 1 }}</span>{% endif %}</summary>
    {% if log %}
    <div class="log-scroll">
      {% for entry in log %}
      {% if loop.index <= 20 %}
      <div class="log-entry">
        <span>{{ entry.timestamp }}</span> —
        {{ entry.songPath|replace('G:\\Muzic\\','')|replace('G:/Muzic/','') }}&nbsp;
        <span class="tag">{{ entry.segment.start }}–{{ entry.segment.end }}</span>
        <span class="tag">×{{ entry.segment.repetition }}</span>
      </div>
      {% endif %}
      {% endfor %}
      {% if log|length > 20 %}
      <p style="font-size:.75rem;color:var(--muted);padding:6px 0">Showing 20 of {{ log|length }} entries</p>
      {% endif %}
    </div>
    {% else %}
    <p style="color:var(--muted);font-size:.85rem;margin-top:8px">No sessions logged yet.</p>
    {% endif %}
  </details>
</div><!-- /log-section -->
</div><!-- /tab-exercises -->
{% endif %}

<!-- Scales & Arpeggios tab panel (FR-20260517-guitar-trainer-scale-exercises) -->
<div id="tab-scales" class="tab-panel"{% if enable_exercise_cards %} style="display:none"{% endif %}>
  <div class="scales-header">
    <h2>🎵 Scales &amp; Arpeggios</h2>
  </div>

  <div class="scale-row">
    <label>Key
      <select id="scale-key" class="scale-select" onchange="onKeyChange()">
        <option value="C">C major / A minor</option>
        <option value="Db">Db major / Bb minor</option>
        <option value="D">D major / B minor</option>
        <option value="Eb">Eb major / C minor</option>
        <option value="E">E major / C# minor</option>
        <option value="F#">F# major / D# minor</option>
        <option value="F">F major / D minor</option>
        <option value="G">G major / E minor</option>
        <option value="A">A major / F# minor</option>
        <option value="Ab">Ab major / F minor</option>
        <option value="Bb">Bb major / G minor</option>
        <option value="B">B major / G# minor</option>
      </select>
    </label>
    <label style="gap:4px">Family</label>
    <div style="display:flex;gap:0;border:1px solid var(--border);border-radius:5px;overflow:hidden">
      <button id="family-btn-diatonic"       onclick="onFamilyChange('diatonic')"       class="family-btn family-btn-active">Diatonic</button>
      <button id="family-btn-major_penta"    onclick="onFamilyChange('major_penta')"    class="family-btn">Maj Penta</button>
      <button id="family-btn-minor_penta"    onclick="onFamilyChange('minor_penta')"    class="family-btn" style="border-left:1px solid var(--border)">Min Penta</button>
    </div>
    <label id="scale-mode-label">Mode
      <select id="scale-mode" class="scale-select" onchange="onModeChange()">
        <option value="Ionian">Ionian</option>
        <option value="Dorian">Dorian</option>
        <option value="Phrygian">Phrygian</option>
        <option value="Lydian">Lydian</option>
        <option value="Mixolydian">Mixolydian</option>
        <option value="Aeolian">Aeolian</option>
        <option value="Locrian">Locrian</option>
      </select>
    </label>
    <label>Position
      <select id="scale-position" class="scale-select" onchange="onPositionChange()"></select>
    </label>
    <span class="scale-legend" id="scale-legend">
      <span class="legend-item"><svg width="12" height="12"><circle cx="6" cy="6" r="5" fill="#ff0080"/></svg>Root</span>
      <span class="legend-item"><svg width="12" height="12"><circle cx="6" cy="6" r="5" fill="#fb5607"/></svg>3rd</span>
      <span class="legend-item"><svg width="12" height="12"><circle cx="6" cy="6" r="5" fill="#00e5cc"/></svg>5th</span>
    </span>
  </div>

  <div class="instructor-box" id="instructor-phrase" style="display:none"></div>
  <audio id="instructor-audio" style="display:none"></audio>

  <!-- Staff notation (FR-20260530-guitar-trainer-staff-notation) -->
  <div id="staff-container" style="display:flex;flex-wrap:wrap;gap:16px;margin-bottom:16px;justify-content:flex-start;max-width:1320px">
    <svg id="staff-treble-svg" viewBox="0 0 500 120" style="flex:1 1 0;min-width:280px;background:#111;border-radius:6px"></svg>
    <svg id="staff-bass-svg"   viewBox="0 0 500 120" style="flex:1 1 0;min-width:280px;background:#111;border-radius:6px"></svg>
  </div>

  <svg id="fretboard-svg" viewBox="0 0 1320 240" preserveAspectRatio="xMinYMid meet">
    <text x="460" y="88" fill="#555" text-anchor="middle" font-size="13" font-family="Segoe UI,sans-serif">Loading fretboard…</text>
  </svg>

  <div class="scale-controls">
    <label class="scale-ctrl-label">BPM
      <input id="scale-bpm" class="scale-ctrl-input" type="number" value="160" min="40" max="200" oninput="scaleSetBpm(this.value)">
    </label>
    <button class="btn-scale-tap" onclick="scaleTap()">Tap</button>
    <label class="scale-ctrl-label">Reps
      <input id="scale-reps" class="scale-ctrl-input" type="number" value="2" min="1" max="20">
    </label>
    <button class="btn-scale-play" id="scale-play-btn" onclick="scaleToggle()">▶ Play</button>
  </div>

  <div class="scale-status" id="scale-status"></div>

  {% if enable_scale_log %}
  <details style="margin-top:16px">
    <summary style="cursor:pointer;color:var(--accent);font-weight:600;font-size:.9rem;user-select:none">Scale Practice Log</summary>
    <div style="margin-top:8px" id="scale-log-wrap">
      <table class="scale-log-table">
        <thead><tr><th>Time</th><th>Key</th><th>Mode</th><th>Scale</th><th>Position</th><th>BPM</th><th>Reps</th></tr></thead>
        <tbody id="scale-log-tbody"><tr><td colspan="7" style="color:var(--muted)">No sessions yet.</td></tr></tbody>
      </table>
    </div>
  </details>
  {% endif %}
</div><!-- /tab-scales -->


<script>
const _saveTimers = {};

function getRows(tbodyId) {
  const rows = [];
  document.querySelectorAll(`#${tbodyId} tr`).forEach(tr => {
    const r = {};
    tr.querySelectorAll('input[data-field]').forEach(inp => r[inp.dataset.field] = inp.value);
    if (r.start) {
      const obj = { start: r.start, end: r.end, speed: parseInt(r.speed)||100, repetition: Math.max(0, parseInt(r.repetition)||0) };
      rows.push(obj);
    }
  });
  return rows;
}

function getGradient(id) {
  const el = document.getElementById('gradient-' + id);
  return el ? (parseInt(el.value) || 0) : 0;
}

function toggleCardLock(id, cb) {
  const btn = document.getElementById('del-card-' + id);
  if (cb.checked) { btn.classList.add('unlocked'); } else { btn.classList.remove('unlocked'); }
}

async function deleteCard(id) {
  const btn = document.getElementById('del-card-' + id);
  if (!btn.classList.contains('unlocked')) return;
  const res = await fetch('/delete', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ id }) });
  const j = await res.json();
  if (j.ok) {
    document.getElementById('card-' + id).remove();
  } else {
    alert('Delete failed: ' + j.error);
  }
}

function scheduleAutosave(id) {
  clearTimeout(_saveTimers[id]);
  setStatus(id, '...', true);
  _saveTimers[id] = setTimeout(() => saveSession(id), 600);
}

function addRow(id) {
  const tbody = document.getElementById('tbody-' + id);
  const tr = document.createElement('tr');
  tr.innerHTML = `<td><input value="0:00" data-field="start" style="width:70px" oninput="scheduleAutosave(${id})"></td><td><input value="0:10" data-field="end" style="width:70px" oninput="scheduleAutosave(${id})"></td><td><input type="number" value="80" data-field="speed" style="width:60px" min="10" max="200" oninput="scheduleAutosave(${id})"></td><td><input type="number" value="3" data-field="repetition" style="width:50px" min="0" oninput="scheduleAutosave(${id})"></td><td><button class="btn-del" onclick="deleteRow(this,${id})" title="Delete row">&times;</button></td>`;
  tbody.appendChild(tr);
  scheduleAutosave(id);
}

function deleteRow(btn, id) {
  btn.closest('tr').remove();
  saveSession(id);
}

function setStatus(id, msg, ok=true) {
  const el = document.getElementById('status-' + id);
  if (el) { el.textContent = msg; el.style.color = ok ? '#6fdc6f' : '#f55'; }
}

async function saveSession(id) {
  const segs = getRows('tbody-' + id);
  const gradient = getGradient(id);
  const res = await fetch('/save', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ id, segments: segs, gradient }) });
  const j = await res.json();
  setStatus(id, j.ok ? '\u2713 Saved' : '\u2717 ' + j.error, j.ok);
}

async function launchSession(id) {
  clearTimeout(_saveTimers[id]);
  setStatus(id, '\u23f3 Saving\u2026');
  await saveSession(id);
  setStatus(id, '\u23f3 Launching\u2026');
  const gradient = getGradient(id);
  const res = await fetch('/launch', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ id, gradient }) });
  const j = await res.json();
  setStatus(id, j.ok ? '\u25b6 Running in terminal' : '\u2717 ' + j.error, j.ok);
}


let _catalog = [];
let _selectedPath = '';
async function showCatalog() {
  if (!_catalog.length) {
    const r = await fetch('/catalog'); _catalog = await r.json();
  }
  renderCatalog(_catalog);
  document.getElementById('catalog-dropdown').style.display = 'block';
}
function filterCatalog(q) {
  const filtered = q ? _catalog.filter(f => f.name.toLowerCase().includes(q.toLowerCase())) : _catalog;
  renderCatalog(filtered);
  document.getElementById('catalog-dropdown').style.display = 'block';
}
function renderCatalog(files) {
  const list = document.getElementById('catalog-list');
  list.innerHTML = files.slice(0, 80).map(f =>
    `<div class="catalog-item" data-path="${f.path.replace(/"/g,'&quot;')}" data-name="${f.name.replace(/"/g,'&quot;')}">${f.name}</div>`
  ).join('') + (files.length > 80 ? `<div style="padding:6px 10px;font-size:.72rem;color:var(--muted)">${files.length - 80} more — type to filter</div>` : '');
}
// catalog-list only exists in the New Training File card, which is gated behind
// ENABLE_EXERCISE_CARDS (FR-20260808) -- null-guard so a disabled flag doesn't
// throw and halt every later top-level statement in this script tag.
const catalogListEl = document.getElementById('catalog-list');
if (catalogListEl) {
  catalogListEl.addEventListener('click', e => {
    const item = e.target.closest('.catalog-item');
    if (item) selectFile(item.dataset.path, item.dataset.name);
  });
}
function selectFile(path, name) {
  _selectedPath = path;
  document.getElementById('new-path').value = '';
  document.getElementById('catalog-dropdown').style.display = 'none';
  const bare = name.replace(/\.[^.]+$/, '');  // strip extension
  const parts = bare.split(' - ');
  const title = parts[0].trim();
  const artist = parts.length > 1 ? parts[parts.length - 1].trim() : '';
  document.getElementById('new-selected').style.display = 'block';
  document.getElementById('new-selected-text').textContent = title + (artist ? '  ·  ' + artist : '');
}
document.addEventListener('click', e => {
  if (!e.target.closest('.new-card')) {
    // catalog-dropdown is also gated behind ENABLE_EXERCISE_CARDS -- guard it too.
    const dropdownEl = document.getElementById('catalog-dropdown');
    if (dropdownEl) dropdownEl.style.display = 'none';
  }
});

function buildCardHTML(s) {
  const id = s.id;
  const artTag = s.song_path
    ? `<img class="album-art" src="/art?path=${encodeURIComponent(s.song_path)}" onerror="this.style.display='none'" alt="">`
    : '';
  const rows = (s.segments || []).map((seg) => `
    <tr>
      <td><input value="${seg.start}" data-field="start" style="width:70px" oninput="scheduleAutosave(${id})"></td>
      <td><input value="${seg.end}" data-field="end" style="width:70px" oninput="scheduleAutosave(${id})"></td>
      <td><input type="number" value="${seg.speed||100}" data-field="speed" style="width:60px" min="10" max="200" oninput="scheduleAutosave(${id})"></td>
      <td><input type="number" value="${seg.repetition||1}" data-field="repetition" style="width:50px" min="0" oninput="scheduleAutosave(${id})"></td>
      <td><button class="btn-del" onclick="deleteRow(this,${id})" title="Delete row">&times;</button></td>
    </tr>`).join('');
  return `<div class="card" id="card-${id}">
    ${artTag}
    <div class="card-header">
      <div class="meta"><h2>${s.title}</h2><div class="artist">${s.artist}</div></div>
      <div class="card-controls">
        <label class="lock-label" title="Unlock to delete this exercise">
          <input type="checkbox" onchange="toggleCardLock(${id},this)"> \uD83D\uDD12
        </label>
        <button class="btn-del-card" id="del-card-${id}" onclick="deleteCard(${id})" title="Delete exercise">\uD83D\uDDD1</button>
      </div>
    </div>
    <table>
      <thead><tr><th>Start</th><th>End</th><th>Speed%</th><th>Reps</th><th></th></tr></thead>
      <tbody id="tbody-${id}">${rows}</tbody>
    </table>
    <div class="actions" style="align-items:center">
      <button class="btn btn-add" onclick="addRow(${id})">+ Row</button>
      <label style="font-size:.75rem;color:var(--muted);display:flex;align-items:center;gap:4px">
        Gradient
        <input type="number" id="gradient-${id}" value="${s.gradient||0}" style="width:52px;background:#111;border:1px solid var(--border);color:#fff;padding:2px 4px;border-radius:3px;font-size:.8rem" min="0" max="50" step="1" oninput="scheduleAutosave(${id})">
      </label>
      <button class="btn btn-red" onclick="launchSession(${id})">&#9654; Launch</button>
    </div>
    <div class="status" id="status-${id}"></div>
  </div>`;
}

async function createSession() {
  if (!_selectedPath) { setStatus('new', '\u2717 Pick a song first', false); return; }
  const name = _selectedPath.split('\\').pop().split('/').pop();
  const bare = name.replace(/\.[^.]+$/, '');
  const parts = bare.split(' - ');
  const title = parts[0].trim();
  const artist = parts.length > 1 ? parts[parts.length - 1].trim() : '';
  const res = await fetch('/create', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ title, artist, songPath: _selectedPath }) });
  const j = await res.json();
  if (j.ok) {
    // Fetch the newly created session by id and inject without page reload
    const sessRes = await fetch('/api/sessions');
    const sessions = await sessRes.json();
    const newSession = sessions.find(s => s.id === j.id);
    if (newSession) {
      const grid = document.getElementById('sessions-grid');
      const newCard = grid.querySelector('.new-card');
      const div = document.createElement('div');
      div.innerHTML = buildCardHTML(newSession);
      grid.insertBefore(div.firstElementChild, newCard);
    }
    setStatus('new', '\u2713 Created');
    _selectedPath = '';
    document.getElementById('new-selected').style.display = 'none';
    document.getElementById('new-selected-text').textContent = '';
    document.getElementById('new-path').value = '';
  } else { setStatus('new', '\u2717 ' + j.error, false); }
}

// ---------------------------------------------------------------------------
// Metronome (FR-20260425-guitar-trainer-metronome)
// Uses Web Audio API scheduler for drift-free timing.
// first.wav = beat-1 accent; click.wav = all other beats.
// ---------------------------------------------------------------------------
(function initMetronome() {
  let audioCtx = null;
  let accentBuf = null;
  let clickBuf = null;
  let running = false;
  let schedulerHandle = null;
  let nextBeatTime = 0;
  let currentBeat = 0;
  let bpm = 120;
  let beatsPerBar = 4;
  let scheduledSources = [];
  let scheduledDotHandles = [];
  const LOOKAHEAD_MS = 25;
  const SCHEDULE_AHEAD_S = 0.1;

  // Tap-tempo state
  const tapTimes = [];
  const MAX_TAP_GAP_MS = 3000;

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function getCtx() {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    return audioCtx;
  }

  async function loadBuffer(url) {
    const ctx = getCtx();
    const resp = await fetch(url);
    if (!resp.ok) return null;
    const ab = await resp.arrayBuffer();
    return ctx.decodeAudioData(ab);
  }

  async function ensureBuffers() {
    if (!accentBuf) accentBuf = await loadBuffer('/click/first.wav');
    if (!clickBuf) clickBuf = await loadBuffer('/click/click.wav');
  }

  async function playCountIn(beats, countInBpm, shouldStop) {
    await ensureBuffers();
    const ctx = getCtx();
    if (ctx.state === 'suspended') await ctx.resume();
    const beatIntervalMs = Math.round(60000 / Math.max(20, Math.min(300, parseInt(countInBpm) || 120)));
    const beatIntervalSec = beatIntervalMs / 1000;
    const startTime = ctx.currentTime + 0.05;
    const status = document.getElementById('scale-status');
    const countInSources = [];
    const countInDotHandles = [];
    const cancelCountIn = () => {
      countInSources.forEach((src) => {
        try {
          src.stop();
        } catch (_e) {
          // ignore sources that are already stopped
        }
        const idx = scheduledSources.indexOf(src);
        if (idx !== -1) scheduledSources.splice(idx, 1);
      });
      countInSources.length = 0;
      countInDotHandles.forEach(clearTimeout);
      countInDotHandles.length = 0;
    };
    for (let beat = 0; beat < beats; beat++) {
      if (shouldStop && shouldStop()) {
        cancelCountIn();
        return false;
      }
      const beatTime = startTime + (beat * beatIntervalSec);
      const src = playBuf(beat === 0 ? accentBuf : clickBuf, beatTime);
      if (src) countInSources.push(src);
      const dotHandle = setTimeout(() => {
        if (shouldStop && shouldStop()) return;
        if (status) status.textContent = `Count-in ${beat + 1}/${beats}`;
        updateDots(beat);
      }, Math.max(0, (beatTime - ctx.currentTime) * 1000));
      countInDotHandles.push(dotHandle);
    }
    const endTime = performance.now() + (beats * beatIntervalMs) + 50;
    while (performance.now() < endTime) {
      if (shouldStop && shouldStop()) {
        cancelCountIn();
        return false;
      }
      await sleep(25);
    }
    countInDotHandles.length = 0;
    return !(shouldStop && shouldStop());
  }

  window.scaleCountIn = async function(beats, countInBpm, shouldStop) {
    return playCountIn(beats, countInBpm, shouldStop);
  };

  function playBuf(buf, time) {
    if (!buf) return null;
    const ctx = getCtx();
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    src.start(time);
    scheduledSources.push(src);
    src.onended = () => {
      const idx = scheduledSources.indexOf(src);
      if (idx !== -1) scheduledSources.splice(idx, 1);
    };
    return src;
  }

  function updateDots(beat) {
    for (let i = 0; i < beatsPerBar; i++) {
      const dot = document.getElementById('mdot-' + i);
      if (!dot) continue;
      dot.classList.remove('active-accent', 'active-beat');
      if (i === beat) dot.classList.add(beat === 0 ? 'active-accent' : 'active-beat');
    }
  }

  function scheduler() {
    if (!running) return;
    const ctx = getCtx();
    while (nextBeatTime < ctx.currentTime + SCHEDULE_AHEAD_S) {
      const isAccent = currentBeat === 0;
      playBuf(isAccent ? accentBuf : clickBuf, nextBeatTime);
      // Schedule dot flash at the right wall-clock time
      const delay = Math.max(0, (nextBeatTime - ctx.currentTime) * 1000);
      const beatSnapshot = currentBeat;
      const handle = setTimeout(() => updateDots(beatSnapshot), delay);
      scheduledDotHandles.push(handle);
      currentBeat = (currentBeat + 1) % beatsPerBar;
      nextBeatTime += 60.0 / bpm;
    }
  }

  async function start() {
    await ensureBuffers();
    const ctx = getCtx();
    if (ctx.state === 'suspended') await ctx.resume();
    running = true;
    currentBeat = 0;
    nextBeatTime = ctx.currentTime + 0.05;
    scheduler();
    schedulerHandle = setInterval(scheduler, LOOKAHEAD_MS);
    document.getElementById('metro-play-btn').textContent = '⏹';
  }

  function stop() {
    running = false;
    clearInterval(schedulerHandle);
    schedulerHandle = null;
    scheduledSources.forEach((src) => {
      try {
        src.stop();
      } catch (_e) {
        // ignore sources that are already stopped
      }
    });
    scheduledSources.length = 0;
    scheduledDotHandles.forEach(clearTimeout);
    scheduledDotHandles.length = 0;
    // Clear all dots
    for (let i = 0; i < 6; i++) {
      const dot = document.getElementById('mdot-' + i);
      if (dot) dot.classList.remove('active-accent', 'active-beat');
    }
    document.getElementById('metro-play-btn').textContent = '▶';
  }

  function rebuildDots(n) {
    const row = document.getElementById('metro-beat-row');
    row.innerHTML = '';
    for (let i = 0; i < n; i++) {
      const d = document.createElement('span');
      d.className = 'metro-dot';
      d.id = 'mdot-' + i;
      row.appendChild(d);
    }
  }

  // Expose to global scope so inline handlers can call them
  window.metroToggle = function() { running ? stop() : start(); };

  window.metroBpmChange = function(v) {
    bpm = Math.max(20, Math.min(300, parseInt(v) || 120));
  };

  window.metroSigChange = function(v) {
    beatsPerBar = parseInt(v) || 4;
    currentBeat = 0;
    rebuildDots(beatsPerBar);
    if (running) { stop(); start(); }
  };

  window.metroTap = function() {
    const now = performance.now();
    if (tapTimes.length && now - tapTimes[tapTimes.length - 1] > MAX_TAP_GAP_MS) {
      tapTimes.length = 0;
    }
    tapTimes.push(now);
    if (tapTimes.length >= 2) {
      const intervals = [];
      for (let i = 1; i < tapTimes.length; i++) intervals.push(tapTimes[i] - tapTimes[i - 1]);
      const avg = intervals.reduce((a, b) => a + b, 0) / intervals.length;
      bpm = Math.round(Math.max(20, Math.min(300, 60000 / avg)));
      const inp = document.getElementById('metro-bpm');
      if (inp) inp.value = bpm;
    }
    if (tapTimes.length > 8) tapTimes.shift();
  };

  window.metroCountIn = function(beats, countInBpm, shouldStop) {
    return playCountIn(beats, countInBpm, shouldStop);
  };
})();
// ---------------------------------------------------------------------------
// Scales tab (FR-20260517-guitar-trainer-scale-exercises)
// ---------------------------------------------------------------------------
(function initScales() {
  let _positions = [];
  let _currentPos = 0;
  let _scaleBpm = 160;
  let _scalePlaying = false;
  let _scaleStopFlag = false;
  let _currentKey = 'C';
  let _currentMode = 'Ionian';
  let _currentFamily = 'diatonic';  // FR-20260806: diatonic | major_penta | minor_penta
  let _calloutPending = false;  // when true, next phrase appends the mode's characteristic-note callout (set on mode switch only)
  const _scaleTapTimes = [];
  const MAX_TAP_GAP_MS = 3000;

  // ── Tab switching ────────────────────────────────────────────────────────
  window.switchTab = function(name) {
    const exPanel = document.getElementById('tab-exercises');
    const scPanel = document.getElementById('tab-scales');
    const exBtn = document.getElementById('tab-btn-exercises');
    const scBtn = document.getElementById('tab-btn-scales');
    if (exPanel) exPanel.style.display = name === 'exercises' ? '' : 'none';
    if (scPanel) scPanel.style.display = name === 'scales'    ? '' : 'none';
    if (exBtn) exBtn.classList.toggle('active', name === 'exercises');
    if (scBtn) scBtn.classList.toggle('active', name === 'scales');
    if (name === 'scales' && !_positions.length) loadScalePositions(_currentKey);
  };

  // ── Load positions from server ───────────────────────────────────────────
  async function loadScalePositions(key) {
    key = key || 'C';
    const family = _currentFamily === 'diatonic' ? 'diatonic'
                 : _currentFamily === 'major_penta' ? 'major_pentatonic'
                 : 'minor_pentatonic';
    try {
      const r = await fetch(
        '/api/scale-positions?key=' + encodeURIComponent(key) +
        '&family=' + encodeURIComponent(family)
      );
      _positions = await r.json();
    } catch (e) { console.error('scale positions load failed', e); return; }

    const sel = document.getElementById('scale-position');
    const hasGroups = _positions.length && _positions[0].group;
    if (hasGroups) {
      // Option B: grouped <optgroup> — Box Positions then CAGED Shapes
      const boxItems  = _positions.filter(p => p.group === 'box');
      const cagedItems = _positions.filter(p => p.group === 'caged');
      let html = `<optgroup label="── Box Positions (${boxItems.length})">`;
      boxItems.forEach((p, i) => {
        html += `<option value="${i}">${p.label}</option>`;
      });
      html += `</optgroup><optgroup label="── CAGED Shapes">`;
      cagedItems.forEach((p, i) => {
        html += `<option value="${boxItems.length + i}">${p.label}</option>`;
      });
      html += '</optgroup>';
      sel.innerHTML = html;
    } else {
      sel.innerHTML = _positions.map((p, i) =>
        `<option value="${i}">${formatPositionLabel(p)}</option>`
      ).join('');
    }
    onPositionChange();
    drawStaves(key, _currentMode, -1);
  }

  // ── Mode root label (FR-20260806-guitar-trainer-mode-root-label) ────────
  // Semitone offset of each mode tonic above the key root, matching MODE_SPEC.
  const MODE_ROOT_OFFSET = {Ionian:0,Dorian:2,Phrygian:4,Lydian:5,Mixolydian:7,Aeolian:9,Locrian:11};
  const CHROMATIC_PC = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];
  const ENHARMONIC_PC = {Db:'C#',Eb:'D#',Gb:'F#',Ab:'G#',Bb:'A#'};
  const FLAT_KEY_SET = ['F','Bb','Eb','Ab','Db','Gb'];
  const TO_FLAT = {'C#':'D♭','D#':'E♭','F#':'G♭','G#':'A♭','A#':'B♭'};

  function modeRootNote(keyVal, mode) {
    const resolved = ENHARMONIC_PC[keyVal] || keyVal;
    const idx = CHROMATIC_PC.indexOf(resolved);
    const rootIdx = (idx + (MODE_ROOT_OFFSET[mode] || 0)) % 12;
    const raw = CHROMATIC_PC[rootIdx];
    if (FLAT_KEY_SET.includes(keyVal) && TO_FLAT[raw]) return TO_FLAT[raw];
    return raw.replace('#', '♯');
  }

  function populateModeSelect(keyVal) {
    const modes = ['Ionian','Dorian','Phrygian','Lydian','Mixolydian','Aeolian','Locrian'];
    const sel = document.getElementById('scale-mode');
    const current = sel.value || _currentMode;
    sel.innerHTML = modes.map(m =>
      `<option value="${m}" ${m===current?'selected':''}>${modeRootNote(keyVal, m)} ${m}</option>`
    ).join('');
    _currentMode = sel.value || 'Ionian';
  }

  window.onKeyChange = function() {
    _currentKey = document.getElementById('scale-key').value || 'C';
    populateModeSelect(_currentKey);
    _positions = [];
    loadScalePositions(_currentKey);
    drawStaves(_currentKey, _currentMode, -1);
  };

  // FR-20260806: pill toggle between Diatonic / Maj Penta / Min Penta
  window.onFamilyChange = function(family) {
    _currentFamily = family;
    const isDiatonic = family === 'diatonic';
    // Update pill button active states
    ['diatonic', 'major_penta', 'minor_penta'].forEach(f => {
      const btn = document.getElementById('family-btn-' + f);
      if (btn) {
        btn.classList.toggle('family-btn-active', f === family);
        btn.style.background = f === family ? 'var(--accent)' : '#111';
        btn.style.color      = f === family ? '#fff' : '#ccc';
      }
    });
    // Show/hide Mode selector (only relevant for diatonic)
    const modeLbl = document.getElementById('scale-mode-label');
    if (modeLbl) {
      modeLbl.style.opacity       = isDiatonic ? '1' : '0.3';
      modeLbl.style.pointerEvents = isDiatonic ? '' : 'none';
    }
    _positions = [];
    loadScalePositions(_currentKey);
  };

  window.onModeChange = function() {
    _currentMode = document.getElementById('scale-mode').value || 'Ionian';
    _calloutPending = true;  // surface the characteristic-note callout once, on this switch
    if (_positions.length) {
      const sel = document.getElementById('scale-position');
      sel.innerHTML = _positions.map((p, i) =>
        `<option value="${i}">${formatPositionLabel(p)}</option>`
      ).join('');
    }
    onPositionChange();
    drawStaves(_currentKey, _currentMode, -1);
  };

  function formatPositionLabel(pos) {
    if (_currentMode === 'Aeolian' && _currentKey === 'C') {
      return pos.label.replace(/\s*\([^)]*\)$/, '');
    }
    return pos.label;
  }

  function findRootNoteInAsc(allAsc, rootPc) {
    return allAsc.find(n => n.midi % 12 === rootPc) || null;
  }

  function buildAscDeduped(notes) {
    const sorted = notes.slice().sort((a, b) => a.midi - b.midi);
    const seen = new Set();
    const allAsc = [];
    for (const n of sorted) {
      if (!seen.has(n.midi)) {
        seen.add(n.midi);
        allAsc.push(n);
      }
    }
    return allAsc;
  }

  function findTonicStart(pos, mode) {
    const rootPc = findModeRootPitchClass(_currentKey, mode);
    const allAsc = buildAscDeduped(pos.notes);
    return findRootNoteInAsc(allAsc, rootPc);
  }

  function buildModePhrase(pos, mode, includeCallout) {
    const shapeName = pos.label.replace(/^Position \d+ — /, '').replace(/\s*\([^)]*\)$/, '')
      .replace(/\s*shape\s*$/i, '')
      .trim()
      .replace(/([A-G])#/g, '$1 sharp')
      .replace(/([A-G])b/g, '$1 flat');
    const tonic = findTonicStart(pos, mode);
    const noteNames = FLAT_KEYS.has(_currentKey) ? PC_NAMES_FLAT : PC_NAMES;
    const modeRootPc = findModeRootPitchClass(_currentKey, mode);
    const rawTonicName = noteNames[modeRootPc] || 'D';
    const tonicName = rawTonicName.replace(/^([A-G])#$/, '$1 sharp').replace(/^([A-G])b$/, '$1 flat');
    const stringNames = {1: 'high e', 2: 'B', 3: 'G', 4: 'D', 5: 'A', 6: 'low E'};
    // Prefer low E when root falls within 2 frets of the position anchor (e.g. Locrian root 1 fret below G/river anchor).
    // No fretboard dots are added — this is TTS location only.
    let effectiveTonic = tonic;
    if (!tonic || tonic.string !== 6) {
      const baseFret = ((modeRootPc - 4 + 12) % 12);  // open low E = pc 4 (E2)
      const nearFret = baseFret + 12 * Math.round((pos.root_fret - baseFret) / 12);
      if (nearFret >= 0 && nearFret <= 22 && Math.abs(nearFret - pos.root_fret) <= 2) {
        effectiveTonic = {string: 6, fret: nearFret};
      }
    }
    let tonicLocation = '';
    if (effectiveTonic) {
      const stringName = stringNames[effectiveTonic.string] || 'unknown';
      if (effectiveTonic.fret === 0) {
        tonicLocation = `on the open ${stringName} string`;
      } else {
        tonicLocation = `on the ${stringName} string at fret ${effectiveTonic.fret}`;
      }
    }
    const spec = MODE_SPEC[mode] || MODE_SPEC['Ionian'];
    const rootLabel = mode === 'Ionian' ? 'tonic root' : `root of the ${spec.tts_label} scale`;
    let phrase = `Start on the ${rootLabel} ${tonicName}`;
    if (tonicLocation) {
      phrase += `, ${tonicLocation}`;
    }
    if (shapeName) {
      phrase += ` and go up and down the ${shapeName} shape.`;
    }
    if (includeCallout && spec.characteristic) {
      phrase += ` — ${spec.characteristic.callout}.`;
    }
    return phrase.trim();
  }

  window.onPositionChange = function() {
    _currentPos = parseInt(document.getElementById('scale-position').value) || 0;
    const pos = _positions[_currentPos];
    if (!pos) return;
    let phrase = pos.instructor_phrase;
    const spec = MODE_SPEC[_currentMode];
    // Modes with a dedicated colored degree set get a mode-aware spoken phrase.
    if (spec && (Object.keys(spec.degrees).length > 3 || spec.characteristic)) {
      phrase = buildModePhrase(pos, _currentMode, _calloutPending);
    }
    _calloutPending = false;
    updateLegend();
    // Load instructor audio — include phrase as cache-buster so URL changes when phrase changes
    const audio = document.getElementById('instructor-audio');
    audio.onerror = () => {};
    audio.src = `/api/instructor-audio?position=${_currentPos + 1}&key=${encodeURIComponent(_currentKey)}&mode=${encodeURIComponent(_currentMode)}&p=${encodeURIComponent(phrase)}`;
    audio.load();
    audio.play().catch(() => {});
    drawFretboard(pos.notes, -1);
    drawStaves(_currentKey, _currentMode, -1);
  };

  // ── SVG fretboard renderer ───────────────────────────────────────────────
  const KEY_PC = {C:0, Db:1, D:2, E:4, F:5, 'F#':6, G:7, A:9, B:11, Bb:10, 'A#':10, Eb:3, 'D#':3, Ab:8};
  // Single source of truth — injected from training/mode_spec.py (FR-20260629).
  const MODE_SPEC = {{ mode_spec | tojson }};
  const DEGREE_COLORS = {{ degree_colors | tojson }};
  const DEGREE_TEXT   = {{ degree_text | tojson }};
  const DEGREE_STROKE = {{ degree_stroke | tojson }};
  const PENTA_DEGREE_COLORS = {{ penta_degree_colors | tojson }};
  const PENTA_DEGREE_TEXT   = {{ penta_degree_text | tojson }};
  const PENTA_DEGREE_STROKE = {{ penta_degree_stroke | tojson }};
  // Pentatonic interval → degree type (intervals relative to penta root)
  const PENTA_DEGREE_MAP = {
    major_penta: {0:'root',2:'penta_second',4:'penta_third',7:'penta_fifth',9:'penta_sixth'},
    minor_penta: {0:'root',3:'penta_third',5:'penta_fourth',7:'penta_fifth',10:'penta_flat7'},
  };
  const MODE_ROOT_OFFSETS = Object.fromEntries(
    Object.entries(MODE_SPEC).map(([m, s]) => [m, s.root_offset])
  );

  const PC_NAMES      = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];
  const PC_NAMES_FLAT = ['C','Db','D','Eb','E','F','Gb','G','Ab','A','Bb','B'];
  const FLAT_KEYS     = new Set(['F','Bb','Eb','Ab','Db','Gb']);

  function findModeRootPitchClass(key, mode) {
    const base = KEY_PC[key] ?? 0;
    const offset = MODE_ROOT_OFFSETS[mode] ?? 0;
    return (base + offset) % 12;
  }

  // For pentatonic families the effective root PC differs from the mode root.
  // major_penta → same as key root; minor_penta → relative minor (key_pc + 9).
  function effectiveRootPc(key, mode) {
    if (_currentFamily === 'minor_penta') return ((KEY_PC[key] ?? 0) + 9) % 12;
    return findModeRootPitchClass(key, mode);
  }

  function buildScalePlayback(notes, key, mode) {
    const allAsc = buildAscDeduped(notes);
    const rootPc = effectiveRootPc(key, mode);
    const rootNote = findRootNoteInAsc(allAsc, rootPc);
    const rootIdx  = rootNote ? allAsc.indexOf(rootNote) : 0;
    const asc       = allAsc.slice(rootIdx);
    const desc      = allAsc.slice(rootIdx === 0 ? 1 : 0, -1).reverse();
    const returnAsc = allAsc.slice(1, rootIdx);
    const sequence  = [...asc, ...desc, ...returnAsc];
    return {sequence, allAsc};
  }

  // Returns pos.notes augmented with the synthetic root on low E when the mode root falls
  // at root_fret-1 on string 6 (e.g. Locrian root B at fret 7 in G/river shapes).
  function getEffectiveNotes(pos) {
    if (!pos) return [];
    const notes = (pos.notes || []).slice();
    const rootPc = effectiveRootPc(_currentKey, _currentMode);
    if (pos.root_fret > 0) {
      const synthFret = pos.root_fret - 1;
      const synthMidi = 40 + synthFret;
      if (synthMidi % 12 === rootPc && !notes.some(n => n.string === 6 && n.fret === synthFret)) {
        notes.push({string: 6, fret: synthFret, midi: synthMidi});
      }
    }
    return notes;
  }
  // Standard guitar fret dot positions
  const FRET_MARKERS = new Set([3, 5, 7, 9, 12, 15, 17, 19, 21]);
  // Degree colors are driven by mode_spec.py (DEGREE_COLORS/TEXT/STROKE) so the
  // fretboard, staff, and legend all render from one palette.
  const DOT_FILL   = DEGREE_COLORS;
  const DOT_TEXT   = DEGREE_TEXT;
  const DOT_STROKE = DEGREE_STROKE;
  const PLAYING_COLOR = '#ffe066';

  function updateLegend() {
    const el = document.getElementById('scale-legend');
    if (!el) return;
    if (_currentFamily !== 'diatonic') {
      const degMap = PENTA_DEGREE_MAP[_currentFamily] || {};
      // Show only root and fifth for minor penta (Option B dominant palette)
      const pentaLabels = _currentFamily === 'minor_penta'
        ? [[0,'Root'],[3,'\u266d3'],[5,'4th'],[7,'5th'],[10,'\u266d7']]
        : [[0,'Root'],[2,'2nd'],[4,'3rd'],[7,'5th'],[9,'6th']];
      el.innerHTML = pentaLabels.map(([iv, label]) => {
        const dt = degMap[iv] || 'root';
        const color = PENTA_DEGREE_COLORS[dt] || '#555';
        return `<span class="legend-item"><svg width="12" height="12"><circle cx="6" cy="6" r="5" fill="${color}"/></svg>${label}</span>`;
      }).join('');
      return;
    }
    const spec = MODE_SPEC[_currentMode] || MODE_SPEC['Ionian'];
    const intervals = Object.keys(spec.degrees).map(Number).sort((a, b) => a - b);
    const items = intervals.map(i => [DEGREE_COLORS[spec.degrees[i].type], spec.degrees[i].label]);
    el.innerHTML = items.map(([color, label]) =>
      `<span class="legend-item"><svg width="12" height="12"><circle cx="6" cy="6" r="5" fill="${color}"/></svg>${label}</span>`
    ).join('');
  }

  function getDotTypeForMode(interval, key, mode) {
    const spec = MODE_SPEC[mode] || MODE_SPEC['Ionian'];
    const deg = spec.degrees[((interval % 12) + 12) % 12];
    return deg ? deg.type : 'other';
  }

  window.drawFretboard = function(notes, activeIdx) {
    const svg = document.getElementById('fretboard-svg');
    const W = 1320, H = 240;
    const LEFT = 58, RIGHT = W - 20;  // wider left margin for open-string zone
    const TOP = 20, BOTTOM = H - 30;
    const NUM_STRINGS = 6;
    const NUM_FRETS = 22;
    const strGap = (BOTTOM - TOP) / (NUM_STRINGS - 1);
    const fretW = (RIGHT - LEFT) / NUM_FRETS;
    let html = '';
    // Fret lines (nut = thick white bar at f=0)
    for (let f = 0; f <= NUM_FRETS; f++) {
      const x = LEFT + f * fretW;
      const w = f === 0 ? 3 : 1;
      html += `<line x1="${x}" y1="${TOP}" x2="${x}" y2="${BOTTOM}" stroke="${f===0?'#eee':'#888'}" stroke-width="${w}"/>`;
    }
    // String lines — string 1 (high e) at top, string 6 (low E) at bottom; thickness increases downward
    for (let s = 0; s < NUM_STRINGS; s++) {
      const y = TOP + s * strGap;
      html += `<line x1="${LEFT}" y1="${y}" x2="${RIGHT}" y2="${y}" stroke="#bbb" stroke-width="${1 + s * 0.3}"/>`;
    }
    // Fret numbers — standard guitar marker positions only
    for (let f = 1; f <= NUM_FRETS; f++) {
      if (!FRET_MARKERS.has(f)) continue;
      const x = LEFT + (f - 0.5) * fretW;
      html += `<text x="${x}" y="${H - 8}" fill="#ddd" text-anchor="middle" font-size="9" font-family="Segoe UI,sans-serif">${f}</text>`;
    }
    // String labels — high e at top (row 0) … low E at bottom (row 5)
    const stringLabels = ['e','B','G','D','A','E'];
    for (let s = 0; s < NUM_STRINGS; s++) {
      const y = TOP + s * strGap;
      html += `<text x="${LEFT - 8}" y="${y + 4}" fill="#eee" text-anchor="end" font-size="9" font-family="Segoe UI,sans-serif">${stringLabels[s]}</text>`;
    }
    // "open" zone label
    html += `<text x="${LEFT - 20}" y="${H - 8}" fill="#bbb" text-anchor="middle" font-size="8" font-family="Segoe UI,sans-serif">open</text>`;
    // Scale dots — string 1 (high e) → row 0 (top), string 6 (low E) → row 5 (bottom)
    // Open-string notes appear to the LEFT of the nut
    const rootPc = effectiveRootPc(_currentKey, _currentMode);
    const noteNames = FLAT_KEYS.has(_currentKey) ? PC_NAMES_FLAT : PC_NAMES;
    const sorted = getEffectiveNotes(_positions[_currentPos]).slice().sort((a,b) => a.midi - b.midi);
    const isPenta = _currentFamily !== 'diatonic';
    const _synPos = null;  // synthetic note now handled by getEffectiveNotes
    sorted.forEach((n, i) => {
      const row = n.string - 1;  // string 1→row 0 (top), string 6→row 5 (bottom)
      const y = TOP + row * strGap;
      const isOpen = n.fret === 0;
      const x = isOpen ? LEFT - 18 : LEFT + (n.fret - 0.5) * fretW;
      const isActive = i === activeIdx;
      const pc = n.midi % 12;
      const interval = (pc - rootPc + 12) % 12;
      let fill, textFill, stroke;
      if (isPenta) {
        const degMap = PENTA_DEGREE_MAP[_currentFamily] || {};
        const degType = degMap[interval] || 'other';
        fill      = isActive ? PLAYING_COLOR : (PENTA_DEGREE_COLORS[degType] || '#555555');
        textFill  = isActive ? '#000000'     : (PENTA_DEGREE_TEXT[degType]   || '#ffffff');
        stroke    = isActive ? '#000000'     : (PENTA_DEGREE_STROKE[degType] || '#000000');
      } else {
        const dotType = getDotTypeForMode(interval, _currentKey, _currentMode);
        fill      = isActive ? PLAYING_COLOR : DOT_FILL[dotType];
        textFill  = isActive ? '#000000'     : DOT_TEXT[dotType];
        stroke    = isActive ? '#000000'     : DOT_STROKE[dotType];
      }
      const r = isActive ? 10 : 9;
      const noteName = noteNames[pc];
      html += `<circle cx="${x}" cy="${y}" r="${r}" fill="${fill}" stroke="${stroke}" stroke-width="1" class="fret-dot${isActive?' playing':''}" data-note-idx="${i}"/>`;
      html += `<text x="${x}" y="${y + 4}" fill="${textFill}" text-anchor="middle" font-size="10" font-weight="bold" font-family="Segoe UI,sans-serif">${noteName}</text>`;
    });
    svg.innerHTML = html;
  };

  // ── Staff notation renderer (FR-20260530-guitar-trainer-staff-notation) ──
  const MAJOR_INTERVALS = [0, 2, 4, 5, 7, 9, 11, 12];
  const MODE_SCALE_INTERVALS = Object.fromEntries(
    Object.entries(MODE_SPEC).map(([m, s]) => [m, s.intervals])
  );
  const STAFF_COLORS = DEGREE_COLORS;
  const STAFF_TEXT   = DEGREE_TEXT;
  // Key signature accidental counts (positive = sharps, negative = flats)
  const KEY_SIGS = { C: 0, Db: -5, D: 2, Eb: -3, E: 4, F: -1, 'F#': 6, G: 1, Ab: -4, Bb: -2, B: 5, 'A#': -2, 'D#': -3 };
  const SHARP_ORDER = ['F', 'C', 'G', 'D', 'A', 'E', 'B'];
  const FLAT_ORDER  = ['B', 'E', 'A', 'D', 'G', 'C', 'F'];
  // Y positions for accidentals on treble/bass clef (per accidental order slot)
  // Staff lines at Y=30(F5),40(D5),50(B4),60(G4),70(E4) — treble; Y=30(A3),40(F3),50(D3),60(B2),70(G2) — bass
  const SHARP_TREBLE_Y = [30, 45, 60, 40, 55, 35, 50]; // F C G D A E B → F5 C5 G4 D5 A4 E5 B4
  const FLAT_TREBLE_Y  = [50, 35, 55, 40, 60, 45, 30]; // B E A D G C F → B4 E5 A4 D5 G4 C5 F5
  const SHARP_BASS_Y   = [40, 55, 35, 50, 65, 45, 60]; // F C G D A E B → F3 C3 G3 D3 A2 E3 B2
  const FLAT_BASS_Y    = [60, 45, 65, 50, 70, 55, 40]; // B E A D G C F → B2 E3 A2 D3 G2 C3 F3
  // Treble clef: C4 sits one ledger line below staff (Y=80); each diatonic step = -5px upward
  // Lines at Y=30,40,50,60,70 (top to bottom): F5,D5,B4,G4,E4
  const DIATONIC_STEP_FROM_C = {
    C: 0, D: 1, E: 2, F: 3, G: 4, A: 5, B: 6,
    Db: 1, Eb: 2, Gb: 4, Ab: 5, Bb: 6,
    'A#': 5, 'D#': 1, 'G#': 4, 'C#': 0, 'F#': 3,
  };
  // Bass clef: G2 at bottom line (Y=70); each diatonic step = -5px upward
  const BASS_STEP_FROM_G2 = {
    C: 3, D: 4, E: 5, F: 6, G: 0, A: 1, B: 2,
    Db: 4, Eb: 5, Gb: 0, Ab: 1, Bb: 2,
    'A#': 1, 'D#': 4, 'G#': 0, 'C#': 3, 'F#': 6,
  };

  window.drawStaves = function(key, mode, highlightMidi) {
    // Staff rendering always uses the selected major key's signature and
    // notation convention. For Aeolian, the note sequence is mode-based
    // but the staff template borrows the major key signature.
    const useFlats = FLAT_KEYS.has(key);
    const noteNames = useFlats ? PC_NAMES_FLAT : PC_NAMES;
    drawSingleStaff('staff-treble-svg', key, mode, 'treble', noteNames, highlightMidi);
    drawSingleStaff('staff-bass-svg',   key, mode, 'bass',   noteNames, highlightMidi);
  };

  function drawSingleStaff(svgId, key, mode, clef, noteNames, highlightMidi) {
    const svg = document.getElementById(svgId);
    if (!svg) return;
    const W = 500, H = 120;
    const sigCount = KEY_SIGS[key] ?? 0;
    const absSig   = Math.abs(sigCount);
    const sigY_arr = clef === 'treble'
      ? (sigCount > 0 ? SHARP_TREBLE_Y : FLAT_TREBLE_Y)
      : (sigCount > 0 ? SHARP_BASS_Y   : FLAT_BASS_Y);
    const sigSymbol = sigCount > 0 ? '\u266f' : '\u266d';
    // Staff lines (5 lines, 10px spacing)
    const lineYs = [30, 40, 50, 60, 70];
    // Mode root base-Y on the staff
    const majorRootPc = KEY_PC[key] ?? 0;
    const modeRootPc = findModeRootPitchClass(key, mode);
    const modeRootName = noteNames[modeRootPc] ?? noteNames[majorRootPc];
    const rootStep = DIATONIC_STEP_FROM_C[modeRootName] ?? 0;
    const TREBLE_C4_Y = 80;
    const baseY = clef === 'treble'
      ? TREBLE_C4_Y - rootStep * 5
      : 70 - (BASS_STEP_FROM_G2[modeRootName] ?? 0) * 5;
    // X layout: leave room for clef symbol (55px) + key signature
    const CLEF_W = 55;
    const SIG_W  = Math.max(0, absSig) * 12;
    const noteXStart = CLEF_W + SIG_W + 8;
    const noteXSpacing = (W - noteXStart - 15) / 7;
    let html = '';
    // Draw staff lines
    for (const ly of lineYs) {
      html += `<line x1="18" y1="${ly}" x2="${W - 8}" y2="${ly}" stroke="#888" stroke-width="1"/>`;
    }
    // Clef label
    const clefChar = clef === 'treble' ? '\u{1D11E}' : '\u{1D122}';
    const clefY = clef === 'treble' ? 66 : 54;
    html += `<text x="20" y="${clefY}" fill="#ccc" font-size="38" font-family="serif">${clefChar}</text>`;
    // Key signature accidentals
    for (let k = 0; k < absSig; k++) {
      const sx = 56 + k * 12;
      const sy = sigY_arr[k] ?? 50;
      html += `<text x="${sx}" y="${sy}" fill="#aaa" font-size="14" font-family="serif" dominant-baseline="central" data-keysig="${clef}">${sigSymbol}</text>`;
    }
    const intervals = MODE_SCALE_INTERVALS[mode] ?? MAJOR_INTERVALS;
    const isPentaStaff = _currentFamily !== 'diatonic';
    const pentaRootPc  = effectiveRootPc(key, mode);
    const pentaDegMap  = PENTA_DEGREE_MAP[_currentFamily] || {};
    const pentaIntervals = _currentFamily === 'minor_penta'
      ? [0, 3, 5, 7, 10, 12] : [0, 2, 4, 7, 9, 12];
    const staffIntervals = isPentaStaff ? pentaIntervals : intervals;
    const staffRootPc    = isPentaStaff ? pentaRootPc    : modeRootPc;
    // Draw note circles
    for (let idx = 0; idx < staffIntervals.length; idx++) {
      const interval = staffIntervals[idx];
      const pc       = (staffRootPc + interval) % 12;
      const noteName = noteNames[pc];
      const noteY    = baseY - idx * 5;
      const noteX    = noteXStart + idx * noteXSpacing;
      const isHighlit = highlightMidi >= 0 && (pc === highlightMidi % 12);
      let noteFill, textFill;
      if (isPentaStaff) {
        const relInterval = (pc - staffRootPc + 12) % 12;
        const dt = pentaDegMap[relInterval] || 'other';
        noteFill = isHighlit ? '#ffe066' : (PENTA_DEGREE_COLORS[dt] || '#555');
        textFill = isHighlit ? '#000'    : (PENTA_DEGREE_TEXT[dt]   || '#fff');
      } else {
        const degInterval = (pc - modeRootPc + 12) % 12;
        const _spec = MODE_SPEC[mode] || MODE_SPEC['Ionian'];
        const colorKey = (_spec.degrees[degInterval] && _spec.degrees[degInterval].type) || 'other';
        noteFill = isHighlit ? '#ffe066' : STAFF_COLORS[colorKey];
        textFill = isHighlit ? '#000'    : STAFF_TEXT[colorKey];
      }
      if (noteY < lineYs[0] - 3 || noteY > lineYs[4] + 3) {
        html += `<line x1="${noteX - 10}" y1="${noteY}" x2="${noteX + 10}" y2="${noteY}" stroke="#888" stroke-width="1"/>`;
      }
      html += `<circle cx="${noteX}" cy="${noteY}" r="8" fill="${noteFill}" stroke="#000" stroke-width="1" data-staff="${clef}" data-degree="${idx}"/>`;
      html += `<text x="${noteX}" y="${noteY + 4}" fill="${textFill}" text-anchor="middle" font-size="9" font-weight="bold" font-family="Segoe UI,sans-serif">${noteName}</text>`;
    }
    svg.innerHTML = html;
  }

  // ── Web Audio oscillator playback ────────────────────────────────────────
  let _audioCtx = null;
  function getAudioCtx() {
    if (!_audioCtx) _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    return _audioCtx;
  }

  function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

  function getModeAccentType(midi) {
    const spec = MODE_SPEC[_currentMode] || MODE_SPEC['Ionian'];
    const rootPc = findModeRootPitchClass(_currentKey, _currentMode);
    const interval = (midi % 12 - rootPc + 12) % 12;
    if (!spec.accents.includes(interval)) return 'normal';
    const deg = spec.degrees[interval];
    return (deg && deg.type) || 'normal';
  }

  async function playNote(midi, durationMs, accentType = 'normal') {
    const ctx = getAudioCtx();
    if (ctx.state === 'suspended') await ctx.resume();
    const freq = {{ freq_table | tojson }}[midi];
    if (!freq) return;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = accentType === 'root' || accentType === 'minor_second' || accentType === 'minor_third'
        || accentType === 'flat_fifth' || accentType === 'flat_seventh'
        || accentType === 'major_sixth' || accentType === 'sharp_fourth'
      ? 'triangle'
      : 'sine';
    osc.frequency.value = freq;
    const now = ctx.currentTime;
    gain.gain.setValueAtTime(0, now);
    gain.gain.linearRampToValueAtTime(0.35, now + 0.01);
    gain.gain.setValueAtTime(0.35, now + durationMs / 1000 - 0.04);
    gain.gain.linearRampToValueAtTime(0, now + durationMs / 1000);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(now);
    osc.stop(now + durationMs / 1000 + 0.01);
  }

  window.scaleToggle = async function() {
    if (_scalePlaying) { _scaleStopFlag = true; return; }
    const pos = _positions[_currentPos];
    if (!pos) return;
    const reps = Math.max(1, Math.min(20, parseInt(document.getElementById('scale-reps').value) || 2));
    const noteDurationMs = Math.round(60000 / _scaleBpm);
    const {sequence, allAsc} = buildScalePlayback(getEffectiveNotes(pos), _currentKey, _currentMode);
    _scalePlaying = true;
    _scaleStopFlag = false;
    const btn = document.getElementById('scale-play-btn');
    btn.textContent = '⏹ Stop';
    const status = document.getElementById('scale-status');
    status.textContent = 'Count-in 1/4';
    if (window.scaleCountIn) {
      const countInOk = await window.scaleCountIn(4, _scaleBpm, () => _scaleStopFlag);
      if (!countInOk || _scaleStopFlag) {
        _scalePlaying = false;
        _scaleStopFlag = false;
        btn.textContent = '▶ Play';
        drawFretboard(pos.notes, -1);
        drawStaves(_currentKey, _currentMode, -1);
        status.textContent = '';
        return;
      }
    }
    for (let rep = 0; rep < reps && !_scaleStopFlag; rep++) {
      for (let i = 0; i < sequence.length && !_scaleStopFlag; i++) {
        status.textContent = `Rep ${rep + 1}/${reps} — note ${i + 1}/${sequence.length}`;
        drawFretboard(pos.notes, allAsc.indexOf(sequence[i]));
        drawStaves(_currentKey, _currentMode, sequence[i].midi);
        const accentType = getModeAccentType(sequence[i].midi);
        await playNote(sequence[i].midi, noteDurationMs * 0.85, accentType);
        await sleep(noteDurationMs);
      }
    }
    const stopped = _scaleStopFlag;
    _scalePlaying = false;
    _scaleStopFlag = false;
    btn.textContent = '▶ Play';
    drawFretboard(pos.notes, -1);
    drawStaves(_currentKey, _currentMode, -1);
    status.textContent = stopped ? '' : '✓ Complete';
    if (!stopped) {
      logScaleSession(_currentKey, _currentMode, _currentPos + 1, _scaleBpm, reps);
    }
  };

  window.scaleSetBpm = function(v) {
    _scaleBpm = Math.max(40, Math.min(200, parseInt(v) || 160));
  };

  window.scaleTap = function() {
    const now = performance.now();
    if (_scaleTapTimes.length && now - _scaleTapTimes[_scaleTapTimes.length - 1] > MAX_TAP_GAP_MS) {
      _scaleTapTimes.length = 0;
    }
    _scaleTapTimes.push(now);
    if (_scaleTapTimes.length >= 2) {
      const intervals = [];
      for (let i = 1; i < _scaleTapTimes.length; i++) intervals.push(_scaleTapTimes[i] - _scaleTapTimes[i-1]);
      const avg = intervals.reduce((a,b)=>a+b,0) / intervals.length;
      _scaleBpm = Math.round(Math.max(40, Math.min(200, 60000 / avg)));
      const inp = document.getElementById('scale-bpm');
      if (inp) inp.value = _scaleBpm;
    }
    if (_scaleTapTimes.length > 8) _scaleTapTimes.shift();
  };

  async function logScaleSession(key, mode, position, bpm, reps) {
    try {
      const modeKey = mode === 'Ionian' ? 'major' : mode.toLowerCase();
      const scale = `${key}_${modeKey}`;
      const r = await fetch('/api/scale-log', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({scale, position, bpm, reps, key: key || 'C', mode}),
      });
      if ((await r.json()).ok) loadScaleLog();
    } catch (e) { console.warn('scale log failed', e); }
  }

  async function loadScaleLog() {
    try {
      const r = await fetch('/api/scale-log');
      const rows = await r.json();
      const tbody = document.getElementById('scale-log-tbody');
      if (!rows.length) return;
      tbody.innerHTML = rows.slice(0, 10).map(row =>
        `<tr><td>${row.logged_at}</td><td>${row.key || 'C'}</td><td>${row.mode || 'Ionian'}</td><td>${row.scale.replace('_',' ')}</td><td>${row.position}</td><td>${row.bpm}</td><td>${row.reps}</td></tr>`
      ).join('');
    } catch(e) { console.warn('scale log load failed', e); }
  }

  populateModeSelect(_currentKey); // seed on page load (FR-20260806-guitar-trainer-mode-root-label)
  {% if not enable_exercise_cards %}
  // FR-20260808: exercise cards off -> Scales tab is pre-rendered active server-side,
  // but nothing ever calls switchTab('scales') (normally the tab button's onclick) --
  // so loadScalePositions() never fired and the Position select / fretboard stayed empty.
  switchTab('scales');
  {% endif %}
})();
</script>
</body>
</html>
"""


def album_art():
    """Return embedded album art bytes for a given audio file path.

    Returns 204 No Content when art is absent or the file cannot be read,
    so the browser <img> onerror handler hides the element gracefully.
    """
    path_str = request.args.get("path", "")
    if not path_str:
        return Response(status=204)
    # --- Security: path-traversal confinement (OWASP A01/A05) ---
    resolved = Path(path_str).resolve()
    if not any(resolved.is_relative_to(root) for root in _ART_ALLOWED_ROOTS):
        abort(403)
    # -------------------------------------------------------------
    try:
        from mutagen import File as MutagenFile  # lazy import
        audio = MutagenFile(str(resolved))
        if audio is None:
            return Response(status=204)
        data: bytes | None = None
        mime: str = "image/jpeg"
        # MP3 — ID3 APIC
        if hasattr(audio, "tags") and audio.tags is not None:
            tags = audio.tags
            # ID3 APIC
            for key in list(tags.keys()):
                if key.startswith("APIC"):
                    apic = tags[key]
                    data = apic.data
                    mime = apic.mime or mime
                    break
        # FLAC — picture blocks
        if data is None and hasattr(audio, "pictures"):
            pics = audio.pictures
            if pics:
                data = pics[0].data
                mime = pics[0].mime or mime
        # MP4/M4A — covr
        if data is None and hasattr(audio, "tags") and audio.tags is not None:
            covr = audio.tags.get("covr")
            if covr:
                cover = covr[0]
                data = bytes(cover)
                from mutagen.mp4 import MP4Cover
                mime = "image/png" if cover.imageformat == MP4Cover.FORMAT_PNG else "image/jpeg"
        if not data:
            return Response(status=204)
        return Response(data, status=200, mimetype=mime)
    except Exception:
        return Response(status=204)


def catalog():
    return jsonify(_scan_muzic())


@app.route("/click/<path:filename>")
def click_audio(filename: str) -> Response:
    """Serve metronome WAV files from the project click/ directory.

    Security: only .wav files, no path traversal.
    """
    if not filename.endswith(".wav") or "/" in filename or "\\" in filename:
        abort(403)
    safe = CLICK_DIR.resolve() / filename
    if not safe.resolve().is_relative_to(CLICK_DIR.resolve()):
        abort(403)
    return send_from_directory(str(CLICK_DIR), filename)


@app.route("/")
def index():
    # FR-20260808: sessions/log read guitar_exercises/guitar_training_log --
    # the same tables backing /api/sessions and /api/log, which are gated
    # behind ENABLE_EXERCISE_CARDS. Skip the DB calls when the flag is off
    # so a cloud deploy with no DB driver installed doesn't 500 on '/'.
    sessions = _list_sessions() if ENABLE_EXERCISE_CARDS else []
    log = _load_log() if ENABLE_EXERCISE_CARDS else []
    if ENABLE_EXERCISE_CARDS or ENABLE_SCALE_LOG:
        stats = get_practice_stats()
    else:
        stats = {"streak_days": 0, "week_minutes": 0, "last_practiced": None}
    return render_template_string(
        HTML,
        sessions=sessions,
        log=log,
        freq_table=MIDI_TO_FREQ,
        stats=stats,
        mode_spec=MODE_SPEC,
        degree_colors=DEGREE_COLORS,
        degree_text=DEGREE_TEXT,
        degree_stroke=DEGREE_STROKE,
        penta_degree_colors=PENTATONIC_DEGREE_COLORS,
        penta_degree_text=PENTATONIC_DEGREE_TEXT,
        penta_degree_stroke=PENTATONIC_DEGREE_STROKE,
        enable_exercise_cards=ENABLE_EXERCISE_CARDS,
        enable_scale_log=ENABLE_SCALE_LOG,
    )


@app.route("/health")
def health():
    return jsonify({"status": "ok", "ready": True})


def save():
    data = request.get_json(force=True)
    exercise_id = data.get("id")
    if not isinstance(exercise_id, int):
        return jsonify({"ok": False, "error": "Invalid id"})
    try:
        segments = json.dumps(data.get("segments", []))
        gradient = int(round(float(data.get("gradient", 0))))
        with get_connection() as conn:
            conn.execute(
                "UPDATE guitar_exercises SET segments=?, gradient=?, updated_at=datetime('now') WHERE id=?",
                (segments, gradient, exercise_id),
            )
            conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


def launch():
    data = request.get_json(force=True)
    exercise_id = data.get("id")
    if not isinstance(exercise_id, int):
        return jsonify({"ok": False, "error": "Invalid id"})
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT title, artist, song_path, segments, gradient FROM guitar_exercises WHERE id=?",
                (exercise_id,),
            ).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "Exercise not found"})
        gradient = int(round(float(data.get("gradient", row["gradient"] or 0))))
        session = {
            "songPath": row["song_path"],
            "title": row["title"],
            "artist": row["artist"],
            "segments": json.loads(row["segments"] or "[]"),
            "gradient": gradient,
        }
        tmp_name = f"_run_{exercise_id}.json"
        tmp_path = TRAINING_DIR / tmp_name
        tmp_path.write_text(json.dumps(session, indent=4), encoding="utf-8")

        tools_dir = str(PROJECT_ROOT / "tools").replace("\u2764", "$([char]0x2764)")
        ps_cmd = (
            f"$env:PYTHONUTF8='1'; "
            f"Set-Location \"{tools_dir}\"; "
            f"& 'C:\\G\\python.exe' 'focused_musician_training.py' '{tmp_name}'"
        )
        subprocess.Popen(  # nosec B603,B607
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-Command", ps_cmd],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


def create():
    data = request.get_json(force=True)
    title = (data.get("title") or "").strip()
    song_path = (data.get("songPath") or "").strip()
    if not title or not song_path:
        return jsonify({"ok": False, "error": "title and songPath required"})
    artist = (data.get("artist") or "").strip()
    default_segments = json.dumps([{"start": "0:05", "end": "0:15", "speed": 75, "repetition": 4}])
    try:
        with get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO guitar_exercises (title, artist, song_path, segments, gradient) VALUES (?,?,?,?,?)",
                (title, artist, song_path, default_segments, 0),
            )
            conn.commit()
            new_id = cur.lastrowid
        return jsonify({"ok": True, "id": new_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


def api_sessions():
    return jsonify(_list_sessions())


def api_log():
    if request.method == "GET":
        return jsonify(_load_log())
    # POST — log a guitar training session manually
    data = request.get_json(force=True) or {}
    song_path = str(data.get("song_path") or "").strip()
    seg_start = str(data.get("seg_start") or "").strip()
    seg_end = str(data.get("seg_end") or "").strip()
    try:
        repetition = int(data.get("repetition") or 1)
    except (TypeError, ValueError):
        repetition = 1
    try:
        duration_minutes = max(0, int(data.get("duration_minutes") or 0))
    except (TypeError, ValueError):
        duration_minutes = 0
    key = str(data.get("key") or "").strip() or None
    try:
        position_val = data.get("position")
        position = int(position_val) if position_val is not None else None
    except (TypeError, ValueError):
        position = None
    exercise_name = str(data.get("exercise_name") or "").strip() or None
    exercise_id_raw = data.get("exercise_id")
    exercise_id = int(exercise_id_raw) if isinstance(exercise_id_raw, (int, float)) else None
    try:
        _append_log(exercise_id, song_path, seg_start, seg_end, repetition,
                    duration_minutes, key, position, exercise_name)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


def delete_session():
    data = request.get_json(force=True)
    exercise_id = data.get("id")
    if not isinstance(exercise_id, int):
        return jsonify({"ok": False, "error": "Invalid id"})
    try:
        with get_connection() as conn:
            conn.execute("DELETE FROM guitar_exercises WHERE id=?", (exercise_id,))
            conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ---------------------------------------------------------------------------
# Scale & Arpeggio routes (FR-20260517-guitar-trainer-scale-exercises)
# ---------------------------------------------------------------------------

@app.route("/api/scale-positions")
def api_scale_positions():
    """Return positions for the given key as JSON.

    Query params:
        key=C               (default) — key root
        family=diatonic     (default) — also accepts major_pentatonic | minor_pentatonic
    """
    key = request.args.get("key", "C").strip()
    family = request.args.get("family", "diatonic").strip()

    _VALID_FAMILIES = {"diatonic", "major_pentatonic", "minor_pentatonic"}
    if family not in _VALID_FAMILIES:
        abort(400)

    if family == "diatonic":
        positions = SCALE_POSITIONS.get(key)
        if positions is None:
            abort(400)
        return jsonify([
            {
                "label": p["label"],
                "root_string": p["root_string"],
                "root_fret": p["root_fret"],
                "instructor_phrase": p["instructor_phrase"],
                "notes": p["notes"],
            }
            for p in positions
        ])
    else:
        # Pentatonic: box positions (group="box"); CAGED group gated by feature flag
        box_list = BOX_PENTA_POSITIONS.get(key, {}).get(family, [])
        caged_list = [] if not PENTA_CAGED_ENABLED else (
            PENTATONIC_POSITIONS.get(key, [])
            if family == "major_pentatonic"
            else _MINOR_PENTA_POSITIONS.get(key, [])
        )
        if not box_list and not caged_list:
            abort(400)

        def _fmt(p, group):
            return {
                "label": p["label"],
                "root_string": p["root_string"],
                "root_fret": p["root_fret"],
                "instructor_phrase": p["instructor_phrase"],
                "notes": p["notes"],
                "group": group,
            }

        return jsonify(
            [_fmt(p, "box") for p in box_list] +
            [_fmt(p, "caged") for p in caged_list]
        )


def api_scale_log():
    if request.method == "GET":
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT key, mode, scale, position, bpm, reps, logged_at "
                    "FROM scale_practice_log ORDER BY id DESC LIMIT 50"
                ).fetchall()
            return jsonify([dict(r) for r in rows])
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    # POST — log a scale session
    data = request.get_json(force=True) or {}
    scale = str(data.get("scale") or "C_major").strip()
    position = data.get("position")
    bpm = data.get("bpm")
    reps = data.get("reps")
    key = str(data.get("key") or "C").strip()
    # Validate
    if not scale:
        return jsonify({"ok": False, "error": "scale required"})
    if key not in SCALE_POSITIONS:
        return jsonify({"ok": False, "error": f"key must be one of {list(SCALE_POSITIONS)}"})
    try:
        position = int(position)
        if not 1 <= position <= len(SCALE_POSITIONS[key]):
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": f"position must be integer 1-{len(SCALE_POSITIONS[key])}"})
    try:
        bpm = int(bpm)
        if not 40 <= bpm <= 200:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "bpm must be integer 40-200"})
    try:
        reps = int(reps)
        if not 1 <= reps <= 100:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "reps must be integer 1-100"})

    try:
        mode = str(data.get("mode") or "Ionian").strip()
        if mode not in ("Ionian", "Dorian", "Phrygian", "Lydian", "Mixolydian", "Aeolian", "Locrian"):
            return jsonify({"ok": False, "error": f"mode must be one of Ionian, Dorian, Phrygian, Lydian, Mixolydian, Aeolian, Locrian"})
        with get_connection() as conn:
            conn.execute(
              "INSERT INTO scale_practice_log (key, mode, scale, position, bpm, reps) VALUES (?,?,?,?,?,?)",
              (key, mode, scale, position, bpm, reps),
            )
            conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/instructor-audio")
def api_instructor_audio():
    """Return cached ElevenLabs MP3 for the instructor phrase of the given position.

    Returns 204 No Content when TTS is unavailable (no key, network error, etc.)
    """
    key = request.args.get("key", "C").strip()
    key_positions = SCALE_POSITIONS.get(key)
    if key_positions is None:
        abort(400)
    try:
        position = int(request.args.get("position", 0))
        if not 1 <= position <= len(key_positions):
            abort(400)
    except (TypeError, ValueError):
        abort(400)

    pos = key_positions[position - 1]
    phrase = str(request.args.get("p") or pos["instructor_phrase"]).strip() or pos["instructor_phrase"]
    audio_path = get_instructor_audio(phrase, TTS_CACHE_DIR)
    if audio_path is None or not audio_path.exists():
        return Response(status=204)

    # Security: ensure the resolved path is inside TTS_CACHE_DIR
    if not audio_path.resolve().is_relative_to(TTS_CACHE_DIR.resolve()):
        abort(403)

    # Cache-Control: no-cache — browser must revalidate with the server on
    # every request so that TTS normalization changes (which alter the
    # server-side cache key) are reflected immediately.  The server-side
    # file cache in TTS_CACHE_DIR still avoids re-calling ElevenLabs.
    return Response(
        audio_path.read_bytes(),
        status=200,
        mimetype="audio/mpeg",
        headers={"Cache-Control": "no-cache"},
    )


# ---------------------------------------------------------------------------
# Feature-flag route registration (FR-20260808-scale-trainer-flyio-deploy)
#
# These routes are conditionally exposed via app.add_url_rule() rather than
# @app.route() so that disabled routes are structurally absent from
# app.url_map (a request to a disabled path 404s at the routing layer, not
# inside the view function).
# ---------------------------------------------------------------------------

if ENABLE_EXERCISE_CARDS:
    app.add_url_rule("/save", view_func=save, methods=["POST"])
    app.add_url_rule("/launch", view_func=launch, methods=["POST"])
    app.add_url_rule("/create", view_func=create, methods=["POST"])
    app.add_url_rule("/delete", view_func=delete_session, methods=["POST"])
    app.add_url_rule("/catalog", view_func=catalog)
    app.add_url_rule("/art", view_func=album_art)
    app.add_url_rule("/api/sessions", view_func=api_sessions)
    app.add_url_rule("/api/log", view_func=api_log, methods=["GET", "POST"])

if ENABLE_SCALE_LOG:
    app.add_url_rule("/api/scale-log", view_func=api_scale_log, methods=["GET", "POST"])


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="❤Music Lead Guitar Training UI")
    parser.add_argument("--port", type=int, default=5055)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    TRAINING_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Lead Guitar Trainer -> http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)
