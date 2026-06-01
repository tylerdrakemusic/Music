"""Generate a standalone Band Management Panel HTML.

Reads catalog_export.json + setlist_active_export.json, builds BM_INLINE,
and writes reports/band_management_panel.html — a fully self-contained dark
panel that can be served as a static_html iframe in the workspace portal.

Usage:
    C:\\G\\python.exe src/band_mgmt/generate_band_mgmt_panel.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Vera portrait (lazy import to keep panel generation working even if vera_portrait errors)
def _get_vera_tag() -> str:
    """Return Vera's portrait <img> tag, or empty string on any error."""
    try:
        _src = Path(__file__).resolve().parents[1] / "utils" / "vera_portrait.py"
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location("_vera_portrait", _src)
        if _spec and _spec.loader:
            _mod = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
            return _mod.get_portrait_img_tag(max_width=160)  # type: ignore[attr-defined]
    except Exception as _exc:
        print(f"  [WARN] Vera portrait unavailable: {_exc}", file=sys.stderr)
    return ""

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CATALOG_JSON = PROJECT_ROOT / "catalog" / "setlists" / "catalog_export.json"
SETLIST_JSON = PROJECT_ROOT / "catalog" / "setlists" / "setlist_active_export.json"
OUTPUT_HTML = PROJECT_ROOT / "reports" / "band_management_panel.html"
OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)

# Roots for --serve mode local-file endpoints (see _resolve_audio_path / _resolve_sheet_path)
AUDIO_ROOT: Path = Path("G:/Muzic")
SHEETS_ROOT: Path = PROJECT_ROOT / "catalog" / "sheet_music"


# ---------------------------------------------------------------------------
# Path-validation helpers for --serve mode file-serving endpoints
# ---------------------------------------------------------------------------

def _resolve_audio_path(raw: str) -> Path:
    """URL-decode *raw* and resolve it relative to AUDIO_ROOT.

    Raises ``ValueError`` on any path-traversal attempt.
    """
    from urllib.parse import unquote
    filename = unquote(raw)
    if ".." in filename.split("/") or ".." in filename.split("\\"):
        raise ValueError(f"Path traversal detected in audio path: {filename!r}")
    resolved = (AUDIO_ROOT / filename).resolve()
    try:
        resolved.relative_to(AUDIO_ROOT.resolve())
    except ValueError:
        raise ValueError(f"Path traversal detected in audio path: {filename!r}")
    return resolved


def _resolve_sheet_path(raw: str) -> Path:
    """URL-decode *raw* and resolve it relative to SHEETS_ROOT.

    Raises ``ValueError`` on any path-traversal attempt.
    """
    from urllib.parse import unquote
    relpath = unquote(raw)
    if ".." in relpath.split("/") or ".." in relpath.split("\\"):
        raise ValueError(f"Path traversal detected in sheet path: {relpath!r}")
    resolved = (SHEETS_ROOT / relpath).resolve()
    try:
        resolved.relative_to(SHEETS_ROOT.resolve())
    except ValueError:
        raise ValueError(f"Path traversal detected in sheet path: {relpath!r}")
    return resolved


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

def load_inline_data() -> dict:
    """Build BM_INLINE from flat catalog/setlist exports.

    BM_INLINE format expected by the JS:
      { "exported_at": str, "bands": [ { "id": int, "name": str, "active": bool,
          "genre": str, "catalog": {"count": int, "songs": [...]},
          "setlist": {"setlist": {...}, "count": int, "songs": [...]} }, ... ] }
    """
    catalog_raw: dict = {}
    setlist_raw: dict = {}
    try:
        catalog_raw = json.loads(CATALOG_JSON.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [WARN] Could not read catalog_export.json: {e}", file=sys.stderr)
    try:
        setlist_raw = json.loads(SETLIST_JSON.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [WARN] Could not read setlist_active_export.json: {e}", file=sys.stderr)

    exported_at = catalog_raw.get("exported_at", setlist_raw.get("exported_at", ""))
    catalog_songs = catalog_raw.get("songs", [])
    setlist_songs = setlist_raw.get("songs", [])
    setlist_meta = setlist_raw.get("setlist", {})

    # Catalog is Copper Creek (id=1). Groove Unit uses catalog_id = 2 in setlist
    # if no songs reference id=2, the band simply shows empty.
    cc_songs = [s for s in catalog_songs]  # all catalog songs are Copper Creek
    gu_songs: list = []  # The Groove Unit — no separate catalog export yet

    bands = [
        {
            "id": 1,
            "name": "Copper Creek",
            "active": True,
            "genre": "Country / Americana",
            "catalog": {"count": len(cc_songs), "songs": cc_songs},
            "setlist": {
                "setlist": setlist_meta,
                "count": len(setlist_songs),
                "songs": setlist_songs,
            },
        },
        {
            "id": 2,
            "name": "The Groove Unit",
            "active": True,
            "genre": "Blues / Rock",
            "catalog": {"count": len(gu_songs), "songs": gu_songs},
            "setlist": {"setlist": {}, "count": 0, "songs": []},
        },
    ]
    return {"exported_at": exported_at, "bands": bands}


def load_inventory_data() -> list:
    """Load gig_inventory items from heartmusic.db.

    Falls back to hardcoded seed list if DB is unavailable.
    """
    _FALLBACK = [
        {"id": 1,  "item": "Guitar",         "category": "Guitar",        "sort_order": 1},
        {"id": 2,  "item": "Guitar Stand",   "category": "Guitar",        "sort_order": 2},
        {"id": 3,  "item": "Amp",            "category": "Amplification", "sort_order": 3},
        {"id": 4,  "item": "Amp stand",      "category": "Amplification", "sort_order": 4},
        {"id": 5,  "item": "Trombone",       "category": "Horn",          "sort_order": 5},
        {"id": 6,  "item": "Trombone stand", "category": "Horn",          "sort_order": 6},
        {"id": 7,  "item": "Music Stand",    "category": "Accessories",   "sort_order": 7},
        {"id": 8,  "item": "Gig Bag",        "category": "Accessories",   "sort_order": 8},
        {"id": 9,  "item": "Sheet Music",    "category": "Accessories",   "sort_order": 9},
        {"id": 10, "item": "Pedal Board",    "category": "Accessories",   "sort_order": 10},
        {"id": 11, "item": "Lights",         "category": "Accessories",   "sort_order": 11},
    ]
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "src"))
        from utils.init_db import get_connection  # noqa: PLC0415
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, item, category, sort_order FROM gig_inventory ORDER BY sort_order, id"
        ).fetchall()
        conn.close()
        if rows:
            return [
                {
                    "id": r["id"],
                    "item": r["item"],
                    "category": r["category"] or "General",
                    "sort_order": r["sort_order"],
                }
                for r in rows
            ]
    except Exception as e:
        print(f"  [WARN] Could not load gig_inventory from DB: {e}", file=sys.stderr)
    return _FALLBACK


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

CSS_VARS = """
:root {
    --bg: #0a0d12;
    --bg2: #1e2530;
    --sidebar-bg: #0f1318;
    --surface: #151a22;
    --border: #1e2530;
    --accent: #6366f1;
    --accent-glow: rgba(99,102,241,0.15);
    --text: #e2e8f0;
    --muted: #64748b;
    --success: #10b981;
    --warning: #f59e0b;
    --live-dot: #ef4444;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg); color: var(--text); }
"""

