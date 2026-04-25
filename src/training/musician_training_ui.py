"""
❤Music — Focused Musician Training UI
Flask web interface for managing and launching lead guitar training sessions.
Reads/writes JSON files in tools/tyJson/exercises/musicTraining/.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, render_template_string, request, Response, abort, send_from_directory

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRAINING_DIR = PROJECT_ROOT / "tools" / "tyJson" / "exercises" / "musicTraining"
LOG_FILE = TRAINING_DIR / "trainingLog.json"
CLICK_DIR = PROJECT_ROOT / "click"
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
    files = sorted(TRAINING_DIR.glob("*.json"))
    sessions = []
    for f in files:
        if f.name == "trainingLog.json" or f.name.startswith("_"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            sessions.append({
                "file": f.name,
                "title": data.get("title", f.stem),
                "artist": data.get("artist", ""),
                "song_path": data.get("songPath", ""),
                "gradient": data.get("gradient", 2),
                "segment_count": len(data.get("segments", [])),
                "segments": data.get("segments", []),
            })
        except Exception:
            pass
    return sessions


def _load_log() -> list[dict]:
    if LOG_FILE.exists():
        try:
            return json.loads(LOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save_session(filename: str, data: dict) -> None:
    path = TRAINING_DIR / filename
    path.write_text(json.dumps(data, indent=4), encoding="utf-8")


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
  .metro-dot.active-beat{background:#6fdc6f;box-shadow:0 0 4px #6fdc6f}</style>
</style>
</head>
<body>
<h1>🎸 Lead Guitar Trainer</h1>
<p class="sub">Focused interval training — loop lead parts, control speed, build muscle memory</p>

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
  <div class="card" id="card-{{ loop.index }}">
    {% if s.song_path %}
    <img class="album-art" src="/art?path={{ s.song_path | urlencode }}" onerror="this.style.display='none'" alt="">
    {% endif %}
    <div class="card-header">
      <div class="meta"><h2>{{ s.title }}</h2><div class="artist">{{ s.artist }}</div></div>
      <div class="card-controls">
        <label class="lock-label" title="Unlock to delete this training file">
          <input type="checkbox" onchange="toggleCardLock('{{ loop.index }}',this)"> 🔒
        </label>
        <button class="btn-del-card" id="del-card-{{ loop.index }}" onclick="deleteCard('{{ s.file }}','{{ loop.index }}')" title="Delete training file">🗑</button>
      </div>
    </div>
    <table>
      <thead><tr><th>Start</th><th>End</th><th>Speed%</th><th>Reps</th><th></th></tr></thead>
      <tbody id="tbody-{{ loop.index }}">
      {% for seg in s.segments %}
        <tr>
          <td><input value="{{ seg.start }}" data-field="start" style="width:70px" oninput="scheduleAutosave('{{ s.file }}','{{ loop.index }}')"></td>
          <td><input value="{{ seg.end }}" data-field="end" style="width:70px" oninput="scheduleAutosave('{{ s.file }}','{{ loop.index }}')"></td>
          <td><input type="number" value="{{ seg.get('speed',100) }}" data-field="speed" style="width:60px" min="10" max="200" oninput="scheduleAutosave('{{ s.file }}','{{ loop.index }}')"></td>
          <td><input type="number" value="{{ seg.get('repetition',1) }}" data-field="repetition" style="width:50px" min="0" oninput="scheduleAutosave('{{ s.file }}','{{ loop.index }}')"></td>
          <td><button class="btn-del" id="del-{{ loop.index }}-{{ loop.index0 }}" onclick="deleteRow(this,'{{ s.file }}','{{ loop.index }}')" title="Delete row">&times;</button></td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
    <div class="actions" style="align-items:center">
      <button class="btn btn-add" onclick="addRow('{{ s.file }}','tbody-{{ loop.index }}','{{ loop.index }}')">+ Row</button>
      <label style="font-size:.75rem;color:var(--muted);display:flex;align-items:center;gap:4px">
        Gradient
        <input type="number" id="gradient-{{ loop.index }}" value="{{ s.gradient }}"
               style="width:52px;background:#111;border:1px solid var(--border);color:#fff;padding:2px 4px;border-radius:3px;font-size:.8rem"
               min="0" max="50" step="1"
               oninput="scheduleAutosave('{{ s.file }}','{{ loop.index }}')\"></label>
      <button class="btn btn-red" onclick="launchSession('{{ s.file }}','{{ loop.index }}')">&#9654; Launch</button>
    </div>
    <div class="status" id="status-{{ loop.index }}"></div>
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
    <button class="btn btn-ghost" onclick="createSession()" style="width:100%">Create File</button>
    <div class="status" id="status-new"></div>
  </div>
</div>

<div class="log-section">
  <details>
    <summary>Practice Log{% if log %} <span style="font-weight:400;font-size:.8rem;color:var(--muted)">— {{ log|length }} session{{ 's' if log|length != 1 }}</span>{% endif %}</summary>
    {% if log %}
    <div class="log-scroll">
      {% for entry in log|reverse %}
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
      <p style="font-size:.75rem;color:var(--muted);padding:6px 0">Showing 20 of {{ log|length }} — older entries in trainingLog.json</p>
      {% endif %}
    </div>
    {% else %}
    <p style="color:var(--muted);font-size:.85rem;margin-top:8px">No sessions logged yet.</p>
    {% endif %}
  </details>
</div>

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

function getGradient(idx) {
  const el = document.getElementById('gradient-' + idx);
  return el ? (parseInt(el.value) || 0) : 0;
}

function toggleCardLock(idx, cb) {
  const btn = document.getElementById('del-card-' + idx);
  if (cb.checked) { btn.classList.add('unlocked'); } else { btn.classList.remove('unlocked'); }
}

async function deleteCard(filename, idx) {
  const btn = document.getElementById('del-card-' + idx);
  if (!btn.classList.contains('unlocked')) return;
  const res = await fetch('/delete', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ filename }) });
  const j = await res.json();
  if (j.ok) {
    document.getElementById('card-' + idx).remove();
  } else {
    alert('Delete failed: ' + j.error);
  }
}

function scheduleAutosave(filename, idx) {
  clearTimeout(_saveTimers[idx]);
  setStatus(idx, '...', true);
  _saveTimers[idx] = setTimeout(() => saveSession(filename, idx), 600);
}

function addRow(filename, tbodyId, idx) {
  const tbody = document.getElementById(tbodyId);
  const tr = document.createElement('tr');
  tr.innerHTML = `<td><input value="0:00" data-field="start" style="width:70px" oninput="scheduleAutosave('${filename}','${idx}')"></td><td><input value="0:10" data-field="end" style="width:70px" oninput="scheduleAutosave('${filename}','${idx}')"></td><td><input type="number" value="80" data-field="speed" style="width:60px" min="10" max="200" oninput="scheduleAutosave('${filename}','${idx}')"></td><td><input type="number" value="3" data-field="repetition" style="width:50px" min="0" oninput="scheduleAutosave('${filename}','${idx}')"></td><td><button class="btn-del" onclick="deleteRow(this,'${filename}','${idx}')" title="Delete row">&times;</button></td>`;
  tbody.appendChild(tr);
  scheduleAutosave(filename, idx);
}

function deleteRow(btn, filename, idx) {
  btn.closest('tr').remove();
  saveSession(filename, idx);
}

function setStatus(id, msg, ok=true) {
  const el = document.getElementById('status-' + id);
  if (el) { el.textContent = msg; el.style.color = ok ? '#6fdc6f' : '#f55'; }
}

async function saveSession(filename, idx) {
  const segs = getRows('tbody-' + idx);
  const gradient = getGradient(idx);
  const res = await fetch('/save', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ filename, segments: segs, gradient }) });
  const j = await res.json();
  setStatus(idx, j.ok ? '\u2713 Saved' : '\u2717 ' + j.error, j.ok);
}

async function launchSession(filename, idx) {
  // Flush current DOM state to disk before launching so that edits not yet
  // persisted by the autosave timer are included in the session. Without this,
  // changes made within the 600 ms autosave window would be silently ignored
  // and a stale on-disk version would be played instead. (FR-20260425)
  clearTimeout(_saveTimers[idx]);
  setStatus(idx, '\u23f3 Saving\u2026');
  await saveSession(filename, idx);
  setStatus(idx, '\u23f3 Launching\u2026');
  const gradient = getGradient(idx);
  const res = await fetch('/launch', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ filename, gradient }) });
  const j = await res.json();
  setStatus(idx, j.ok ? '\u25b6 Running in terminal' : '\u2717 ' + j.error, j.ok);
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

function buildCardHTML(s, idx) {
  const artTag = s.song_path
    ? `<img class="album-art" src="/art?path=${encodeURIComponent(s.song_path)}" onerror="this.style.display='none'" alt="">`
    : '';
  const rows = (s.segments || []).map((seg, i) => `
    <tr>
      <td><input value="${seg.start}" data-field="start" style="width:70px" oninput="scheduleAutosave('${s.file}','${idx}')"></td>
      <td><input value="${seg.end}" data-field="end" style="width:70px" oninput="scheduleAutosave('${s.file}','${idx}')"></td>
      <td><input type="number" value="${seg.speed||100}" data-field="speed" style="width:60px" min="10" max="200" oninput="scheduleAutosave('${s.file}','${idx}')"></td>
      <td><input type="number" value="${seg.repetition||1}" data-field="repetition" style="width:50px" min="0" oninput="scheduleAutosave('${s.file}','${idx}')"></td>
      <td><button class="btn-del" onclick="deleteRow(this,'${s.file}','${idx}')" title="Delete row">&times;</button></td>
    </tr>`).join('');
  return `<div class="card" id="card-${idx}">
    ${artTag}
    <div class="card-header">
      <div class="meta"><h2>${s.title}</h2><div class="artist">${s.artist}</div></div>
      <div class="card-controls">
        <label class="lock-label" title="Unlock to delete this training file">
          <input type="checkbox" onchange="toggleCardLock('${idx}',this)"> 🔒
        </label>
        <button class="btn-del-card" id="del-card-${idx}" onclick="deleteCard('${s.file}','${idx}')" title="Delete training file">🗑</button>
      </div>
    </div>
    <table>
      <thead><tr><th>Start</th><th>End</th><th>Speed%</th><th>Reps</th><th></th></tr></thead>
      <tbody id="tbody-${idx}">${rows}</tbody>
    </table>
    <div class="actions" style="align-items:center">
      <button class="btn btn-add" onclick="addRow('${s.file}','tbody-${idx}','${idx}')">+ Row</button>
      <label style="font-size:.75rem;color:var(--muted);display:flex;align-items:center;gap:4px">
        Gradient
        <input type="number" id="gradient-${idx}" value="${s.gradient||0}" style="width:52px;background:#111;border:1px solid var(--border);color:#fff;padding:2px 4px;border-radius:3px;font-size:.8rem" min="0" max="50" step="1" oninput="scheduleAutosave('${s.file}','${idx}')">
      </label>
      <button class="btn btn-red" onclick="launchSession('${s.file}','${idx}')">▶ Launch</button>
    </div>
    <div class="status" id="status-${idx}"></div>
  </div>`;
}

async function createSession() {
  if (!_selectedPath) { setStatus('new', '✗ Pick a song first', false); return; }
  const name = _selectedPath.split('\\').pop().split('/').pop();
  const bare = name.replace(/\.[^.]+$/, '');
  const parts = bare.split(' - ');
  const title = parts[0].trim();
  const artist = parts.length > 1 ? parts[parts.length - 1].trim() : '';
  const res = await fetch('/create', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ title, artist, songPath: _selectedPath }) });
  const j = await res.json();
  if (j.ok) {
    // Fetch updated session list and inject the new card without a page reload
    const sessRes = await fetch('/api/sessions');
    const sessions = await sessRes.json();
    const newSession = sessions.find(s => s.file === j.file);
    if (newSession) {
      const grid = document.getElementById('sessions-grid');
      const newCard = grid.querySelector('.new-card');
      const idx = sessions.indexOf(newSession) + 1;
      const div = document.createElement('div');
      div.innerHTML = buildCardHTML(newSession, idx);
      grid.insertBefore(div.firstElementChild, newCard);
    }
    setStatus('new', '✓ Created');
    _selectedPath = '';
    document.getElementById('new-selected').style.display = 'none';
    document.getElementById('new-selected-text').textContent = '';
    document.getElementById('new-path').value = '';
  } else { setStatus('new', '✗ ' + j.error, false); }
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
    return render_template_string(HTML, sessions=sessions, log=log)


@app.route("/save", methods=["POST"])
def save():
    data = request.get_json(force=True)
    filename = data.get("filename", "")
    if not filename or "/" in filename or "\\" in filename:
        return jsonify({"ok": False, "error": "Invalid filename"})
    path = TRAINING_DIR / filename
    if not path.exists():
        return jsonify({"ok": False, "error": "File not found"})
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
        existing["segments"] = data.get("segments", [])
        existing["gradient"] = int(round(float(data.get("gradient", 2))))
        path.write_text(json.dumps(existing, indent=4), encoding="utf-8")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/launch", methods=["POST"])
def launch():
    data = request.get_json(force=True)
    filename = data.get("filename", "")
    if not filename or "/" in filename or "\\" in filename:
        return jsonify({"ok": False, "error": "Invalid filename"})
    try:
        src_path = TRAINING_DIR / filename
        session = json.loads(src_path.read_text(encoding="utf-8"))
        gradient = int(round(float(data.get("gradient", session.get("gradient", 0)))))

        # Patch gradient into a temp JSON so focused_musician_training.py picks it up
        tmp = json.loads(json.dumps(session))
        tmp["gradient"] = gradient
        tmp_name = "_run_" + filename
        tmp_path = TRAINING_DIR / tmp_name
        tmp_path.write_text(json.dumps(tmp, indent=4), encoding="utf-8")

        tools_dir = str(PROJECT_ROOT / "tools").replace("\u2764", "$([char]0x2764)")
        tmp_name_safe = tmp_name  # no special chars in tmp_name
        ps_cmd = (
            f"$env:PYTHONUTF8='1'; "
            f"Set-Location \"{tools_dir}\"; "
            f"& 'C:\\G\\python.exe' 'focused_musician_training.py' '{tmp_name}'"
        )
        subprocess.Popen(
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
    safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in title).strip().replace(" ", "_").lower() + ".json"
    path = TRAINING_DIR / safe_name
    if path.exists():
        return jsonify({"ok": False, "error": f"{safe_name} already exists"})
    payload = {
        "songPath": song_path,
        "title": title,
        "artist": (data.get("artist") or "").strip(),
        "segments": [
            {"start": "0:05", "end": "0:15", "speed": 75, "repetition": 4}
        ],
    }
    path.write_text(json.dumps(payload, indent=4), encoding="utf-8")
    return jsonify({"ok": True, "file": safe_name})


@app.route("/api/sessions")
def api_sessions():
    return jsonify(_list_sessions())


@app.route("/api/log")
def api_log():
    return jsonify(_load_log())


@app.route("/delete", methods=["POST"])
def delete_session():
    data = request.get_json(force=True)
    filename = data.get("filename", "")
    if not filename or "/" in filename or "\\" in filename or not filename.endswith(".json"):
        return jsonify({"ok": False, "error": "Invalid filename"})
    path = TRAINING_DIR / filename
    if not path.exists():
        return jsonify({"ok": False, "error": "File not found"})
    try:
        path.unlink()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


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
