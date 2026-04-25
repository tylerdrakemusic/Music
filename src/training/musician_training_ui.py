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
from flask import Flask, jsonify, render_template_string, request

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRAINING_DIR = PROJECT_ROOT / "tools" / "tyJson" / "exercises" / "musicTraining"
LOG_FILE = TRAINING_DIR / "trainingLog.json"
PYTHON_EXE = r"C:\G\python.exe"
TRAINING_SCRIPT = PROJECT_ROOT / "tools" / "focused_musician_training.py"

MUZIC_DIR = Path(r"G:\Muzic")
AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".flac"}

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
</style>
</head>
<body>
<h1>🎸 Lead Guitar Trainer</h1>
<p class="sub">Focused interval training — loop lead parts, control speed, build muscle memory</p>

<div class="grid" id="sessions-grid">
  {% for s in sessions %}
  <div class="card" id="card-{{ loop.index }}">
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
    setStatus('new', '✓ Created — reload to edit');
    _selectedPath = '';
    document.getElementById('new-selected').style.display = 'none';
    document.getElementById('new-selected-text').textContent = '';
    document.getElementById('new-path').value = '';
  } else { setStatus('new', '✗ ' + j.error, false); }
}
</script>
</body>
</html>
"""


@app.route("/catalog")
def catalog():
    return jsonify(_scan_muzic())


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
