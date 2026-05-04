"""Studio Equipment Panel — Flask app on port 5060.

Run:
    C:\\G\\python.exe src/studio/studio_panel.py
    C:\\G\\python.exe src/studio/studio_panel.py --port 5060
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, jsonify, request, send_file  # noqa: E402
from utils.init_db import get_connection  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
MIC_CONFIG_PATH = ROOT / "studio" / "mic_config_template.html"

app = Flask(__name__)

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _get_conn():
    return get_connection()


def _ensure_table():
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS studio_equipment (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            studio_name TEXT NOT NULL,
            category    TEXT NOT NULL,
            label       TEXT NOT NULL,
            spec_json   TEXT NOT NULL DEFAULT '{}',
            status      TEXT NOT NULL DEFAULT 'active',
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/mic-config")
def mic_config():
    return send_file(str(MIC_CONFIG_PATH), mimetype="text/html")


@app.route("/api/equipment", methods=["GET"])
def list_equipment():
    studio_filter = request.args.get("studio")
    conn = _get_conn()
    try:
        if studio_filter:
            rows = conn.execute(
                "SELECT * FROM studio_equipment WHERE studio_name = ? ORDER BY category, label",
                (studio_filter,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM studio_equipment ORDER BY studio_name, category, label"
            ).fetchall()
        cols = [d[0] for d in conn.execute("SELECT * FROM studio_equipment LIMIT 0").description or []]
        # Use row_factory-style: rows are sqlite3.Row objects
        result = [dict(zip([c[0] for c in conn.execute("PRAGMA table_info(studio_equipment)").fetchall()], ())) for _ in []]
        # Build result properly
        col_names = ["id", "studio_name", "category", "label", "spec_json", "status", "created_at", "updated_at"]
        result = []
        for row in rows:
            item = dict(zip(col_names, row))
            try:
                item["specs"] = json.loads(item["spec_json"])
            except (json.JSONDecodeError, TypeError):
                item["specs"] = {}
            result.append(item)
        return jsonify(result)
    finally:
        conn.close()


@app.route("/api/equipment", methods=["POST"])
def create_equipment():
    data = request.get_json(force=True)
    required = ("studio_name", "category", "label")
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"Missing field: {field}"}), 400

    spec_raw = data.get("spec_json", "{}")
    if isinstance(spec_raw, dict):
        spec_raw = json.dumps(spec_raw)

    conn = _get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO studio_equipment (studio_name, category, label, spec_json, status)
               VALUES (?, ?, ?, ?, ?)""",
            (
                data["studio_name"],
                data["category"],
                data["label"],
                spec_raw,
                data.get("status", "active"),
            ),
        )
        conn.commit()
        new_id = cur.lastrowid
        row = conn.execute(
            "SELECT * FROM studio_equipment WHERE id = ?", (new_id,)
        ).fetchone()
        col_names = ["id", "studio_name", "category", "label", "spec_json", "status", "created_at", "updated_at"]
        return jsonify(dict(zip(col_names, row))), 201
    finally:
        conn.close()


@app.route("/api/equipment/<int:item_id>", methods=["PUT"])
def update_equipment(item_id: int):
    data = request.get_json(force=True)
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM studio_equipment WHERE id = ?", (item_id,)
        ).fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404

        fields = []
        values = []
        for field in ("studio_name", "category", "label", "spec_json", "status"):
            if field in data:
                val = data[field]
                if field == "spec_json" and isinstance(val, dict):
                    val = json.dumps(val)
                fields.append(f"{field} = ?")
                values.append(val)

        if not fields:
            return jsonify({"error": "No fields to update"}), 400

        fields.append("updated_at = datetime('now')")
        values.append(item_id)
        conn.execute(
            f"UPDATE studio_equipment SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM studio_equipment WHERE id = ?", (item_id,)
        ).fetchone()
        col_names = ["id", "studio_name", "category", "label", "spec_json", "status", "created_at", "updated_at"]
        return jsonify(dict(zip(col_names, row)))
    finally:
        conn.close()


@app.route("/api/equipment/<int:item_id>", methods=["DELETE"])
def delete_equipment(item_id: int):
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM studio_equipment WHERE id = ?", (item_id,)
        ).fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404
        conn.execute("DELETE FROM studio_equipment WHERE id = ?", (item_id,))
        conn.commit()
        return jsonify({"deleted": item_id})
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Main panel HTML
# ---------------------------------------------------------------------------