PANEL_CSS = """
  .bm-wrap { display:flex; flex-direction:column; height:100vh; background:var(--bg); overflow:hidden; }
  .bm-header { padding:1rem 1.5rem 0.75rem; border-bottom:1px solid var(--border); flex-shrink:0; position:relative; }
  .bm-vera-portrait { position:absolute; top:0.6rem; right:1.25rem; display:inline-block; }
  .vera-edit-btn { position:absolute; bottom:4px; right:4px; background:rgba(0,0,0,.65); border:none; border-radius:50%; width:24px; height:24px; font-size:12px; color:#c9a96e; cursor:pointer; display:flex; align-items:center; justify-content:center; opacity:0.35; transition:opacity .15s; padding:0; line-height:1; }
  .vera-edit-btn:hover { opacity:0.95 !important; }
  .vera-modal-overlay { display:none; position:fixed; inset:0; background:rgba(0,0,0,.72); z-index:9999; align-items:center; justify-content:center; }
  .vera-modal-overlay.open { display:flex; }
  .vera-modal-card { background:#1a1f2e; border:1px solid #334155; border-radius:14px; padding:1.5rem; width:min(680px,90vw); max-height:90vh; overflow-y:auto; position:relative; box-shadow:0 24px 60px rgba(0,0,0,.7); }
  .vera-modal-card h2 { font-size:1.1rem; font-weight:700; color:#e2e8f0; margin-bottom:1rem; }
  .vera-modal-close { position:absolute; top:0.75rem; right:0.9rem; background:none; border:none; color:#94a3b8; font-size:1.4rem; cursor:pointer; line-height:1; padding:0; }
  .vera-modal-close:hover { color:#e2e8f0; }
  .vera-modal-label { display:block; font-size:0.78rem; font-weight:600; color:#94a3b8; margin-bottom:0.3rem; text-transform:uppercase; letter-spacing:.05em; }
  .vera-modal-card textarea { width:100%; background:#0f1318; border:1px solid #334155; border-radius:8px; color:#e2e8f0; font-size:0.82rem; padding:0.65rem 0.75rem; font-family:inherit; resize:vertical; outline:none; }
  .vera-modal-card textarea:focus { border-color:#6366f1; }
  .vera-modal-card select { background:#1e2530; border:1px solid #334155; border-radius:6px; color:#e2e8f0; font-size:0.82rem; padding:0.3rem 0.6rem; cursor:pointer; outline:none; margin-bottom:0.75rem; }
  .vera-modal-actions { display:flex; gap:0.6rem; margin-top:0.75rem; flex-wrap:wrap; }
  .vera-btn-save { background:linear-gradient(135deg,#6366f1,#818cf8); color:#fff; border:none; border-radius:8px; padding:0.45rem 1.1rem; font-size:0.88rem; font-weight:600; cursor:pointer; }
  .vera-btn-regen { background:linear-gradient(135deg,#10b981,#059669); color:#fff; border:none; border-radius:8px; padding:0.45rem 1.1rem; font-size:0.88rem; font-weight:600; cursor:pointer; }
  .vera-btn-cancel { background:transparent; border:1px solid #334155; color:#94a3b8; border-radius:8px; padding:0.45rem 1.1rem; font-size:0.88rem; font-weight:600; cursor:pointer; }
  .vera-modal-actions button:disabled { opacity:0.5; cursor:wait; }
  .vera-modal-status { font-size:0.8rem; margin-top:0.5rem; color:#94a3b8; min-height:1.2em; }
  .bm-title { font-size:1.25rem; font-weight:700; display:flex; align-items:center; gap:0.5rem; }
  .bm-subtitle { font-size:0.7rem; color:var(--muted); margin-left:0.4rem; font-weight:400; }
  .bm-meta { font-size:0.72rem; color:var(--muted); margin-top:0.25rem; display:flex; gap:1.2rem; flex-wrap:wrap; }
  .bm-view-toggle { display:flex; gap:0.4rem; margin-top:0.5rem; }
  .bm-vtab { background:var(--surface); border:1px solid var(--border); border-radius:6px; padding:0.25rem 0.9rem; font-size:0.78rem; color:var(--muted); cursor:pointer; user-select:none; transition:all .15s; font-weight:600; }
  .bm-vtab.active { background:rgba(99,102,241,.2); border-color:var(--accent); color:#a5b4fc; }
  .bm-controls { padding:0.65rem 1.5rem; border-bottom:1px solid var(--border); display:flex; align-items:center; gap:0.75rem; flex-wrap:wrap; flex-shrink:0; }
  .bm-search { background:var(--surface); border:1px solid var(--border); border-radius:6px; padding:0.35rem 0.7rem; color:var(--text); font-size:0.82rem; outline:none; width:220px; }
  .bm-search:focus { border-color:var(--accent); }
  .bm-tabs { display:flex; gap:0.4rem; }
  .bm-tab { background:var(--surface); border:1px solid var(--border); border-radius:20px; padding:0.2rem 0.75rem; font-size:0.75rem; color:var(--muted); cursor:pointer; user-select:none; transition:all .15s; }
  .bm-tab.active { background:rgba(99,102,241,.15); border-color:var(--accent); color:#818cf8; }
  .bm-stat-chips { display:flex; gap:0.4rem; margin-left:auto; flex-wrap:wrap; }
  .bm-chip { background:var(--surface); border:1px solid var(--border); border-radius:6px; padding:0.15rem 0.5rem; font-size:0.68rem; color:var(--muted); }
  .bm-chip b { color:var(--text); }
  .bm-table-wrap { flex:1; overflow-y:auto; padding:0.5rem 1.5rem 1.5rem; }
  .bm-table { width:100%; border-collapse:collapse; font-size:0.82rem; }
  .bm-table th { position:sticky; top:0; background:var(--sidebar-bg); color:var(--muted); font-size:0.68rem; font-weight:700; text-transform:uppercase; letter-spacing:.06em; padding:0.5rem 0.6rem; text-align:left; border-bottom:1px solid var(--border); cursor:pointer; user-select:none; white-space:nowrap; }
  .bm-table th:hover { color:var(--text); }
  .bm-table th .sort-arrow { opacity:0.4; margin-left:0.3rem; font-size:0.6rem; }
  .bm-table th.sorted .sort-arrow { opacity:1; color:var(--accent); }
  .bm-table td { padding:0.45rem 0.6rem; border-bottom:1px solid var(--border); vertical-align:middle; }
  .bm-table tr:hover td { background:var(--accent-glow); }
  .bm-set-header td { background:var(--surface); color:var(--muted); font-size:0.7rem; font-weight:700; text-transform:uppercase; letter-spacing:.08em; padding:0.4rem 0.6rem; }
  .bm-play-btn { background:none; border:1px solid var(--border); color:var(--accent); border-radius:4px; padding:0 0.45rem; height:1.5rem; cursor:pointer; font-size:0.78rem; line-height:1; transition:background .15s,border-color .15s; white-space:nowrap; }
  .bm-play-btn:hover { background:var(--accent-glow,rgba(99,102,241,.15)); border-color:var(--accent); }
  .bm-play-btn.playing { border-color:var(--accent); color:#fff; background:var(--accent); }
  .bm-progress { width:62px; height:3px; cursor:pointer; accent-color:var(--accent); vertical-align:middle; margin-left:5px; }
  .key-badge { display:inline-block; padding:0.15rem 0.45rem; border-radius:4px; font-size:0.72rem; font-weight:700; letter-spacing:.03em; }
  .key-major { background:rgba(16,185,129,.15); color:#34d399; }
  .key-minor { background:rgba(99,102,241,.15); color:#818cf8; }
  .bpm-val { font-family:'Cascadia Code','Consolas',monospace; font-size:0.8rem; }
  .bpm-unknown { color:var(--muted); font-style:italic; }
  .bm-footer { padding:0.5rem 1.5rem; border-top:1px solid var(--border); font-size:0.68rem; color:var(--muted); display:flex; gap:1rem; align-items:center; flex-shrink:0; }
  .bm-footer a { color:var(--accent); text-decoration:none; }
  .bm-footer a:hover { text-decoration:underline; }
  .bm-no-results { text-align:center; padding:3rem; color:var(--muted); }
  @media print {
    html, body { background:#fff !important; color:#000 !important; height:auto !important; min-height:0 !important; }
    body > * { display:none !important; }
    #bm-print-area { display:block !important; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; color:#000; background:#fff; }
    #bm-print-area h1 { font-size:1.4rem; margin-bottom:.25rem; }
    #bm-print-area h2 { font-size:1.1rem; font-weight:600; margin-bottom:.2rem; }
    #bm-print-area p { font-size:.85rem; color:#444; margin-bottom:.75rem; }
    #bm-print-area table { width:100%; border-collapse:collapse; font-size:.82rem; }
    #bm-print-area th { border-bottom:2px solid #000; padding:.3rem .5rem; text-align:left; font-size:.7rem; text-transform:uppercase; letter-spacing:.06em; }
    #bm-print-area td { padding:.3rem .5rem; border-bottom:1px solid #ddd; }
    #bm-print-area tr.bm-print-set-header td { background:#f0f0f0; font-weight:700; font-size:.72rem; text-transform:uppercase; letter-spacing:.08em; padding:.25rem .5rem; border-bottom:1px solid #bbb; }
    #bm-print-area .bm-print-footer { font-size:.7rem; color:#888; margin-top:.75rem; }
  }
  .bm-loading { text-align:center; padding:3rem; color:var(--muted); font-style:italic; }
  .bm-err { text-align:center; padding:2rem; color:#f87171; background:rgba(239,68,68,.08); border-radius:8px; margin:1rem; }
  /* Gig Inventory tab */
  #bm-inv-section { padding:0.5rem 1.5rem 1.5rem; overflow-y:auto; }
  .bm-inv-table { width:100%; border-collapse:collapse; font-size:0.82rem; }
  .bm-inv-table th { position:sticky; top:0; background:var(--sidebar-bg); color:var(--muted); font-size:0.68rem; font-weight:700; text-transform:uppercase; letter-spacing:.06em; padding:0.5rem 0.6rem; text-align:left; border-bottom:1px solid var(--border); white-space:nowrap; }
  .bm-inv-table td { padding:0.45rem 0.6rem; border-bottom:1px solid var(--border); vertical-align:middle; }
  .bm-inv-table tr:hover td { background:var(--accent-glow); }
  .bm-inv-cb { width:16px; height:16px; cursor:pointer; accent-color:var(--accent); }
  .bm-inv-cat { display:inline-block; background:var(--surface); border:1px solid var(--border); border-radius:4px; padding:0.1rem 0.45rem; font-size:0.72rem; color:var(--muted); }
  .bm-inv-remove-btn { background:none; border:none; color:#e74c3c; border-radius:4px; padding:0 6px; cursor:pointer; font-size:1.1em; line-height:1; font-weight:700; transition:color .15s,background .15s; }
  .bm-inv-remove-btn:hover { color:#ff6b6b; background:rgba(231,76,60,.12); border-radius:3px; }
  .bm-inv-btn { background:var(--surface); border:1px solid var(--border); border-radius:5px; color:var(--text); padding:0.3rem 0.75rem; font-size:0.78rem; cursor:pointer; transition:background .15s,border-color .15s; }
  .bm-inv-btn:hover { background:var(--accent-glow); border-color:var(--accent); color:#a5b4fc; }
  .bm-inv-editable { cursor:pointer; }
  .bm-inv-editable:hover { opacity:.75; text-decoration:underline dotted; }
  @media print {
    #bm-inv-print-area { display:block !important; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; color:#000; background:#fff; }
    #bm-inv-print-area h1 { font-size:1.4rem; margin-bottom:.25rem; }
    #bm-inv-print-area table { width:100%; border-collapse:collapse; font-size:.82rem; margin-top:.5rem; }
    #bm-inv-print-area th { border-bottom:2px solid #000; padding:.3rem .5rem; text-align:left; font-size:.7rem; text-transform:uppercase; letter-spacing:.06em; }
    #bm-inv-print-area td { padding:.3rem .5rem; border-bottom:1px solid #ddd; }
    #bm-inv-print-area .inv-cb-cell { text-align:center; }
  }
"""

