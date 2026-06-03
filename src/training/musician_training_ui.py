"""
❤Music — Focused Musician Training UI
Flask web interface for managing and launching lead guitar training sessions.
Exercise cards + practice log stored in heartmusic.db (guitar_exercises, guitar_training_log tables).
Scales & Arpeggios tab added in FR-20260517-guitar-trainer-scale-exercises.
"""

import argparse
import json
import os
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
from training.scale_data import SCALE_POSITIONS, CAGED_POSITIONS, MIDI_TO_FREQ, get_scale_sequence  # noqa: E402
from training.scale_tts import get_instructor_audio  # noqa: E402

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
  .scale-log-table td{padding:4px 8px;border-bottom:1px solid #222;color:#aaa}</style>
</style>
</head>
<body>
<div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px">
  <div>
    <h1>🎸 Lead Guitar Trainer</h1>
    <p class="sub">Focused interval training — loop lead parts, control speed, build muscle memory</p>
  </div>
  <div class="streak-badge" style="background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.15);border-radius:10px;padding:10px 16px;font-size:0.85rem;text-align:center;min-width:160px;flex-shrink:0">
    <div style="font-size:1.4rem;font-weight:700;">🔥 {{ stats.streak_days }} day{{ 's' if stats.streak_days != 1 else '' }}</div>
    <div style="opacity:0.7;margin-top:2px;">{{ stats.week_minutes }} min this week</div>
    <div style="opacity:0.5;margin-top:2px;font-size:0.75rem;">Last: {{ stats.last_practiced or 'never' }}</div>
  </div>
</div>

<!-- Tab navigation (FR-20260517-guitar-trainer-scale-exercises) -->
<div class="tab-nav" id="tab-nav">
  <button class="tab-btn active" id="tab-btn-exercises" onclick="switchTab('exercises')">🎸 Exercises</button>
  <button class="tab-btn" id="tab-btn-scales" onclick="switchTab('scales')">🎵 Scales</button>
</div>

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

<!-- Scales & Arpeggios tab panel (FR-20260517-guitar-trainer-scale-exercises) -->
<div id="tab-scales" class="tab-panel" style="display:none">
  <div class="scales-header">
    <h2>🎵 Scales &amp; Arpeggios</h2>
  </div>

  <div class="scale-row">
    <label>Key
      <select id="scale-key" class="scale-select" onchange="onKeyChange()">
        <option value="C">C major</option>
        <option value="D">D major</option>
        <option value="Eb">Eb / D&#x23; major</option>
        <option value="E">E major</option>
        <option value="F">F major</option>
        <option value="G">G major</option>
        <option value="A">A major</option>
        <option value="Bb">Bb / A&#x23; major</option>
        <option value="B">B major</option>
      </select>
    </label>
    <label>Position
      <select id="scale-position" class="scale-select" onchange="onPositionChange()"></select>
    </label>
    <span class="scale-legend">
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
      <input id="scale-bpm" class="scale-ctrl-input" type="number" value="60" min="40" max="200" oninput="scaleSetBpm(this.value)">
    </label>
    <button class="btn-scale-tap" onclick="scaleTap()">Tap</button>
    <label class="scale-ctrl-label">Reps
      <input id="scale-reps" class="scale-ctrl-input" type="number" value="4" min="1" max="20">
    </label>
    <label class="scale-ctrl-label">Duration (min)
      <input id="scale-duration" class="scale-ctrl-input" type="number" value="0" min="0" max="300">
    </label>
    <button class="btn-scale-play" id="scale-play-btn" onclick="scaleToggle()">▶ Play</button>
  </div>

  <div class="scale-status" id="scale-status"></div>

  <details style="margin-top:16px">
    <summary style="cursor:pointer;color:var(--accent);font-weight:600;font-size:.9rem;user-select:none">Scale Practice Log</summary>
    <div style="margin-top:8px" id="scale-log-wrap">
      <table class="scale-log-table">
        <thead><tr><th>Time</th><th>Key</th><th>Scale</th><th>Position</th><th>BPM</th><th>Reps</th></tr></thead>
        <tbody id="scale-log-tbody"><tr><td colspan="6" style="color:var(--muted)">No sessions yet.</td></tr></tbody>
      </table>
    </div>
  </details>
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
document.getElementById('catalog-list').addEventListener('click', e => {
  const item = e.target.closest('.catalog-item');
  if (item) selectFile(item.dataset.path, item.dataset.name);
});
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
  if (!e.target.closest('.new-card')) document.getElementById('catalog-dropdown').style.display = 'none';
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
  const LOOKAHEAD_MS = 25;
  const SCHEDULE_AHEAD_S = 0.1;

  // Tap-tempo state
  const tapTimes = [];
  const MAX_TAP_GAP_MS = 3000;

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

  function playBuf(buf, time) {
    if (!buf) return;
    const ctx = getCtx();
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    src.start(time);
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
    const ctx = getCtx();
    while (nextBeatTime < ctx.currentTime + SCHEDULE_AHEAD_S) {
      const isAccent = currentBeat === 0;
      playBuf(isAccent ? accentBuf : clickBuf, nextBeatTime);
      // Schedule dot flash at the right wall-clock time
      const delay = Math.max(0, (nextBeatTime - ctx.currentTime) * 1000);
      const beatSnapshot = currentBeat;
      setTimeout(() => updateDots(beatSnapshot), delay);
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
})();
// ---------------------------------------------------------------------------
// Scales tab (FR-20260517-guitar-trainer-scale-exercises)
// ---------------------------------------------------------------------------
(function initScales() {
  let _positions = [];
  let _currentPos = 0;
  let _scaleBpm = 60;
  let _scalePlaying = false;
  let _scaleStopFlag = false;
  let _currentKey = 'C';
  const _scaleTapTimes = [];
  const MAX_TAP_GAP_MS = 3000;

  // ── Tab switching ────────────────────────────────────────────────────────
  window.switchTab = function(name) {
    document.getElementById('tab-exercises').style.display = name === 'exercises' ? '' : 'none';
    document.getElementById('tab-scales').style.display   = name === 'scales'    ? '' : 'none';
    document.getElementById('tab-btn-exercises').classList.toggle('active', name === 'exercises');
    document.getElementById('tab-btn-scales').classList.toggle('active', name === 'scales');
    if (name === 'scales' && !_positions.length) loadScalePositions(_currentKey);
  };

  // ── Load positions from server ───────────────────────────────────────────
  async function loadScalePositions(key) {
    key = key || 'C';
    try {
      const r = await fetch('/api/scale-positions?key=' + encodeURIComponent(key));
      _positions = await r.json();
    } catch (e) { console.error('scale positions load failed', e); return; }
    const sel = document.getElementById('scale-position');
    sel.innerHTML = _positions.map((p, i) =>
      `<option value="${i}">${p.label}</option>`
    ).join('');
    onPositionChange();
    drawStaves(key, -1);
  }

  window.onKeyChange = function() {
    _currentKey = document.getElementById('scale-key').value || 'C';
    _positions = [];
    loadScalePositions(_currentKey);
    drawStaves(_currentKey, -1);
  };

  window.onPositionChange = function() {
    _currentPos = parseInt(document.getElementById('scale-position').value) || 0;
    const pos = _positions[_currentPos];
    if (!pos) return;
    const phraseBox = document.getElementById('instructor-phrase');
    phraseBox.textContent = pos.instructor_phrase;
    phraseBox.style.display = 'none';
    // Load instructor audio — include phrase as cache-buster so URL changes when phrase changes
    const audio = document.getElementById('instructor-audio');
    audio.onerror = () => { phraseBox.style.display = ''; };
    audio.src = `/api/instructor-audio?position=${_currentPos + 1}&key=${encodeURIComponent(_currentKey)}&p=${encodeURIComponent(pos.instructor_phrase)}`;
    audio.load();
    audio.play().catch(() => {});
    drawFretboard(pos.notes, -1);
  };

  // ── SVG fretboard renderer ───────────────────────────────────────────────
  const KEY_PC = {C:0, D:2, E:4, F:5, G:7, A:9, B:11, Bb:10, 'A#':10, Eb:3, 'D#':3};
  const PC_NAMES      = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];
  const PC_NAMES_FLAT = ['C','Db','D','Eb','E','F','Gb','G','Ab','A','Bb','B'];
  const FLAT_KEYS     = new Set(['F','Bb','Eb','Ab','Db','Gb']);
  // Standard guitar fret dot positions
  const FRET_MARKERS = new Set([3, 5, 7, 9, 12, 15, 17, 19, 21]);
  // Interval color map: root=hot-pink, major 3rd=red-orange, perfect 5th=hot-teal, other=grey
  const DOT_FILL  = { root: '#ff0080', third: '#fb5607', fifth: '#00e5cc', other: '#555555' };
  const DOT_TEXT  = { root: '#ffffff', third: '#ffffff', fifth: '#000000', other: '#ffffff' };
  const DOT_STROKE = { root: '#000000', third: '#000000', fifth: '#000000', other: '#333333' };
  const PLAYING_COLOR = '#ffe066';
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
    const rootPc = KEY_PC[_currentKey] ?? 0;
    const noteNames = FLAT_KEYS.has(_currentKey) ? PC_NAMES_FLAT : PC_NAMES;
    const sorted = (notes || []).slice().sort((a,b) => a.midi - b.midi);
    sorted.forEach((n, i) => {
      const row = n.string - 1;  // string 1→row 0 (top), string 6→row 5 (bottom)
      const y = TOP + row * strGap;
      const isOpen = n.fret === 0;
      const x = isOpen ? LEFT - 18 : LEFT + (n.fret - 0.5) * fretW;
      const isActive = i === activeIdx;
      const pc = n.midi % 12;
      const interval = (pc - rootPc + 12) % 12;
      const dotType = interval === 0 ? 'root' : interval === 4 ? 'third' : interval === 7 ? 'fifth' : 'other';
      const fill   = isActive ? PLAYING_COLOR : DOT_FILL[dotType];
      const textFill = isActive ? '#000000' : DOT_TEXT[dotType];
      const stroke = isActive ? '#000000' : DOT_STROKE[dotType];
      const r = isActive ? 10 : 9;
      const noteName = noteNames[pc];
      html += `<circle cx="${x}" cy="${y}" r="${r}" fill="${fill}" stroke="${stroke}" stroke-width="1" class="fret-dot${isActive?' playing':''}" data-note-idx="${i}"/>`;
      html += `<text x="${x}" y="${y + 4}" fill="${textFill}" text-anchor="middle" font-size="10" font-weight="bold" font-family="Segoe UI,sans-serif">${noteName}</text>`;
    });
    svg.innerHTML = html;
  };

  // ── Staff notation renderer (FR-20260530-guitar-trainer-staff-notation) ──
  const MAJOR_INTERVALS = [0, 2, 4, 5, 7, 9, 11, 12];
  const STAFF_COLORS = { root: '#ff0080', third: '#fb5607', fifth: '#00e5cc', other: '#555555' };
  const STAFF_TEXT   = { root: '#fff',    third: '#fff',    fifth: '#000',    other: '#fff'    };
  // Key signature accidental counts (positive = sharps, negative = flats)
  const KEY_SIGS = { C: 0, D: 2, Eb: -3, E: 4, F: -1, G: 1, Bb: -2, B: 5, 'A#': -2, 'D#': -3 };
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
    Eb: 2, Bb: 5, 'A#': 5, 'D#': 1, 'G#': 4, 'C#': 0, 'F#': 3,
  };
  // Bass clef: G2 at bottom line (Y=70); each diatonic step = -5px upward
  const BASS_STEP_FROM_G2 = {
    C: 3, D: 4, E: 5, F: 6, G: 0, A: 1, B: 2,
    Eb: 5, Bb: 1, 'A#': 1, 'D#': 4, 'G#': 0, 'C#': 3, 'F#': 6,
  };

  window.drawStaves = function(key, highlightMidi) {
    const rootPc   = KEY_PC[key] ?? 0;
    const useFlats = FLAT_KEYS.has(key);
    const noteNames = useFlats ? PC_NAMES_FLAT : PC_NAMES;
    drawSingleStaff('staff-treble-svg', key, 'treble', rootPc, noteNames, highlightMidi);
    drawSingleStaff('staff-bass-svg',   key, 'bass',   rootPc, noteNames, highlightMidi);
  };

  function drawSingleStaff(svgId, key, clef, rootPc, noteNames, highlightMidi) {
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
    // Root base-Y on the staff
    const rootStep = DIATONIC_STEP_FROM_C[key] ?? 0;
    const TREBLE_C4_Y = 80;
    const baseY = clef === 'treble'
      ? TREBLE_C4_Y - rootStep * 5
      : 70 - (BASS_STEP_FROM_G2[key] ?? 0) * 5;
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
    // Draw 8 diatonic note circles
    for (let idx = 0; idx < MAJOR_INTERVALS.length; idx++) {
      const interval = MAJOR_INTERVALS[idx];
      const pc       = (rootPc + interval) % 12;
      const noteName = noteNames[pc];
      const noteY    = baseY - idx * 5;
      const noteX    = noteXStart + idx * noteXSpacing;
      const degInterval = (pc - rootPc + 12) % 12;
      const colorKey = degInterval === 0 ? 'root' : degInterval === 4 ? 'third' : degInterval === 7 ? 'fifth' : 'other';
      const isHighlit = highlightMidi >= 0 && (pc === highlightMidi % 12);
      const noteFill  = isHighlit ? '#ffe066' : STAFF_COLORS[colorKey];
      const textFill  = isHighlit ? '#000'    : STAFF_TEXT[colorKey];
      // Ledger line if note is above/below staff
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

  async function playNote(midi, durationMs) {
    const ctx = getAudioCtx();
    if (ctx.state === 'suspended') await ctx.resume();
    const freq = {{ freq_table | tojson }}[midi];
    if (!freq) return;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
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
    const reps = Math.max(1, Math.min(20, parseInt(document.getElementById('scale-reps').value) || 4));
    const noteDurationMs = Math.round(60000 / _scaleBpm);
    const sorted = pos.notes.slice().sort((a, b) => a.midi - b.midi);
    // Deduplicate midi values for playback sequence
    const seen = new Set();
    const allAsc = [];
    for (const n of sorted) { if (!seen.has(n.midi)) { seen.add(n.midi); allAsc.push(n); } }
    // Start ascending run from the position root (lowest root-pitch-class note).
    // Each rep is a closed loop with no double root at the seam:
    // - rootIdx > 0 (C/A shape): desc goes all the way to the bottom, returnAsc
    //   climbs back to one below root; next rep opens on root.
    // - rootIdx = 0 (G/E/D shape): root IS the lowest note, so desc starts from
    //   allAsc[1] and stops one above root; no returnAsc needed.
    const rootPc   = KEY_PC[_currentKey] ?? 0;
    const rootNote = allAsc.find(n => n.midi % 12 === rootPc);
    const rootIdx  = rootNote ? allAsc.indexOf(rootNote) : 0;
    const asc       = allAsc.slice(rootIdx);
    const desc      = allAsc.slice(rootIdx === 0 ? 1 : 0, -1).reverse();
    const returnAsc = allAsc.slice(1, rootIdx);           // empty when rootIdx=0
    const sequence = [...asc, ...desc, ...returnAsc];
    _scalePlaying = true;
    _scaleStopFlag = false;
    const btn = document.getElementById('scale-play-btn');
    btn.textContent = '⏹ Stop';
    const status = document.getElementById('scale-status');
    for (let rep = 0; rep < reps && !_scaleStopFlag; rep++) {
      for (let i = 0; i < sequence.length && !_scaleStopFlag; i++) {
        status.textContent = `Rep ${rep + 1}/${reps} — note ${i + 1}/${sequence.length}`;
        drawFretboard(pos.notes, allAsc.indexOf(sequence[i]));
        drawStaves(_currentKey, sequence[i].midi);
        await playNote(sequence[i].midi, noteDurationMs * 0.85);
        await sleep(noteDurationMs);
      }
    }
    _scalePlaying = false;
    _scaleStopFlag = false;
    btn.textContent = '▶ Play';
    drawFretboard(pos.notes, -1);
    drawStaves(_currentKey, -1);
    status.textContent = _scaleStopFlag ? '' : '✓ Complete';
    if (!_scaleStopFlag) {
      logScaleSession(_currentKey + '_major', _currentPos + 1, _scaleBpm, reps, _currentKey);
    }
  };

  window.scaleSetBpm = function(v) {
    _scaleBpm = Math.max(40, Math.min(200, parseInt(v) || 60));
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

  async function logScaleSession(scale, position, bpm, reps, key) {
    try {
      const durEl = document.getElementById('scale-duration');
      const duration_minutes = durEl ? (parseInt(durEl.value) || 0) : 0;
      const r = await fetch('/api/scale-log', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({scale, position, bpm, reps, key: key || 'C', duration_minutes}),
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
        `<tr><td>${row.logged_at}</td><td>${row.key || 'C'}</td><td>${row.scale.replace('_',' ')}</td><td>${row.position}</td><td>${row.bpm}</td><td>${row.reps}</td></tr>`
      ).join('');
    } catch(e) { console.warn('scale log load failed', e); }
  }
})();
</script>
</body>
</html>
"""


@app.route("/art")
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


@app.route("/catalog")
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
    sessions = _list_sessions()
    log = _load_log()
    stats = get_practice_stats()
    return render_template_string(HTML, sessions=sessions, log=log, freq_table=MIDI_TO_FREQ, stats=stats)


@app.route("/save", methods=["POST"])
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


@app.route("/launch", methods=["POST"])
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


@app.route("/create", methods=["POST"])
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


@app.route("/api/sessions")
def api_sessions():
    return jsonify(_list_sessions())


@app.route("/api/log", methods=["GET", "POST"])
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


@app.route("/delete", methods=["POST"])
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
    """Return positions for the given key as JSON. Query param: ?key=C (default) or ?key=G."""
    key = request.args.get("key", "C").strip()
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


@app.route("/api/scale-log", methods=["GET", "POST"])
def api_scale_log():
    if request.method == "GET":
        try:
            with get_connection() as conn:
                rows = conn.execute(
                    "SELECT key, scale, position, bpm, reps, logged_at "
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
    try:
        duration_minutes = max(0, int(data.get("duration_minutes") or 0))
    except (TypeError, ValueError):
        duration_minutes = 0

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
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO scale_practice_log (key, scale, position, bpm, reps, duration_minutes) VALUES (?,?,?,?,?,?)",
                (key, scale, position, bpm, reps, duration_minutes),
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
    audio_path = get_instructor_audio(pos["instructor_phrase"], TTS_CACHE_DIR)
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