PANEL_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Studio Equipment Panel</title>
<style>
  :root {
    --bg: #0a0d12;
    --surface: #13171f;
    --surface2: #1c2130;
    --accent: #6366f1;
    --accent-hover: #818cf8;
    --danger: #ef4444;
    --text: #e2e8f0;
    --text-muted: #94a3b8;
    --border: #2d3748;
    --card-bg: #1a2035;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'Inter', system-ui, sans-serif; min-height: 100vh; }

  /* NAV */
  .nav { display: flex; gap: 0; border-bottom: 1px solid var(--border); background: var(--surface); padding: 0 1.5rem; }
  .nav-tab { padding: 0.85rem 1.4rem; cursor: pointer; color: var(--text-muted); font-size: 0.9rem; font-weight: 500;
             border-bottom: 3px solid transparent; transition: all 0.15s; user-select: none; }
  .nav-tab:hover { color: var(--text); background: rgba(255,255,255,0.04); }
  .nav-tab.active { color: var(--accent); border-bottom-color: var(--accent); }

  /* CONTENT */
  .tab-content { display: none; padding: 1.5rem; }
  .tab-content.active { display: block; }

  /* MIC CONFIG TAB */
  .mic-header { display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem; }
  .mic-header h2 { font-size: 1.1rem; color: var(--text); }
  .btn { padding: 0.5rem 1.1rem; border-radius: 6px; border: none; cursor: pointer; font-size: 0.85rem; font-weight: 600; transition: background 0.15s; }
  .btn-accent { background: var(--accent); color: #fff; }
  .btn-accent:hover { background: var(--accent-hover); }
  .btn-danger { background: var(--danger); color: #fff; }
  .btn-danger:hover { background: #dc2626; }
  .btn-ghost { background: var(--surface2); color: var(--text); border: 1px solid var(--border); }
  .btn-ghost:hover { background: var(--surface); }
  .mic-frame { width: 100%; height: calc(100vh - 160px); border: 1px solid var(--border); border-radius: 8px; background: #fff; }

  /* STUDIO TABS */
  .studio-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.5rem; }
  .studio-header h2 { font-size: 1.1rem; }
  .category-section { margin-bottom: 2rem; }
  .category-title { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; color: var(--accent);
                    border-bottom: 1px solid var(--border); padding-bottom: 0.4rem; margin-bottom: 0.75rem; }
  .equipment-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 0.75rem; }
  .eq-card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px; padding: 0.9rem 1rem; position: relative; }
  .eq-label { font-weight: 600; font-size: 0.92rem; margin-bottom: 0.4rem; }
  .eq-specs { font-size: 0.78rem; color: var(--text-muted); line-height: 1.5; }
  .eq-actions { display: flex; gap: 0.4rem; margin-top: 0.75rem; }
  .eq-actions button { padding: 0.3rem 0.65rem; font-size: 0.75rem; border-radius: 4px; }
  .confirm-row { display: flex; gap: 0.5rem; align-items: center; margin-top: 0.5rem; font-size: 0.8rem; }
  .loading { color: var(--text-muted); padding: 2rem; text-align: center; }

  /* MODAL */
  .modal-backdrop { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.7); z-index: 100; align-items: center; justify-content: center; }
  .modal-backdrop.open { display: flex; }
  .modal { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 1.5rem; width: 480px; max-width: 95vw; }
  .modal h3 { font-size: 1rem; margin-bottom: 1.2rem; }
  .form-row { margin-bottom: 1rem; }
  .form-row label { display: block; font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.35rem; }
  .form-row input, .form-row select, .form-row textarea {
    width: 100%; padding: 0.55rem 0.75rem; background: var(--bg); border: 1px solid var(--border);
    border-radius: 6px; color: var(--text); font-size: 0.88rem; outline: none;
  }
  .form-row input:focus, .form-row select, .form-row textarea:focus { border-color: var(--accent); }
  .form-row textarea { resize: vertical; min-height: 90px; font-family: monospace; }
  .modal-actions { display: flex; gap: 0.75rem; justify-content: flex-end; margin-top: 1.2rem; }
  select option { background: var(--surface); }
</style>
</head>
<body>

<nav class="nav">
  <div class="nav-tab active" data-tab="mic">🎙 Mic Config</div>
  <div class="nav-tab" data-tab="personal">🎛 Personal Studio</div>
  <div class="nav-tab" data-tab="hyperthreat">🏢 HyperThreat Studio</div>
</nav>

<!-- MIC CONFIG TAB -->
<div id="tab-mic" class="tab-content active">
  <div class="mic-header">
    <h2>Hyperthreat Studios — Mic Configuration</h2>
    <button class="btn btn-accent" onclick="window.open('/mic-config','_blank'); setTimeout(()=>{ let w=window.open('/mic-config','_blank'); if(w) w.onload=()=>w.print(); },100)">🖨 Print</button>
  </div>
  <iframe class="mic-frame" src="/mic-config" title="Mic Config"></iframe>
</div>

<!-- PERSONAL STUDIO TAB -->
<div id="tab-personal" class="tab-content">
  <div class="studio-header">
    <h2>🎛 Personal Studio</h2>
    <button class="btn btn-accent" onclick="openModal(null, 'Personal Studio')">＋ Add Equipment</button>
  </div>
  <div id="personal-content" class="loading">Loading…</div>
</div>

<!-- HYPERTHREAT TAB -->
<div id="tab-hyperthreat" class="tab-content">
  <div class="studio-header">
    <h2>🏢 HyperThreat Recording Studio</h2>
    <button class="btn btn-accent" onclick="openModal(null, 'HyperThreat Recording Studio')">＋ Add Equipment</button>
  </div>
  <div id="hyperthreat-content" class="loading">Loading…</div>
</div>

<!-- MODAL -->
<div class="modal-backdrop" id="modal">
  <div class="modal">
    <h3 id="modal-title">Add Equipment</h3>
    <div class="form-row">
      <label>Studio</label>
      <select id="f-studio">
        <option value="Personal Studio">Personal Studio</option>
        <option value="HyperThreat Recording Studio">HyperThreat Recording Studio</option>
      </select>
    </div>
    <div class="form-row">
      <label>Category</label>
      <input type="text" id="f-category" placeholder="e.g. Guitar, Microphone, Pedal…">
    </div>
    <div class="form-row">
      <label>Label</label>
      <input type="text" id="f-label" placeholder="e.g. Fender Stratocaster">
    </div>
    <div class="form-row">
      <label>Specs (JSON)</label>
      <textarea id="f-spec" placeholder='{"type": "Electric Guitar", "serial_number": "12345"}'></textarea>
    </div>
    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="closeModal()">Cancel</button>
      <button class="btn btn-accent" onclick="saveModal()">Save</button>
    </div>
  </div>
</div>

<script>
const STUDIOS = {
  personal: 'Personal Studio',
  hyperthreat: 'HyperThreat Recording Studio'
};

// Tab switching
document.querySelectorAll('.nav-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    tab.classList.add('active');
    const id = 'tab-' + tab.dataset.tab;
    document.getElementById(id).classList.add('active');
    if (tab.dataset.tab === 'personal') loadStudio('personal');
    if (tab.dataset.tab === 'hyperthreat') loadStudio('hyperthreat');
  });
});