BAND_SELECT_STYLE = (
    "background:var(--bg2,#2a2a2a);border:1px solid var(--accent,#7ecfff);"
    "border-radius:5px;color:var(--text);font-size:inherit;font-weight:700;"
    "cursor:pointer;outline:none;padding:.15rem .5rem .15rem .4rem;"
    "appearance:auto;-webkit-appearance:auto"
)

PANEL_BODY = f"""
<div class="bm-wrap">
  <div class="bm-header">
    <div class="bm-title">&#x1F3B5; Band Management &mdash;
      <select id="bm-band-select" onchange="bmSwitchBand(this.value)" style="{BAND_SELECT_STYLE}"></select>
      <span class="bm-subtitle" id="bm-view-label">&middot; Active Setlist</span>
    </div>
    <div class="bm-view-toggle">
      <span class="bm-vtab active" id="vtab-setlist" onclick="bmSwitchView('setlist',this)">&#x1F3A4; Active Setlist</span>
      <span class="bm-vtab" id="vtab-catalog" onclick="bmSwitchView('catalog',this)">&#x1F4DA; Full Catalog</span>
      <span class="bm-vtab" id="vtab-inventory" onclick="bmSwitchView('inventory',this)">&#x1F4E6; Gig Inventory</span>
      <button id="bm-print-btn" onclick="bmPrintSetlist()" style="background:var(--accent);color:#fff;border:none;border-radius:5px;padding:.3rem .8rem;font-size:.8rem;cursor:pointer;margin-left:.5rem;">&#x1F5A8; Print Setlist</button>
      <button id="bm-print-inv-btn" onclick="bmPrintInventory()" style="background:var(--accent);color:#fff;border:none;border-radius:5px;padding:.3rem .8rem;font-size:.8rem;cursor:pointer;margin-left:.25rem;display:none;">&#x1F5A8; Print Inventory</button>
    </div>
    <div class="bm-meta" id="bm-meta"></div>
  </div>
  <div class="bm-controls">
    <input class="bm-search" id="bm-search" placeholder="Search songs, artists, keys&hellip;" oninput="applyFilter()">
    <div class="bm-tabs" id="bm-set-tabs"></div>
    <div class="bm-stat-chips" id="bm-stat-chips"></div>
  </div>
  <div class="bm-table-wrap">
    <div class="bm-loading" id="bm-loading">Loading&hellip;</div>
    <table class="bm-table" id="bm-table" style="display:none">
      <thead id="bm-thead"></thead>
      <tbody id="bm-tbody"></tbody>
    </table>
    <div class="bm-no-results" id="bm-no-results" style="display:none">No songs match your search.</div>
    <div class="bm-err" id="bm-err" style="display:none"></div>
    <div id="bm-inv-section" style="display:none"></div>
  </div>
  <div class="bm-footer">
    BPM: librosa on <code>G:\\Muzic</code> &middot;
    Source: catalog_export.json &middot; setlist_active_export.json &middot;
    <span id="bm-sort-info" style="color:var(--muted)">Default order</span>
  </div>
  <audio id="bm-audio" preload="none"></audio>
</div>
<div id="bm-print-area" style="display:none"></div>
<div id="bm-inv-print-area" style="display:none"></div>
"""

BM_JS = r"""
(function(){
  // BM_INLINE injected by generate_band_mgmt_panel.py
  // <!--BM_DATA_START-->
  const BM_INLINE = /*INJECT_DATA*/null/*END_INJECT*/;
  // <!--BM_DATA_END-->
  var BM_INVENTORY = /*INJECT_INVENTORY*/[]/*END_INJECT_INVENTORY*/;

  let currentView = 'setlist';
  let currentBandId = null;
  let allSongs = [];
  let activeSet = 'all';
  let sortCol = null;
  let sortAsc = true;
  let dataCache = {};

  function getBandData(bandId) {
    if (!BM_INLINE || !BM_INLINE.bands) return null;
    return BM_INLINE.bands.find(function(b){ return b.id == bandId; }) || null;
  }

  function populateBandSelect() {
    const sel = document.getElementById('bm-band-select');
    if (!BM_INLINE || !BM_INLINE.bands) return;
    sel.innerHTML = '';
    BM_INLINE.bands.forEach(function(b) {
      const opt = document.createElement('option');
      opt.value = b.id;
      opt.textContent = b.name + (b.active ? '' : ' (inactive)');
      sel.appendChild(opt);
    });
    currentBandId = BM_INLINE.bands[0] ? BM_INLINE.bands[0].id : null;
    sel.value = currentBandId;
  }

  window.bmSwitchBand = function(bandId) {
    currentBandId = parseInt(bandId);
    dataCache = {};
    document.getElementById('bm-search').value = '';
    activeSet = 'all';
    sortCol = null; sortAsc = true;
    loadView(currentView);
  };

  window.bmSwitchView = function(view, el) {
    currentView = view;
    document.querySelectorAll('.bm-vtab').forEach(function(t){ t.classList.remove('active'); });
    el.classList.add('active');
    var labels = {setlist: '\u00b7 Active Setlist', catalog: '\u00b7 Full Catalog', inventory: '\u00b7 Gig Inventory'};
    document.getElementById('bm-view-label').textContent = labels[view] || '';
    var printBtn = document.getElementById('bm-print-btn');
    if (printBtn) printBtn.style.display = view === 'setlist' ? '' : 'none';
    var printInvBtn = document.getElementById('bm-print-inv-btn');
    if (printInvBtn) printInvBtn.style.display = view === 'inventory' ? '' : 'none';
    var controls = document.querySelector('.bm-controls');
    if (controls) controls.style.display = view === 'inventory' ? 'none' : '';
    var invSection = document.getElementById('bm-inv-section');
    if (invSection) invSection.style.display = view === 'inventory' ? 'block' : 'none';
    if (view === 'inventory') { bmLoadInventoryView(); return; }
    dataCache = {};
    sortCol = null; sortAsc = true;
    activeSet = 'all';
    document.getElementById('bm-search').value = '';
    loadView(view);
  };

  function keyBadge(key) {
    if (!key) return '<span style="color:var(--muted)">\u2014</span>';
    const minor = /m$/.test(key);
    return '<span class="key-badge ' + (minor ? 'key-minor' : 'key-major') + '">' + key + '</span>';
  }

  function showErr(msg) {
    document.getElementById('bm-loading').style.display = 'none';
    document.getElementById('bm-err').style.display = 'block';
    document.getElementById('bm-err').textContent = '\u26a0 ' + msg;
  }

  function render(songs) {
    const tbody   = document.getElementById('bm-tbody');
    const noRes   = document.getElementById('bm-no-results');
    const tbl     = document.getElementById('bm-table');
    const loading = document.getElementById('bm-loading');
    const countEl = document.getElementById('bm-visible-count');
    loading.style.display = 'none';
    if (!songs.length) {
      tbody.innerHTML = '';
      tbl.style.display = 'none';
      noRes.style.display = 'block';
      if (countEl) countEl.textContent = '0';
      return;
    }
    noRes.style.display = 'none';
    tbl.style.display = 'table';
    if (countEl) countEl.textContent = songs.length;
    const grouped = sortCol === null && currentView === 'setlist';
    let html = '';
    let lastSet = null;
    songs.forEach(function(s) {
      if (grouped && s.set !== lastSet) {
        lastSet = s.set;
        const headerLabel = s.set > 3 ? '\u2500\u2500 Backup' : '\u2500\u2500 Set ' + s.set;
        html += '<tr class="bm-set-header"><td colspan="8">' + headerLabel + '</td></tr>';
      }
      const isSetlist = currentView === 'setlist';
      const bpmHtml  = s.bpm != null ? '<span class="bpm-val">' + s.bpm + '</span>' : '<span class="bpm-val bpm-unknown">?</span>';
      let smHtml = '';
      if (s.sheet_music && s.sheet_music.length) {
        smHtml = s.sheet_music.map(function(url, i) {
          const fname = decodeURIComponent(url.split('/').pop());
          const label = fname.replace(/^.*?\(([^)]+)\).*$/, '$1') || ('View ' + (i+1));
          return '<a href="' + url + '" target="_blank" style="color:var(--accent);font-size:.72rem;margin-right:.35rem;white-space:nowrap">' + label + '</a>';
        }).join('');
      } else {
        smHtml = '<span style="color:var(--muted);font-size:.72rem">\u2014</span>';
      }
      let audioHtml = '';
      if (s.audio_url) {
        audioHtml = '<button class="bm-play-btn" data-audio-url="' + s.audio_url + '" onclick="bmPlayRow(this)">\u25b6</button>' +
                    '<input type="range" class="bm-progress" value="0" min="0" max="100" oninput="bmSeek(this)">';
      } else {
        audioHtml = '<span style="color:var(--muted);font-size:.72rem">\u2014</span>';
      }
      html += '<tr>' +
        (isSetlist ? '<td style="color:var(--muted);font-size:.72rem;white-space:nowrap">' + (s.set > 3 ? 'BU' : 'S'+s.set) + '.' + s.order + '</td>' : '') +
        '<td style="font-weight:600">' + s.title + '</td>' +
        '<td style="color:var(--muted)">' + (s.artist || '') + '</td>' +
        '<td>' + keyBadge(s.key) + '</td>' +
        '<td style="text-align:center">' + bpmHtml + '</td>' +
        '<td>' + smHtml + '</td>' +
        '<td>' + audioHtml + '</td>' +
      '</tr>';
    });
    tbody.innerHTML = html;
  }

  function buildHeader() {
    const thead = document.getElementById('bm-thead');
    const isSetlist = currentView === 'setlist';
    const cols = [
      ...(isSetlist ? [['#', '', '']] : []),
      ['Title', 'title', ''], ['Artist', 'artist', ''], ['Key', 'key', ''], ['BPM', 'bpm', ''],
      ['\u266b', '', 'bm-th-sheet'], ['\u25b6', '', 'bm-th-audio'],
    ];
    thead.innerHTML = '<tr>' + cols.map(function(c) {
      const isSorted = sortCol === c[1] && c[1];
      const idAttr = c[2] ? ' id="' + c[2] + '"' : '';
      return '<th' + idAttr + ' class="' + (isSorted ? 'sorted' : '') + '" ' +
        (c[1] ? 'onclick="bmSort(\'' + c[1] + '\')"' : '') + '>' +
        c[0] + (c[1] ? '<span class="sort-arrow">' + (isSorted ? (sortAsc ? '\u25b2' : '\u25bc') : '\u25b2') + '</span>' : '') +
        '</th>';
    }).join('') + '</tr>';
  }

  window.bmSort = function(col) {
    if (sortCol === col) { sortAsc = !sortAsc; } else { sortCol = col; sortAsc = true; }
    document.getElementById('bm-sort-info').textContent = 'Sorted by ' + col + (sortAsc ? ' \u2191' : ' \u2193');
    applyFilter();
  };

  function loadView(view) {
    const cacheKey = currentBandId + ':' + view;
    if (dataCache[cacheKey]) { allSongs = dataCache[cacheKey]; buildHeader(); applyFilter(); return; }
    const band = getBandData(currentBandId);
    if (!band) { showErr('Band data not found'); return; }
    document.getElementById('bm-loading').style.display = 'block';
    document.getElementById('bm-table').style.display = 'none';
    if (view === 'setlist') {
      var setlistSongs = (band.setlist && band.setlist.songs) || [];
      var catalogSongs = (band.catalog && band.catalog.songs) || [];
      var catalogMap = {};
      catalogSongs.forEach(function(s){ catalogMap[s.id] = s; });
      allSongs = setlistSongs.map(function(s) {
        var cat = catalogMap[s.catalog_id] || {};
        return Object.assign({}, s, {
          sheet_music: cat.sheet_music || s.sheet_music || [],
          audio_url: s.audio_url || cat.audio_url || null,
        });
      });
      var meta = band.setlist && band.setlist.setlist;
      var metaEl = document.getElementById('bm-meta');
      if (meta && meta.name) {
        metaEl.innerHTML = '<span>' + meta.name + '</span>' +
          (meta.gig_date ? '<span>' + meta.gig_date + '</span>' : '') +
          (meta.venue ? '<span>' + meta.venue + '</span>' : '');
      } else {
        metaEl.innerHTML = band.genre ? '<span>' + band.genre + '</span>' : '';
      }
      buildSetTabs(allSongs);
    } else {
      var catalogSongs2 = (band.catalog && band.catalog.songs) || [];
      allSongs = catalogSongs2;
      document.getElementById('bm-meta').innerHTML = band.genre ? '<span>' + band.genre + '</span>' +
        '<span><b>' + (band.catalog ? band.catalog.count : 0) + '</b> songs</span>' : '';
      buildSetTabs([]);
    }
    dataCache[cacheKey] = allSongs;
    buildHeader();
    applyFilter();
  }

  function buildSetTabs(songs) {
    const tabsEl = document.getElementById('bm-set-tabs');
    if (currentView !== 'setlist' || !songs.length) { tabsEl.innerHTML = ''; return; }
    const sets = [...new Set(songs.map(function(s){ return s.set; }))].sort(function(a,b){return a-b;});
    tabsEl.innerHTML = ['<span class="bm-tab active" data-set="all" onclick="bmSetTab(this,\'all\')">All</span>']
      .concat(sets.map(function(s) {
        return '<span class="bm-tab" data-set="' + s + '" onclick="bmSetTab(this,' + s + ')">' +
          (s > 3 ? 'Backup' : 'Set ' + s) + '</span>';
      })).join('');
  }

  window.bmSetTab = function(el, set) {
    document.querySelectorAll('.bm-tab').forEach(function(t){ t.classList.remove('active'); });
    el.classList.add('active');
    activeSet = set;
    applyFilter();
  };

  window.applyFilter = function() {
    const q = (document.getElementById('bm-search').value || '').toLowerCase();
    let songs = allSongs;
    if (activeSet !== 'all') { songs = songs.filter(function(s){ return s.set == activeSet; }); }
    if (q) { songs = songs.filter(function(s){ return (s.title+s.artist+s.key).toLowerCase().includes(q); }); }
    if (sortCol) {
      songs = songs.slice().sort(function(a,b){
        const av = a[sortCol] != null ? a[sortCol] : '';
        const bv = b[sortCol] != null ? b[sortCol] : '';
        return sortAsc ? (av < bv ? -1 : av > bv ? 1 : 0) : (av > bv ? -1 : av < bv ? 1 : 0);
      });
    }
    var chips = document.getElementById('bm-stat-chips');
    chips.innerHTML = '<span class="bm-chip"><b id="bm-visible-count">0</b> shown</span>';
    render(songs);
  };

  var _bmCurrentAudioBtn = null;
  window.bmPlayRow = function(btn) {
    const audio = document.getElementById('bm-audio');
    const url = btn.dataset.audioUrl;
    const resolvedUrl = new URL(url, location.href).href;
    if (_bmCurrentAudioBtn && _bmCurrentAudioBtn !== btn) {
      _bmCurrentAudioBtn.textContent = '\u25b6';
      _bmCurrentAudioBtn.classList.remove('playing');
    }
    if (audio.src === resolvedUrl && !audio.paused) {
      audio.pause(); btn.textContent = '\u25b6'; btn.classList.remove('playing'); _bmCurrentAudioBtn = null;
    } else {
      audio.src = url; audio.play().catch(function(){});
      btn.textContent = '\u23f8'; btn.classList.add('playing'); _bmCurrentAudioBtn = btn;
      audio.ontimeupdate = function() {
        var prog = btn.parentElement ? btn.parentElement.querySelector('.bm-progress') : null;
        if (prog && audio.duration) prog.value = (audio.currentTime / audio.duration) * 100;
      };
      audio.onended = function() {
        btn.textContent = '\u25b6'; btn.classList.remove('playing'); _bmCurrentAudioBtn = null;
      };
    }
  };

  window.bmSeek = function(range) {
    const audio = document.getElementById('bm-audio');
    if (audio.duration) audio.currentTime = (range.value / 100) * audio.duration;
  };

  window.bmPrintSetlist = function() {
    var band = getBandData(currentBandId);
    if (!band) return;
    var meta = (band.setlist && band.setlist.setlist) || {};
    var songs = allSongs;
    var exportedAt = (BM_INLINE && BM_INLINE.exported_at) ? BM_INLINE.exported_at : '';
    var rows = '';
    var lastSet = null;
    songs.forEach(function(s, i) {
      if (s.set !== lastSet) {
        lastSet = s.set;
        var hdr = s.set > 3 ? 'Backup' : 'Set ' + s.set;
        rows += '<tr class="bm-print-set-header"><td colspan="5">' + hdr + '</td></tr>';
      }
      rows += '<tr>' +
        '<td>' + (s.set > 3 ? 'BU.' : 'S' + s.set + '.') + s.order + '</td>' +
        '<td>' + (s.title || '') + '</td>' +
        '<td>' + (s.artist || '') + '</td>' +
        '<td>' + (s.key || '\u2014') + '</td>' +
        '<td>' + (s.bpm != null ? s.bpm : '?') + '</td>' +
        '</tr>';
    });
    var html = '<h1>\u266a ' + band.name + '</h1>' +
      (meta.name ? '<h2>' + meta.name + '</h2>' : '') +
      ((meta.gig_date || meta.venue) ? '<p>' + (meta.gig_date || '') + (meta.gig_date && meta.venue ? ' \u00b7 ' : '') + (meta.venue || '') + '</p>' : '') +
      '<table>' +
        '<thead><tr><th>#</th><th>Title</th><th>Artist</th><th>Key</th><th>BPM</th></tr></thead>' +
        '<tbody>' + rows + '</tbody>' +
      '</table>' +
      '<p class="bm-print-footer">Printed from \u2764Music Band Management \u00b7 ' + exportedAt + '</p>';
    var area = document.getElementById('bm-print-area');
    area.innerHTML = html;
    window.print();
    area.innerHTML = '';
  };

  // === GIG INVENTORY (AC2-AC6) ===
  function bmLoadInventoryView() {
    document.getElementById('bm-loading').style.display = 'none';
    document.getElementById('bm-table').style.display = 'none';
    document.getElementById('bm-no-results').style.display = 'none';
    var invSection = document.getElementById('bm-inv-section');
    if (invSection) { invSection.style.display = 'block'; bmRenderInventory(); }
  }

  function _escHtml(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  window.bmRenderInventory = function() {
    var customRows = [];
    try { customRows = JSON.parse(localStorage.getItem('bm_inv_custom_rows') || '[]'); } catch(e) {}
    var removedIds = [];
    try { removedIds = JSON.parse(localStorage.getItem('bm_inv_removed_ids') || '[]'); } catch(e) {}
    var edits = {};
    try { edits = JSON.parse(localStorage.getItem('bm_inv_edits') || '{}'); } catch(e) {}
    var seedRows = BM_INVENTORY
      .filter(function(r){ return removedIds.indexOf(String(r.id)) === -1; })
      .map(function(r) {
        var ed = edits[String(r.id)] || {};
        return {id: r.id, item: ed.item !== undefined ? ed.item : r.item,
                category: ed.category !== undefined ? ed.category : (r.category || 'General'), custom: false};
      });
    var allRows = seedRows.concat(customRows.map(function(r){ return {id: r.id, item: r.item, category: r.category || 'General', custom: true}; }));
    var rowsHtml = allRows.map(function(row) {
      var gc = localStorage.getItem('bm_inv_going_' + row.id) === '1' ? ' checked' : '';
      var rc = localStorage.getItem('bm_inv_returning_' + row.id) === '1' ? ' checked' : '';
      var isC = row.custom ? 'true' : 'false';
      var itemHtml = '<span class="bm-inv-editable" title="Click to edit" onclick="bmInvEditField(this,\'' + row.id + '\',\'item\',' + isC + ')">' +
        '\u270f\u00a0' + _escHtml(row.item) + '</span>';
      var catHtml = '<span class="bm-inv-cat bm-inv-editable" title="Click to edit" onclick="bmInvEditField(this,\'' + row.id + '\',\'category\',' + isC + ')">' +
        '\u270f\u00a0' + _escHtml(row.category) + '</span>';
      var rmBtn = '<button class="bm-inv-remove-btn" onclick="bmInvRemove(\'' + row.id + '\',' + isC + ')" title="Remove row">\u00d7</button>';
      return '<tr data-inv-id="' + row.id + '">' +
        '<td style="font-weight:600">' + itemHtml + '</td>' +
        '<td>' + catHtml + '</td>' +
        '<td style="text-align:center"><input type="checkbox" class="bm-inv-cb"' + gc + ' data-type="going" data-id="' + row.id + '" onchange="bmInvToggle(this)"></td>' +
        '<td style="text-align:center"><input type="checkbox" class="bm-inv-cb"' + rc + ' data-type="returning" data-id="' + row.id + '" onchange="bmInvToggle(this)"></td>' +
        '<td style="text-align:center">' + rmBtn + '</td>' +
        '</tr>';
    }).join('');
    var html =
      '<table class="bm-inv-table"><thead><tr>' +
        '<th>Item</th><th>Category</th><th>Going \u2713</th><th>Returning \u2713</th><th></th>' +
      '</tr></thead><tbody>' + rowsHtml + '</tbody></table>' +
      '<div style="margin-top:.75rem;display:flex;gap:.5rem;flex-wrap:wrap;align-items:center;">' +
        '<button class="bm-inv-btn" onclick="bmInvResetChecks()">Reset Checks</button>' +
        '<button class="bm-inv-btn" onclick="bmInvRestoreDefaults()" style="color:#f87171;border-color:rgba(231,76,60,.5);">Restore Defaults</button>' +
        '<button class="bm-inv-btn" onclick="bmInvToggleAddForm()">+ Add Item</button>' +
      '</div>' +
      '<div id="bm-inv-add-form" style="display:none;margin-top:.5rem;padding:.75rem;background:var(--surface);border:1px solid var(--border);border-radius:6px;">' +
        '<input id="bm-inv-new-item" placeholder="Item name" style="background:var(--bg2,#1e2530);border:1px solid var(--border);border-radius:4px;color:var(--text);padding:.3rem .5rem;font-size:.82rem;margin-right:.4rem;">' +
        '<input id="bm-inv-new-cat" placeholder="Category" style="background:var(--bg2,#1e2530);border:1px solid var(--border);border-radius:4px;color:var(--text);padding:.3rem .5rem;font-size:.82rem;margin-right:.4rem;">' +
        '<button class="bm-inv-btn" onclick="bmInvSaveRow()">Save</button>' +
        ' <button class="bm-inv-btn" onclick="bmInvToggleAddForm()">Cancel</button>' +
      '</div>';
    document.getElementById('bm-inv-section').innerHTML = html;
  };

  window.bmInvToggle = function(cb) {
    localStorage.setItem('bm_inv_' + cb.dataset.type + '_' + cb.dataset.id, cb.checked ? '1' : '0');
  };

  window.bmInvResetChecks = function() {
    var keys = [];
    for (var i = 0; i < localStorage.length; i++) {
      var k = localStorage.key(i);
      if (k && (k.startsWith('bm_inv_going_') || k.startsWith('bm_inv_returning_'))) keys.push(k);
    }
    keys.forEach(function(k){ localStorage.removeItem(k); });
    bmRenderInventory();
  };

  window.bmInvToggleAddForm = function() {
    var form = document.getElementById('bm-inv-add-form');
    if (form) form.style.display = (form.style.display === 'none' || form.style.display === '') ? 'block' : 'none';
  };

  window.bmInvSaveRow = function() {
    var itemEl = document.getElementById('bm-inv-new-item');
    var catEl  = document.getElementById('bm-inv-new-cat');
    var item = itemEl ? itemEl.value.trim() : '';
    var cat  = catEl  ? catEl.value.trim()  : '';
    if (!item) { if (itemEl) itemEl.focus(); return; }
    if (!cat) cat = 'General';
    var customRows = [];
    try { customRows = JSON.parse(localStorage.getItem('bm_inv_custom_rows') || '[]'); } catch(e) {}
    customRows.push({id: 'c_' + Date.now(), item: item, category: cat});
    localStorage.setItem('bm_inv_custom_rows', JSON.stringify(customRows));
    if (itemEl) itemEl.value = '';
    if (catEl)  catEl.value  = '';
    bmRenderInventory();
  };

  window.bmInvRemove = function(rowId, isCustom) {
    if (isCustom) {
      var customRows = [];
      try { customRows = JSON.parse(localStorage.getItem('bm_inv_custom_rows') || '[]'); } catch(e) {}
      customRows = customRows.filter(function(r){ return String(r.id) !== String(rowId); });
      localStorage.setItem('bm_inv_custom_rows', JSON.stringify(customRows));
    } else {
      var removedIds = [];
      try { removedIds = JSON.parse(localStorage.getItem('bm_inv_removed_ids') || '[]'); } catch(e) {}
      if (removedIds.indexOf(String(rowId)) === -1) removedIds.push(String(rowId));
      localStorage.setItem('bm_inv_removed_ids', JSON.stringify(removedIds));
    }
    localStorage.removeItem('bm_inv_going_'     + rowId);
    localStorage.removeItem('bm_inv_returning_' + rowId);
    bmRenderInventory();
  };

  window.bmInvRestoreDefaults = function() {
    localStorage.removeItem('bm_inv_removed_ids');
    localStorage.removeItem('bm_inv_custom_rows');
    localStorage.removeItem('bm_inv_edits');
    var keys = [];
    for (var i = 0; i < localStorage.length; i++) {
      var k = localStorage.key(i);
      if (k && (k.startsWith('bm_inv_going_') || k.startsWith('bm_inv_returning_'))) keys.push(k);
    }
    keys.forEach(function(k){ localStorage.removeItem(k); });
    bmRenderInventory();
  };

  window.bmInvEditField = function(span, rowId, field, isCustom) {
    var pencilPrefix = '\u270f\u00a0';
    var current = span.textContent.replace(pencilPrefix, '').trim();
    var input = document.createElement('input');
    input.value = current;
    input.style.cssText = 'background:var(--bg2,#1e2530);border:1px solid var(--accent);border-radius:4px;' +
      'color:var(--text);padding:.2rem .4rem;font-size:.82rem;width:auto;min-width:80px;max-width:180px;';
    span.parentNode.replaceChild(input, span);
    input.focus(); input.select();
    function save() {
      var val = input.value.trim() || current;
      if (isCustom) {
        var customRows = [];
        try { customRows = JSON.parse(localStorage.getItem('bm_inv_custom_rows') || '[]'); } catch(e) {}
        customRows = customRows.map(function(r){
          if (String(r.id) === String(rowId)) { var copy = Object.assign({}, r); copy[field] = val; return copy; }
          return r;
        });
        localStorage.setItem('bm_inv_custom_rows', JSON.stringify(customRows));
      } else {
        var edits = {};
        try { edits = JSON.parse(localStorage.getItem('bm_inv_edits') || '{}'); } catch(e) {}
        if (!edits[String(rowId)]) edits[String(rowId)] = {};
        edits[String(rowId)][field] = val;
        localStorage.setItem('bm_inv_edits', JSON.stringify(edits));
      }
      bmRenderInventory();
    }
    input.addEventListener('blur', save);
    input.addEventListener('keydown', function(e){
      if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
      else if (e.key === 'Escape') { bmRenderInventory(); }
    });
  };

  window.bmPrintInventory = function() {
    var customRows = [];
    try { customRows = JSON.parse(localStorage.getItem('bm_inv_custom_rows') || '[]'); } catch(e) {}
    var removedIds = [];
    try { removedIds = JSON.parse(localStorage.getItem('bm_inv_removed_ids') || '[]'); } catch(e) {}
    var edits = {};
    try { edits = JSON.parse(localStorage.getItem('bm_inv_edits') || '{}'); } catch(e) {}
    var seedRows = BM_INVENTORY
      .filter(function(r){ return removedIds.indexOf(String(r.id)) === -1; })
      .map(function(r) {
        var ed = edits[String(r.id)] || {};
        return {id: r.id, item: ed.item !== undefined ? ed.item : r.item,
                category: ed.category !== undefined ? ed.category : (r.category || 'General')};
      });
    var allRows = seedRows.concat(customRows);
    var rowsHtml = allRows.map(function(row) {
      var gc = localStorage.getItem('bm_inv_going_'     + row.id) === '1' ? '\u2611' : '\u2610';
      var rc = localStorage.getItem('bm_inv_returning_' + row.id) === '1' ? '\u2611' : '\u2610';
      return '<tr>' +
        '<td>' + _escHtml(row.item) + '</td>' +
        '<td>' + _escHtml(row.category || 'General') + '</td>' +
        '<td class="inv-cb-cell">' + gc + '</td>' +
        '<td class="inv-cb-cell">' + rc + '</td>' +
        '</tr>';
    }).join('');
    var html = '<h1>\u2764 Gig Inventory Checklist</h1>' +
      '<table><thead><tr><th>Item</th><th>Category</th><th>Going</th><th>Returning</th></tr></thead>' +
      '<tbody>' + rowsHtml + '</tbody></table>' +
      '<p style="font-size:.7rem;color:#888;margin-top:.5rem">Printed from \u2764Music Band Management</p>';
    var area = document.getElementById('bm-inv-print-area');
    area.innerHTML = html;
    window.print();
    area.innerHTML = '';
  };

  // ---------------------------------------------------------------------------
  // HTTP-origin URL rewriting (BFX-20260531-band-mgmt-file-urls)
  // When the panel is served at http:// or https://, browsers block file://
  // resources.  This function rewrites BM_INLINE song data in-place so every
  // file:/// URI becomes a relative URL served by the local HTTP server.
  // When the panel is opened directly as file://, it returns immediately so
  // existing behaviour is completely unchanged (AC3).
  // ---------------------------------------------------------------------------
  function _bmRewriteFileUrls() {
    if (window.location.protocol === 'file:') return;  // AC3: file:// mode — keep as-is
    if (!BM_INLINE || !BM_INLINE.bands) return;
    BM_INLINE.bands.forEach(function(band) {
      var groups = [];
      if (band.catalog && band.catalog.songs) groups.push(band.catalog.songs);
      if (band.setlist && band.setlist.songs) groups.push(band.setlist.songs);
      groups.forEach(function(songs) {
        songs.forEach(function(s) {
          // Rewrite audio_url: file:///G:/Muzic/<filename> → /audio/<filename>
          if (s.audio_url && s.audio_url.indexOf('file:///') === 0) {
            var audioMatch = s.audio_url.match(/^file:\/\/\/[Gg]:[\/\\]Muzic[\/\\](.+)$/i);
            if (audioMatch) {
              s.audio_url = '/audio/' + audioMatch[1];
            }
          }
          // Rewrite sheet_music[]: file:///f:/%E2%9D%A4Music/catalog/sheet_music/<relpath>
          //                       → /sheets/<relpath>
          if (s.sheet_music && s.sheet_music.length) {
            s.sheet_music = s.sheet_music.map(function(url) {
              if (url.indexOf('file:///') !== 0) return url;
              var sheetMatch = url.match(/^file:\/\/\/(?:f:\/)?%E2%9D%A4Music\/catalog\/sheet_music\/(.+)$/i);
              if (sheetMatch) {
                return '/sheets/' + sheetMatch[1];
              }
              return url;
            });
          }
        });
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function() {
    _bmRewriteFileUrls();  // rewrite file:// → HTTP endpoints before first render (AC1, AC2)
    populateBandSelect();
    var printBtn = document.getElementById('bm-print-btn');
    if (printBtn) printBtn.style.display = currentView === 'setlist' ? '' : 'none';
    var printInvBtn = document.getElementById('bm-print-inv-btn');
    if (printInvBtn) printInvBtn.style.display = 'none';
    var invSection = document.getElementById('bm-inv-section');
    if (invSection) invSection.style.display = 'none';
    if (currentBandId !== null) loadView(currentView);
  });
})();
"""