// Load studio data
async function loadStudio(studioKey) {
  const studioName = STUDIOS[studioKey];
  const el = document.getElementById(studioKey + '-content');
  el.innerHTML = '<div class="loading">Loading…</div>';
  const res = await fetch('/api/equipment?studio=' + encodeURIComponent(studioName));
  const data = await res.json();
  renderStudio(el, data, studioName);
}

function renderStudio(el, items, studioName) {
  if (!items.length) {
    el.innerHTML = '<div class="loading">No equipment yet. Add some!</div>';
    return;
  }
  // Group by category
  const groups = {};
  items.forEach(item => {
    if (!groups[item.category]) groups[item.category] = [];
    groups[item.category].push(item);
  });
  let html = '';
  Object.keys(groups).sort().forEach(cat => {
    html += `<div class="category-section"><div class="category-title">${escHtml(cat)}</div><div class="equipment-grid">`;
    groups[cat].forEach(item => {
      const specs = item.specs || {};
      const specLines = Object.entries(specs)
        .filter(([k]) => !['manufacturer','model_name','make_and_model','replacement_consideration'].includes(k))
        .slice(0, 5)
        .map(([k, v]) => `<span>${escHtml(k.replace(/_/g,' '))}: <b>${escHtml(String(v))}</b></span>`)
        .join('<br>');
      html += `
        <div class="eq-card" id="card-${item.id}">
          <div class="eq-label">${escHtml(item.label)}</div>
          <div class="eq-specs">${specLines}</div>
          <div class="eq-actions">
            <button class="btn btn-ghost" onclick="openModal(${item.id})">✏️ Edit</button>
            <button class="btn btn-danger" onclick="confirmDelete(${item.id}, ${JSON.stringify(item.label)})">🗑 Delete</button>
          </div>
          <div class="confirm-row" id="confirm-${item.id}" style="display:none">
            Delete <b>${escHtml(item.label)}</b>?
            <button class="btn btn-danger" onclick="doDelete(${item.id})">Yes</button>
            <button class="btn btn-ghost" onclick="document.getElementById('confirm-${item.id}').style.display='none'">No</button>
          </div>
        </div>`;
    });
    html += '</div></div>';
  });
  el.innerHTML = html;
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// Modal state
let _editId = null;
let _defaultStudio = null;

function openModal(id, defaultStudio) {
  _editId = id || null;
  _defaultStudio = defaultStudio || null;
  document.getElementById('modal-title').textContent = id ? 'Edit Equipment' : 'Add Equipment';
  document.getElementById('f-studio').value = defaultStudio || 'Personal Studio';
  document.getElementById('f-category').value = '';
  document.getElementById('f-label').value = '';
  document.getElementById('f-spec').value = '{}';

  if (id) {
    // pre-fill from DOM data
    fetch('/api/equipment').then(r => r.json()).then(data => {
      const item = data.find(i => i.id === id);
      if (item) {
        document.getElementById('f-studio').value = item.studio_name;
        document.getElementById('f-category').value = item.category;
        document.getElementById('f-label').value = item.label;
        document.getElementById('f-spec').value = JSON.stringify(item.specs || {}, null, 2);
      }
    });
  }
  document.getElementById('modal').classList.add('open');
}

function closeModal() {
  document.getElementById('modal').classList.remove('open');
}

async function saveModal() {
  const studio = document.getElementById('f-studio').value.trim();
  const category = document.getElementById('f-category').value.trim();
  const label = document.getElementById('f-label').value.trim();
  const specRaw = document.getElementById('f-spec').value.trim();

  if (!studio || !category || !label) { alert('Studio, Category, and Label are required.'); return; }

  let specObj = {};
  try { specObj = JSON.parse(specRaw || '{}'); } catch { alert('Spec must be valid JSON.'); return; }

  const payload = { studio_name: studio, category, label, spec_json: JSON.stringify(specObj) };
  let res;
  if (_editId) {
    res = await fetch('/api/equipment/' + _editId, { method: 'PUT', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) });
  } else {
    res = await fetch('/api/equipment', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) });
  }
  if (res.ok) {
    closeModal();
    // Refresh the visible studio tab
    const activeTab = document.querySelector('.nav-tab.active');
    if (activeTab && activeTab.dataset.tab !== 'mic') loadStudio(activeTab.dataset.tab);
  } else {
    const err = await res.json();
    alert('Error: ' + (err.error || 'Unknown'));
  }
}

function confirmDelete(id, label) {
  document.getElementById('confirm-' + id).style.display = 'flex';
}

async function doDelete(id) {
  const res = await fetch('/api/equipment/' + id, { method: 'DELETE' });
  if (res.ok) {
    const activeTab = document.querySelector('.nav-tab.active');
    if (activeTab && activeTab.dataset.tab !== 'mic') loadStudio(activeTab.dataset.tab);
  } else {
    alert('Delete failed.');
  }
}

// Close modal on backdrop click
document.getElementById('modal').addEventListener('click', e => {
  if (e.target === document.getElementById('modal')) closeModal();
});
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return PANEL_HTML


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5060)
    args = parser.parse_args()
    _ensure_table()
    app.run(port=args.port, debug=False)