def generate(data: dict, inventory: list | None = None) -> str:
    """Build the full standalone HTML."""
    if inventory is None:
        inventory = []
    bm_inline_json = json.dumps(data, ensure_ascii=False)
    bm_inventory_json = json.dumps(inventory, ensure_ascii=False)
    vera_tag = _get_vera_tag()
    vera_block = ""
    if vera_tag:
        vera_block = (
            '<div class="bm-vera-portrait">'
            + vera_tag
            + '<button class="vera-edit-btn" onclick="openVeraModal()" '
            + 'title="Edit Vera\'s portrait prompt" '
            + 'onmouseenter="this.style.opacity=\'0.9\'" '
            + 'onmouseleave="this.style.opacity=\'0.35\'">&#x270F;</button>'
            + '</div>'
        )
    panel_body_with_vera = PANEL_BODY.replace(
        '<div class="bm-header">',
        f'<div class="bm-header">{vera_block}',
        1,
    )
    js_with_data = BM_JS.replace(
        "/*INJECT_DATA*/null/*END_INJECT*/",
        bm_inline_json,
    ).replace(
        "/*INJECT_INVENTORY*/[]/*END_INJECT_INVENTORY*/",
        bm_inventory_json,
    )
    vera_modal_html = """
<!-- Vera Prompt Modal -->
<div class="vera-modal-overlay" id="vera-prompt-modal" onclick="veraModalClickOutside(event)">
  <div class="vera-modal-card" role="dialog" aria-modal="true" aria-labelledby="vera-modal-title">
    <button class="vera-modal-close" onclick="closeVeraModal()" aria-label="Close">&times;</button>
    <h2 id="vera-modal-title">&#x270F; Edit Vera&rsquo;s Portrait Prompt</h2>
    <label class="vera-modal-label" for="vera-mode-select">Mode</label>
    <select id="vera-mode-select" onchange="veraLoadPromptForMode(this.value)">
      <option value="rehearsal">Rehearsal &mdash; no gig within 14 days</option>
      <option value="pre_show">Pre-Show &mdash; gig within 14 days</option>
      <option value="show_night">Show Night &mdash; gig is today</option>
    </select>
    <label class="vera-modal-label" for="vera-positive-prompt">Positive Prompt</label>
    <textarea id="vera-positive-prompt" rows="10" spellcheck="false"></textarea>
    <div class="vera-modal-actions">
      <button class="vera-btn-save" id="vera-save-btn" onclick="veraModalSave()">Save &amp; Regenerate</button>
      <button class="vera-btn-cancel" onclick="closeVeraModal()">Cancel</button>
    </div>
    <div class="vera-modal-status" id="vera-modal-status"></div>
  </div>
</div>"""
    vera_js = r"""
// Probe whether the Vera API is actually reachable (works in both file:// and portal iframe)
let _veraApiAvailable = null;
async function _veraCheckApi() {
  if (_veraApiAvailable !== null) return _veraApiAvailable;
  try {
    const r = await fetch('/vera/prompt?mode=rehearsal', {method: 'HEAD'});
    _veraApiAvailable = r.ok || r.status === 405;  // 405 = method not allowed → endpoint exists
  } catch(_) {
    _veraApiAvailable = false;
  }
  return _veraApiAvailable;
}
function _veraShowServeHint() {
  document.getElementById('vera-modal-status').textContent =
    'Live edits require server mode: python src/band_mgmt/generate_band_mgmt_panel.py --serve';
}
async function openVeraModal() {
  const modal = document.getElementById('vera-prompt-modal');
  modal.classList.add('open');
  const sel = document.getElementById('vera-mode-select');
  veraLoadPromptForMode(sel.value);
}
function closeVeraModal() {
  document.getElementById('vera-prompt-modal').classList.remove('open');
  document.getElementById('vera-modal-status').textContent = '';
}
function veraModalClickOutside(e) {
  if (e.target === document.getElementById('vera-prompt-modal')) closeVeraModal();
}
async function veraLoadPromptForMode(mode) {
  const available = await _veraCheckApi();
  if (!available) {
    document.getElementById('vera-positive-prompt').value = '(Server mode required to load prompt)';
    document.getElementById('vera-modal-status').textContent =
      'Run: python src/band_mgmt/generate_band_mgmt_panel.py --serve';
    return;
  }
  const status = document.getElementById('vera-modal-status');
  status.textContent = 'Loading\u2026';
  fetch('/vera/prompt?mode=' + encodeURIComponent(mode))
    .then(r => r.json())
    .then(d => {
      document.getElementById('vera-positive-prompt').value = d.positive_prompt || '';
      status.textContent = '';
    })
    .catch(e => { status.textContent = 'Failed to load prompt: ' + e.message; });
}
async function veraModalSave() {
  const available = await _veraCheckApi();
  if (!available) { _veraShowServeHint(); return; }
  const btn = document.getElementById('vera-save-btn');
  const status = document.getElementById('vera-modal-status');
  const prompt = document.getElementById('vera-positive-prompt').value.trim();
  const mode = document.getElementById('vera-mode-select').value;
  if (!prompt) { status.textContent = 'Prompt cannot be empty.'; return; }
  btn.disabled = true;
  btn.textContent = 'Saving…';
  status.textContent = '';
  try {
    const saveResp = await fetch('/vera/prompt', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({positive_prompt: prompt, mode: mode})
    });
    if (!saveResp.ok) { status.textContent = 'Save failed (' + saveResp.status + ').'; return; }
    btn.textContent = 'Regenerating…';
    const regenResp = await fetch('/vera/portrait/regen?mode=' + encodeURIComponent(mode));
    if (regenResp.ok) {
      status.textContent = '\u2705 Portrait regenerated. Reloading\u2026';
      setTimeout(() => { closeVeraModal(); window.location.reload(); }, 1200);
    } else {
      status.textContent = 'Regen failed (' + regenResp.status + '). Prompt was saved.';
    }
  } catch(e) {
    status.textContent = 'Error: ' + e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Save & Regenerate';
  }
}"""
    exported_at = data.get("exported_at", "")
    band_count = len(data.get("bands", []))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>\u2764 Band Management</title>
<style>
{CSS_VARS}
{PANEL_CSS}
</style>
</head>
<body>
{vera_modal_html}
{panel_body_with_vera}
<script>
{js_with_data}
{vera_js}
</script>
</body>
</html>
"""


def main() -> None:
    print("Generating Band Management Panel...")
    data = load_inline_data()
    inventory = load_inventory_data()
    for b in data.get("bands", []):
        cat_n = b.get("catalog", {}).get("count", 0)
        sl_n = b.get("setlist", {}).get("count", 0)
        print(f"  Band: {b['name']} — {cat_n} catalog songs, {sl_n} setlist songs")
    print(f"  Inventory: {len(inventory)} items")
    html = generate(data, inventory)
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"  Written to {OUTPUT_HTML}")
    print(f"  Size: {OUTPUT_HTML.stat().st_size:,} bytes")


# ---------------------------------------------------------------------------
# HTTP server (--serve mode) — API endpoints for Vera prompt editing
# ---------------------------------------------------------------------------

def _serve_mode(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Run a local HTTP server that hot-rebuilds the panel and exposes Vera APIs."""
    import argparse  # noqa: F401 — already parsed before calling
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from socketserver import ThreadingMixIn
    from urllib.parse import urlparse, parse_qs

    class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True

    def _load_vera_portrait_module():
        import importlib.util as _ilu
        _src = Path(__file__).resolve().parents[1] / "utils" / "vera_portrait.py"
        _spec = _ilu.spec_from_file_location("_vera_portrait_srv", _src)
        if _spec and _spec.loader:
            _mod = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
            return _mod
        return None

    def _load_vera_config_module():
        import importlib.util as _ilu
        _src = Path(__file__).resolve().parents[1] / "utils" / "vera_config_db.py"
        _spec = _ilu.spec_from_file_location("_vera_config_srv", _src)
        if _spec and _spec.loader:
            _mod = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
            return _mod
        return None

    class BandMgmtHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # silence default access log spam
            print(f"  [{self.address_string()}] {fmt % args}")

        def _json(self, data: dict, status: int = 200) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _html(self, body_text: str) -> None:
            body = body_text.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_file(self, file_path: Path, content_type: str) -> None:
            """Stream *file_path* with optional Range-request support."""
            import mimetypes
            try:
                file_size = file_path.stat().st_size
            except OSError:
                self.send_error(404, "File not found")
                return
            range_header = self.headers.get("Range", "")
            range_match = re.match(r"bytes=(\d+)-(\d*)", range_header) if range_header else None
            if range_match:
                start = int(range_match.group(1))
                end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
                end = min(end, file_size - 1)
                length = end - start + 1
                self.send_response(206)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                self.send_header("Content-Length", str(length))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                with open(file_path, "rb") as fh:
                    fh.seek(start)
                    self.wfile.write(fh.read(length))
            else:
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(file_size))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                with open(file_path, "rb") as fh:
                    self.wfile.write(fh.read())

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            path = parsed.path.rstrip("/") or "/"
            if path in ("/", "/index.html"):
                data = load_inline_data()
                inv = load_inventory_data()
                self._html(generate(data, inv))
            elif path.startswith("/audio/"):
                # Serve audio files from AUDIO_ROOT (e.g. G:\Muzic)
                raw = path[len("/audio/"):]
                try:
                    audio_path = _resolve_audio_path(raw)
                except ValueError:
                    self.send_error(400, "Invalid audio path")
                    return
                import mimetypes
                ct = mimetypes.guess_type(audio_path.name)[0] or "audio/mpeg"
                self._send_file(audio_path, ct)
            elif path.startswith("/sheets/"):
                # Serve sheet-music files from SHEETS_ROOT
                raw = path[len("/sheets/"):]
                try:
                    sheet_path = _resolve_sheet_path(raw)
                except ValueError:
                    self.send_error(400, "Invalid sheet path")
                    return
                import mimetypes
                _DOCX_CT = (
                    "application/vnd.openxmlformats-officedocument"
                    ".wordprocessingml.document"
                )
                ct = (
                    _DOCX_CT
                    if sheet_path.suffix.lower() == ".docx"
                    else (mimetypes.guess_type(sheet_path.name)[0] or "application/octet-stream")
                )
                self._send_file(sheet_path, ct)
            elif path == "/vera/prompt":
                mode = qs.get("mode", ["rehearsal"])[0]
                try:
                    cfg = _load_vera_config_module()
                    positive, _ = cfg.get_active_prompt(mode)
                    self._json({"positive_prompt": positive, "mode": mode})
                except Exception as exc:
                    self._json({"error": str(exc)}, 500)
            elif path == "/vera/portrait/regen":
                mode = qs.get("mode", ["rehearsal"])[0]
                try:
                    mod = _load_vera_portrait_module()
                    # Delete today's cached file for this mode
                    today_path = mod._today_cache_path(mode)
                    if today_path.exists():
                        today_path.unlink()
                    from datetime import date as _date
                    today = _date.today().isoformat()
                    svg_path = mod._IMAGE_CACHE_DIR / f"vera_portrait_{today}_{mode}.svg"
                    if svg_path.exists():
                        svg_path.unlink()
                    new_path = mod.get_daily_portrait(mode=mode)
                    self._json({"status": "ok", "path": str(new_path), "mode": mode})
                except Exception as exc:
                    self._json({"error": str(exc)}, 500)
            else:
                self.send_error(404)

        def do_HEAD(self) -> None:
            """Return 405 for known API paths so _veraCheckApi() can detect serve mode."""
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            if path == "/vera/prompt":
                self.send_response(405)
                self.send_header("Allow", "GET, POST")
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                self.send_error(404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/")
            if path == "/vera/prompt":
                try:
                    content_len = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(content_len))
                    positive_prompt = body.get("positive_prompt", "").strip()
                    mode = body.get("mode", "rehearsal")
                    if not positive_prompt:
                        self._json({"error": "positive_prompt is required"}, 400)
                        return
                    cfg = _load_vera_config_module()
                    cfg.update_active_prompt(positive_prompt, mode)
                    self._json({"ok": True, "mode": mode})
                except Exception as exc:
                    self._json({"error": str(exc)}, 500)
            else:
                self.send_error(404)

    server = ThreadedHTTPServer((host, port), BandMgmtHandler)
    url = f"http://{host}:{port}"
    print(f"  \u2764 Band Management server running at {url}")
    print(f"  Vera API: GET/POST {url}/vera/prompt?mode=rehearsal")
    print(f"          : GET {url}/vera/portrait/regen?mode=rehearsal")
    print("  Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="❤ Band Management Panel generator")
    parser.add_argument("--serve", action="store_true", help="Run as a local HTTP server")
    parser.add_argument("--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Server port (default: 8765)")
    args = parser.parse_args()
    if args.serve:
        _serve_mode(host=args.host, port=args.port)
    else:
        main()
