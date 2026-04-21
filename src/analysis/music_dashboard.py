"""
❤Music — Interactive Track Dashboard

Minimal web dashboard for browsing and managing tracks in heartmusic.db.
Features: track listing with album/artist info, delete with safety lock.

Usage:
    C:\G\python.exe src/analysis/music_dashboard.py
    C:\G\python.exe src/analysis/music_dashboard.py --port 5050
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request, send_file

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.init_db import get_connection

CATALOG_ROOT = Path(__file__).resolve().parent.parent.parent / "catalog"

app = Flask(__name__)

# ── HTML Template ─────────────────────────────────────────────────────────────

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>❤Music Dashboard</title>
<style>
  :root {
    --bg: #0d0f14;
    --surface: #151820;
    --surface2: #1c2030;
    --border: #252a3a;
    --text: #e2e8f0;
    --text-dim: #64748b;
    --text-muted: #94a3b8;
    --accent: #e11d48;
    --accent2: #fb7185;
    --ok: #22c55e;
    --danger: #ef4444;
    --danger-bg: #2e0808;
    --warning: #f59e0b;
    --radius: 12px;
    --radius-sm: 6px;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 14px;
    line-height: 1.6;
    min-height: 100vh;
  }

  .header {
    background: linear-gradient(135deg, #0d0f14 0%, #1a0812 50%, #0d0f14 100%);
    border-bottom: 1px solid var(--border);
    padding: 24px 32px;
    position: sticky; top: 0; z-index: 100;
  }
  .header-inner {
    max-width: 1280px; margin: 0 auto;
    display: flex; align-items: center; justify-content: space-between;
    flex-wrap: wrap; gap: 12px;
  }
  .brand { display: flex; align-items: center; gap: 12px; }
  .brand-icon {
    font-size: 28px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }
  .brand-name {
    font-size: 20px; font-weight: 700; letter-spacing: -0.5px;
    background: linear-gradient(90deg, #e2e8f0, var(--accent2));
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }
  .brand-sub { font-size: 12px; color: var(--text-dim); }

  .controls {
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  }
  .search-box {
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: 20px; padding: 7px 16px; font-size: 13px;
    color: var(--text); outline: none; width: 220px;
  }
  .search-box:focus { border-color: var(--accent); }
  .search-box::placeholder { color: var(--text-dim); }

  .safety-toggle {
    display: flex; align-items: center; gap: 8px;
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: 20px; padding: 6px 14px; cursor: pointer;
    user-select: none; font-size: 12px; color: var(--text-muted);
    transition: all 0.2s;
  }
  .safety-toggle.unlocked {
    border-color: var(--danger); color: var(--danger);
    background: var(--danger-bg);
  }
  .safety-toggle .lock-icon { font-size: 16px; }

  .meta-pill {
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: 20px; padding: 6px 14px;
    font-size: 12px; color: var(--text-muted);
  }
  .meta-pill strong { color: var(--text); }

  /* Status filter */
  .filters {
    max-width: 1280px; margin: 16px auto 0; padding: 0 32px;
    display: flex; gap: 6px; flex-wrap: wrap;
  }
  .filter-btn {
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: 20px; padding: 5px 14px; font-size: 12px;
    color: var(--text-muted); cursor: pointer; transition: all 0.15s;
  }
  .filter-btn:hover, .filter-btn.active {
    background: var(--accent); border-color: var(--accent); color: white;
  }

  .main { max-width: 1280px; margin: 0 auto; padding: 20px 32px 48px; }

  /* Tab nav */
  .tab-nav {
    max-width: 1280px; margin: 16px auto 0; padding: 0 32px;
    display: flex; gap: 0; border-bottom: 1px solid var(--border);
  }
  .tab-btn {
    background: transparent; border: none; border-bottom: 2px solid transparent;
    padding: 10px 20px; font-size: 13px; font-weight: 600;
    color: var(--text-dim); cursor: pointer; transition: all 0.15s;
  }
  .tab-btn:hover { color: var(--text); }
  .tab-btn.active { color: var(--accent2); border-bottom-color: var(--accent); }
  .tab-content { display: none; }
  .tab-content.active { display: block; }

  /* Summary */
  .summary-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 12px; margin-bottom: 24px;
  }
  .summary-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 16px 18px; text-align: center;
  }
  .summary-card .num { font-size: 28px; font-weight: 700; line-height: 1; margin-bottom: 4px; }
  .summary-card .label { font-size: 12px; color: var(--text-dim); }
  .sc-total .num { color: var(--accent2); }
  .sc-released .num { color: var(--ok); }
  .sc-progress .num { color: var(--warning); }
  .sc-albums .num { color: #6366f1; }

  /* Table */
  .table-wrap {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); overflow: hidden;
  }
  table { width: 100%; border-collapse: collapse; }
  thead th {
    padding: 11px 16px; text-align: left; font-size: 11px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-dim);
    border-bottom: 1px solid var(--border); background: var(--surface2);
    cursor: pointer; user-select: none;
  }
  thead th:hover { color: var(--text); }
  thead th .sort-arrow { font-size: 10px; margin-left: 4px; }
  tbody td {
    padding: 10px 16px; border-bottom: 1px solid var(--border); vertical-align: middle;
  }
  tbody tr:last-child td { border-bottom: none; }
  tbody tr:hover td { background: rgba(225,29,72,0.04); }

  .track-title { font-weight: 500; }
  .track-album { color: var(--text-muted); font-size: 12px; }
  .track-num { color: var(--text-dim); font-variant-numeric: tabular-nums; text-align: center; }

  .status-badge {
    display: inline-flex; padding: 3px 10px; border-radius: 10px;
    font-size: 11px; font-weight: 600; letter-spacing: 0.04em; white-space: nowrap;
  }
  .st-idea { background: #1a1f2e; color: #64748b; }
  .st-rough { background: #2a1a00; color: #f59e0b; }
  .st-recorded { background: #0c1a2e; color: #3b82f6; }
  .st-mixed { background: #1a0a2e; color: #a78bfa; }
  .st-mastered { background: #0a2e1a; color: #34d399; }
  .st-released { background: #052e14; color: #22c55e; }

  .delete-btn {
    background: transparent; border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 5px 10px;
    color: var(--text-dim); cursor: not-allowed; font-size: 12px;
    transition: all 0.15s; opacity: 0.4;
  }
  .delete-btn.enabled {
    cursor: pointer; opacity: 1; border-color: var(--danger);
    color: var(--danger);
  }
  .delete-btn.enabled:hover {
    background: var(--danger); color: white;
  }

  .player-shell {
    display: grid; grid-template-columns: minmax(220px, 320px) 1fr;
    gap: 16px; align-items: center; margin-bottom: 18px;
    background: linear-gradient(135deg, rgba(225,29,72,0.12), rgba(251,191,36,0.08));
    border: 1px solid rgba(225,29,72,0.16); border-radius: var(--radius);
    padding: 16px 18px;
  }
  .player-kicker {
    font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em;
    color: var(--text-dim); margin-bottom: 6px;
  }
  .player-title { font-size: 18px; font-weight: 700; margin-bottom: 4px; }
  .player-subtitle { font-size: 12px; color: var(--text-muted); }
  .player-shell audio { width: 100%; }

  .listen-cell { min-width: 160px; }
  .audio-chip-row { display: flex; flex-wrap: wrap; gap: 6px; }
  .audio-chip {
    border: 1px solid var(--border); background: var(--surface2); color: var(--text);
    border-radius: 999px; padding: 5px 10px; font-size: 11px; font-weight: 600;
    cursor: pointer; transition: all 0.15s;
  }
  .audio-chip:hover { transform: translateY(-1px); border-color: var(--accent); }
  .audio-chip.ai { border-color: rgba(34,197,94,0.4); color: #86efac; }
  .audio-chip.human { border-color: rgba(251,191,36,0.4); color: #fcd34d; }
  .audio-chip.active { box-shadow: 0 0 0 1px rgba(255,255,255,0.08) inset; background: rgba(225,29,72,0.18); }
  .audio-empty {
    color: var(--text-dim); font-size: 11px; font-style: italic;
  }

  /* Modal */
  .modal-overlay {
    display: none; position: fixed; inset: 0;
    background: rgba(0,0,0,0.7); z-index: 200;
    justify-content: center; align-items: center;
  }
  .modal-overlay.show { display: flex; }
  .modal {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 28px; max-width: 420px; width: 90%;
  }
  .modal h3 { font-size: 16px; margin-bottom: 8px; color: var(--danger); }
  .modal p { font-size: 13px; color: var(--text-muted); margin-bottom: 16px; }
  .modal .track-info {
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 12px; margin-bottom: 16px;
    font-size: 13px;
  }
  .modal .track-info strong { color: var(--text); }
  .modal-actions { display: flex; gap: 10px; justify-content: flex-end; }
  .btn {
    padding: 8px 18px; border-radius: var(--radius-sm);
    font-size: 13px; font-weight: 600; cursor: pointer; border: none;
    transition: all 0.15s;
  }
  .btn-cancel { background: var(--surface2); color: var(--text-muted); border: 1px solid var(--border); }
  .btn-cancel:hover { background: var(--border); color: var(--text); }
  .btn-danger { background: var(--danger); color: white; }
  .btn-danger:hover { background: #dc2626; }

  .toast {
    position: fixed; bottom: 24px; right: 24px; z-index: 300;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 12px 20px;
    font-size: 13px; transform: translateY(100px); opacity: 0;
    transition: all 0.3s;
  }
  .toast.show { transform: translateY(0); opacity: 1; }
  .toast.success { border-color: var(--ok); color: var(--ok); }
  .toast.error { border-color: var(--danger); color: var(--danger); }

  .empty-state {
    text-align: center; padding: 60px 20px; color: var(--text-dim);
  }
  .empty-state .icon { font-size: 48px; margin-bottom: 12px; }

  @media (max-width: 768px) {
    .header { padding: 16px; }
    .main { padding: 16px; }
    .filters { padding: 0 16px; }
    .search-box { width: 160px; }
    .player-shell { grid-template-columns: 1fr; }
  }

  /* Inline edit fields */
  .inline-edit {
    background: transparent; border: 1px solid transparent;
    border-radius: var(--radius-sm); padding: 3px 6px;
    color: var(--text); font-size: 13px; width: 80px;
    transition: all 0.15s;
  }
  .inline-edit:disabled {
    border-color: transparent; background: transparent;
    color: var(--text-muted); cursor: default; opacity: 0.7;
  }
  .inline-edit:not(:disabled) {
    border-color: var(--border); background: var(--surface2);
    cursor: text;
  }
  .inline-edit:not(:disabled):focus {
    border-color: var(--accent); outline: none;
    background: var(--bg);
  }
  .inline-edit.bpm-input { width: 55px; text-align: center; }
  .inline-edit.key-input { width: 70px; }
  .inline-edit.genre-input { width: 90px; }
  .inline-edit.title-input { width: 160px; }
  .inline-edit.num-input { width: 42px; text-align: center; }

  .album-select {
    background: transparent; border: 1px solid transparent;
    border-radius: var(--radius-sm); padding: 3px 6px;
    color: var(--text-muted); font-size: 12px;
    cursor: default; appearance: none; max-width: 120px;
  }
  .album-select:not(:disabled) {
    border-color: var(--border); background: var(--surface2);
    color: var(--text); cursor: pointer; appearance: auto;
  }
  .album-select:not(:disabled):focus {
    border-color: var(--accent); outline: none;
  }

  .status-select {
    background: transparent; border: 1px solid transparent;
    border-radius: var(--radius-sm); padding: 3px 6px;
    color: var(--text-muted); font-size: 12px;
    cursor: default; appearance: none;
  }
  .status-select:not(:disabled) {
    border-color: var(--border); background: var(--surface2);
    color: var(--text); cursor: pointer; appearance: auto;
  }
  .status-select:not(:disabled):focus {
    border-color: var(--accent); outline: none;
  }

  /* Signatures tab */
  .sig-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(420px, 1fr));
    gap: 16px; margin-top: 16px;
  }
  .sig-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 20px; transition: border-color 0.15s;
  }
  .sig-card:hover { border-color: var(--accent); }
  .sig-card h4 { font-size: 15px; margin-bottom: 8px; }
  .sig-card .sig-format { color: var(--accent2); font-size: 11px; font-weight: 600; text-transform: uppercase; }
  .sig-meta { display: grid; grid-template-columns: auto 1fr; gap: 4px 12px; font-size: 12px; margin-top: 10px; }
  .sig-meta dt { color: var(--text-dim); font-weight: 500; }
  .sig-meta dd { color: var(--text); margin: 0; word-break: break-all; }
  .sig-hash { font-family: 'Consolas', 'Courier New', monospace; font-size: 10px; color: var(--text-muted); }
  .entropy-bar {
    height: 6px; border-radius: 3px; background: var(--surface2);
    overflow: hidden; margin-top: 2px;
  }
  .entropy-fill {
    height: 100%; border-radius: 3px;
    background: linear-gradient(90deg, #22c55e, #f59e0b, #ef4444);
  }
  .sig-provenance {
    margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border);
    font-size: 11px; color: var(--text-muted);
  }
  .sig-provenance .platform-badge {
    display: inline-flex; padding: 2px 8px; border-radius: 8px;
    font-size: 10px; font-weight: 700; text-transform: uppercase;
    background: #1a0a2e; color: #a78bfa; margin-right: 6px;
  }
  .sig-provenance .platform-badge.suno { background: #0a2e1a; color: #34d399; }
  .sig-provenance .platform-badge.pro_tools { background: #2a1a00; color: #f59e0b; }
  .sig-provenance .platform-badge.manual { background: #2a1a00; color: #f59e0b; }

  .sig-section { margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--border); }
  .sig-section-title {
    font-size: 10px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.08em; color: var(--text-dim); margin-bottom: 6px;
  }
  .hash-list { font-family: 'Consolas', monospace; font-size: 9.5px; color: var(--text-muted); line-height: 1.8; }
  .hash-list .hash-label { color: var(--text-dim); display: inline-block; width: 80px; font-weight: 600; }
  .hash-list .hash-value { word-break: break-all; }

  .master-type-badge {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 3px 10px; border-radius: 10px; font-size: 10px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.05em;
  }
  .master-type-badge.human { background: #2a1a00; color: #f59e0b; }
  .master-type-badge.ai { background: #0a2e1a; color: #34d399; }

  .aead-badge {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 2px 8px; border-radius: 8px; font-size: 9px; font-weight: 700;
    background: #1a102e; color: #c084fc; margin-right: 4px;
  }
  .quantum-badge {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 2px 8px; border-radius: 8px; font-size: 9px; font-weight: 700;
    background: #0a1e2e; color: #38bdf8;
  }
  .sig-version-badge {
    font-size: 9px; padding: 2px 6px; border-radius: 4px;
    background: var(--surface2); color: var(--text-dim); font-weight: 600;
  }

  /* ── Radio Tab ── */
  .radio-player-card {
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 24px; width: 320px; text-align: center;
  }
  .radio-status { display: flex; align-items: center; gap: 8px; justify-content: center; margin-bottom: 16px; }
  .radio-dot {
    width: 10px; height: 10px; border-radius: 50%; display: inline-block;
  }
  .radio-dot.online { background: #22c55e; box-shadow: 0 0 8px #22c55e88; animation: pulse-dot 1.5s infinite; }
  .radio-dot.offline { background: #ef4444; }
  @keyframes pulse-dot { 0%,100% { opacity:1; } 50% { opacity:0.4; } }
  .radio-now-playing { margin: 12px 0; }
  .radio-track-title { font-size: 1.3em; font-weight: 700; color: var(--text); }
  .radio-track-album { font-size: 0.85em; color: var(--text-dim); margin-top: 4px; }
  .radio-controls { display: flex; align-items: center; gap: 16px; justify-content: center; margin: 16px 0; }
  .radio-play-btn {
    width: 48px; height: 48px; border-radius: 50%; border: 2px solid var(--accent);
    background: transparent; color: var(--accent); font-size: 1.3em; cursor: pointer;
    transition: background 0.2s, color 0.2s;
  }
  .radio-play-btn:hover { background: var(--accent); color: #fff; }
  .radio-vol-row { display: flex; align-items: center; gap: 8px; }
  .radio-vol-row label { font-size: 0.7em; color: var(--text-dim); letter-spacing: 2px; }
  .radio-vol-row input[type=range] { width: 100px; accent-color: var(--accent); }
  .radio-stats {
    display: flex; gap: 16px; justify-content: center; margin-top: 12px;
    font-size: 0.8em; color: var(--text-dim);
  }
  .radio-stats .stat-val { color: var(--accent2); font-weight: 700; }
  .radio-history, .radio-playlist {
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 20px; flex: 1; min-width: 260px; max-height: 500px; overflow-y: auto;
  }
  .radio-history h3, .radio-playlist h3 {
    font-size: 0.9em; color: var(--text-dim); margin-bottom: 12px; letter-spacing: 1px;
  }
  .rh-item {
    display: flex; justify-content: space-between; align-items: center;
    padding: 8px 0; border-bottom: 1px solid var(--border);
    font-size: 0.85em;
  }
  .rh-item:last-child { border-bottom: none; }
  .rh-title { color: var(--text); font-weight: 600; }
  .rh-album { color: var(--text-dim); font-size: 0.85em; }
  .rh-time { color: var(--text-muted); font-size: 0.8em; font-family: monospace; }
  .rpl-item { padding: 6px 0; border-bottom: 1px solid #1a1a2a; font-size: 0.82em; color: var(--text-dim); }
  .rpl-item:last-child { border-bottom: none; }

  /* Release Ops */
  .ops-panel {
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 20px; margin-bottom: 18px;
  }
  .ops-panel h3 {
    font-size: 14px; margin-bottom: 8px; color: var(--text);
  }
  .ops-panel p {
    color: var(--text-dim); font-size: 13px;
  }
  .ops-chip-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
  .ops-chip {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 5px 10px; border-radius: 999px; font-size: 11px; font-weight: 600;
    background: var(--surface2); border: 1px solid var(--border); color: var(--text-muted);
  }
  .ops-chip.warn { color: #fbbf24; border-color: rgba(251,191,36,0.35); }
  .ops-chip.ok { color: #86efac; border-color: rgba(34,197,94,0.35); }
  .ops-table-note { margin-top: 10px; color: var(--text-dim); font-size: 12px; }
  .ops-platforms { display: flex; flex-wrap: wrap; gap: 6px; }
  .ops-platform {
    display: inline-flex; align-items: center; gap: 4px;
    font-size: 11px; border-radius: 999px; padding: 4px 8px;
    background: var(--surface2); border: 1px solid var(--border); color: var(--text-muted);
  }
  .ops-platform.ok { color: #86efac; border-color: rgba(34,197,94,0.35); }
  .ops-platform.off { color: #fca5a5; border-color: rgba(239,68,68,0.35); }
  .ops-links { color: var(--text-dim); font-size: 12px; }
</style>
</head>
<body>

<div class="header">
  <div class="header-inner">
    <div class="brand">
      <div class="brand-icon">❤</div>
      <div>
        <div class="brand-name">❤Music Dashboard</div>
        <div class="brand-sub">Tyler James Drake · Track Manager</div>
      </div>
    </div>
    <div class="controls">
      <input class="search-box" type="text" placeholder="Search tracks..." id="searchBox" oninput="applyFilters()">
      <div class="meta-pill">Tracks: <strong id="trackCount">0</strong></div>
      <div class="safety-toggle" id="safetyToggle" onclick="toggleSafety()">
        <span class="lock-icon" id="lockIcon">🔒</span>
        <span id="lockLabel">Edit / Delete locked</span>
      </div>
    </div>
  </div>
</div>

<div class="filters" id="statusFilters">
  <button class="filter-btn active" onclick="setStatusFilter('all', this)">All</button>
  <button class="filter-btn" onclick="setStatusFilter('idea', this)">💡 Idea</button>
  <button class="filter-btn" onclick="setStatusFilter('rough', this)">🔶 Rough</button>
  <button class="filter-btn" onclick="setStatusFilter('recorded', this)">🔵 Recorded</button>
  <button class="filter-btn" onclick="setStatusFilter('mixed', this)">🟣 Mixed</button>
  <button class="filter-btn" onclick="setStatusFilter('mastered', this)">✨ Mastered</button>
  <button class="filter-btn" onclick="setStatusFilter('released', this)">🟢 Released</button>
  <button class="filter-btn" onclick="setStatusFilter('demo', this)">🎤 Demo</button>
</div>

<div class="tab-nav">
  <button class="tab-btn active" onclick="switchTab('tracks', this)">🎵 Tracks</button>
  <button class="tab-btn" onclick="switchTab('signatures', this)">🔐 Release Signatures</button>
  <button class="tab-btn" onclick="switchTab('release-ops', this)">📡 Release Ops</button>
  <button class="tab-btn" onclick="switchTab('radio', this)">📻 Radio</button>
</div>

<div class="main">
  <div id="tab-tracks" class="tab-content active">
  <div class="summary-grid" id="summaryGrid"></div>
  <div class="player-shell">
    <div>
      <div class="player-kicker">Master Playback</div>
      <div class="player-title" id="playerTitle">No master selected</div>
      <div class="player-subtitle" id="playerSubtitle">AI Suno and human masters will appear per track when available.</div>
    </div>
    <audio id="masterPlayer" controls preload="metadata"></audio>
  </div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th onclick="sortBy('track_number')"># <span class="sort-arrow" id="sort_track_number"></span></th>
          <th onclick="sortBy('title')">Title <span class="sort-arrow" id="sort_title"></span></th>
          <th onclick="sortBy('album')">Album <span class="sort-arrow" id="sort_album"></span></th>
          <th onclick="sortBy('status')">Status <span class="sort-arrow" id="sort_status"></span></th>
          <th onclick="sortBy('key_signature')">Key <span class="sort-arrow" id="sort_key_signature"></span></th>
          <th onclick="sortBy('tempo_bpm')">BPM <span class="sort-arrow" id="sort_tempo_bpm"></span></th>
          <th onclick="sortBy('genre')">Genre <span class="sort-arrow" id="sort_genre"></span></th>
          <th>Listen</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody id="trackBody"></tbody>
    </table>
  </div>
</div>

<!-- Delete confirmation modal -->
</div><!-- end tab-tracks -->

<div id="tab-signatures" class="tab-content">
  <div class="summary-grid" id="sigSummaryGrid"></div>
  <div class="sig-grid" id="sigGrid">
    <div class="empty-state"><div class="icon">🔐</div>No signatures yet — run sig_analyzer.py on your releases</div>
  </div>
</div>

<div id="tab-release-ops" class="tab-content">
  <div class="summary-grid" id="releaseOpsSummary"></div>
  <div class="ops-panel" id="releaseOpsPanel">
    <h3>Bloom Post-Release Operations</h3>
    <p>Checking releases table, Bloom presence, platform confirmation fields, and signature coverage.</p>
    <div class="ops-chip-row" id="releaseOpsSchema"></div>
  </div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Release</th>
          <th>Status</th>
          <th>Date</th>
          <th>Platforms</th>
          <th>Links</th>
          <th>Notes</th>
        </tr>
      </thead>
      <tbody id="releaseOpsBody">
        <tr><td colspan="6" style="color:var(--text-dim)">Loading release operations data...</td></tr>
      </tbody>
    </table>
  </div>
  <div class="ops-table-note" id="releaseOpsNote"></div>
</div>
</div><!-- end main -->

<div id="tab-radio" class="tab-content">
  <div class="summary-grid" id="radioSummary"></div>
  <div style="display:flex;gap:24px;flex-wrap:wrap;margin-top:16px;">
    <div class="radio-player-card" id="radioPlayerCard">
      <div class="radio-status" id="radioStatus">
        <span class="radio-dot offline" id="radioDot"></span>
        <span id="radioStatusText">Checking...</span>
      </div>
      <div class="radio-now-playing">
        <div class="radio-track-title" id="radioTrackTitle">—</div>
        <div class="radio-track-album" id="radioTrackAlbum">&nbsp;</div>
      </div>
      <div class="radio-controls">
        <button class="radio-play-btn" id="radioPlayBtn" onclick="toggleRadio()">▶</button>
        <div class="radio-vol-row">
          <label>VOL</label>
          <input type="range" id="radioVol" min="0" max="100" value="70" oninput="setRadioVol(this.value)">
        </div>
      </div>
      <div class="radio-stats" id="radioStats"></div>
    </div>
    <div class="radio-history" id="radioHistory">
      <h3>Recently Played</h3>
      <div id="radioHistoryList"><div style="color:var(--text-dim);padding:12px;">Waiting for data...</div></div>
    </div>
    <div class="radio-playlist" id="radioPlaylist">
      <h3>Full Playlist</h3>
      <div id="radioPlaylistList"><div style="color:var(--text-dim);padding:12px;">Loading...</div></div>
    </div>
  </div>
</div>

<!-- Delete confirmation modal -->
<div class="modal-overlay" id="deleteModal">
  <div class="modal">
    <h3>⚠ Delete Track</h3>
    <p>This will permanently remove the track and all associated recordings, lyrics, and catalog entries.</p>
    <div class="track-info" id="deleteTrackInfo"></div>
    <div class="modal-actions">
      <button class="btn btn-cancel" onclick="closeModal()">Cancel</button>
      <button class="btn btn-danger" id="confirmDeleteBtn" onclick="confirmDelete()">Delete forever</button>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
let tracks = [];
let albums = [];
let audioIndex = {};
let editUnlocked = false;
let currentFilter = 'all';
let currentSearch = '';
let sortCol = 'album';
let sortAsc = true;
let pendingDeleteId = null;
let currentAudioPath = null;

async function loadTracks() {
  const [tRes, aRes, audioRes] = await Promise.all([
    fetch('/api/tracks'),
    fetch('/api/albums'),
    fetch('/api/audio/discover')
  ]);
  tracks = await tRes.json();
  albums = await aRes.json();
  audioIndex = await audioRes.json();
  render();
  // Auto-populate master player with a QE-random track on load
  const withAudio = tracks.filter(t => (audioIndex[String(t.id)] || []).length > 0);
  if (withAudio.length > 0) {
    const buf = new Uint32Array(1);
    crypto.getRandomValues(buf);
    const pick = withAudio[buf[0] % withAudio.length];
    const file = audioIndex[String(pick.id)][0];
    currentAudioPath = file.path;
    const player = document.getElementById('masterPlayer');
    player.src = audioUrl(file.path);
    player.load();
    document.getElementById('playerTitle').textContent = pick.title || 'Untitled';
    document.getElementById('playerSubtitle').textContent =
      `${file.type === 'ai' ? 'AI master' : 'Human master'} · ${file.label} · ${(file.size_kb / 1024).toFixed(1)} MB`;
  }
}

function audioUrl(path) {
  return '/audio/' + path.split('/').map(encodeURIComponent).join('/');
}

function renderAudioButtons(track) {
  const files = audioIndex[String(track.id)] || [];
  if (files.length === 0) {
    return '<div class="audio-empty">No playable master</div>';
  }
  return `<div class="audio-chip-row">${files.map((file, idx) => {
    const typeLabel = file.type === 'ai' ? 'AI' : 'Human';
    const variantCount = files.filter(item => item.type === file.type).length;
    const variantIndex = files.slice(0, idx + 1).filter(item => item.type === file.type).length;
    const chipLabel = variantCount > 1 ? `${typeLabel} ${variantIndex}` : typeLabel;
    const active = currentAudioPath === file.path ? 'active' : '';
    const title = esc(`${typeLabel}: ${file.label} (${Math.round(file.size_kb)} KB)`);
    return `<button class="audio-chip ${file.type} ${active}" onclick="playTrack(${track.id}, ${idx})" title="${title}">${chipLabel}</button>`;
  }).join('')}</div>`;
}

async function playTrack(trackId, audioIdx) {
  const files = audioIndex[String(trackId)] || [];
  const file = files[audioIdx];
  const track = tracks.find(item => item.id === trackId);
  if (!file || !track) return;

  currentAudioPath = file.path;
  const player = document.getElementById('masterPlayer');
  player.src = audioUrl(file.path);
  document.getElementById('playerTitle').textContent = track.title || 'Untitled track';
  document.getElementById('playerSubtitle').textContent = `${file.type === 'ai' ? 'AI master' : 'Human master'} · ${file.label} · ${(file.size_kb / 1024).toFixed(1)} MB`;
  render();
  try {
    await player.play();
  } catch (err) {
    showToast('Audio loaded. Press play to start playback.', 'success');
  }
}

function render() {
  let filtered = tracks.filter(t => {
    if (currentFilter !== 'all' && t.status !== currentFilter) return false;
    if (currentSearch) {
      const s = currentSearch.toLowerCase();
      return (t.title||'').toLowerCase().includes(s)
          || (t.album||'').toLowerCase().includes(s)
          || (t.genre||'').toLowerCase().includes(s)
          || (t.key_signature||'').toLowerCase().includes(s);
    }
    return true;
  });

  filtered.sort((a, b) => {
    let va = a[sortCol] ?? '', vb = b[sortCol] ?? '';
    if (typeof va === 'string') va = va.toLowerCase();
    if (typeof vb === 'string') vb = vb.toLowerCase();
    if (va < vb) return sortAsc ? -1 : 1;
    if (va > vb) return sortAsc ? 1 : -1;
    return 0;
  });

  // Summary
  const statuses = {};
  tracks.forEach(t => { statuses[t.status] = (statuses[t.status]||0) + 1; });
  const albumNames = new Set(tracks.map(t => t.album).filter(Boolean));
  document.getElementById('summaryGrid').innerHTML = `
    <div class="summary-card sc-total"><div class="num">${tracks.length}</div><div class="label">Total Tracks</div></div>
    <div class="summary-card sc-albums"><div class="num">${albumNames.size}</div><div class="label">Albums</div></div>
    <div class="summary-card sc-released"><div class="num">${statuses.released||0}</div><div class="label">Released</div></div>
    <div class="summary-card sc-progress"><div class="num">${(statuses.rough||0)+(statuses.recorded||0)+(statuses.mixed||0)+(statuses.mastered||0)}</div><div class="label">In Progress</div></div>
  `;

  document.getElementById('trackCount').textContent = filtered.length;

  // Sort arrows
  document.querySelectorAll('.sort-arrow').forEach(el => el.textContent = '');
  const arrow = document.getElementById('sort_' + sortCol);
  if (arrow) arrow.textContent = sortAsc ? '▲' : '▼';

  // Table
  const tbody = document.getElementById('trackBody');
  if (filtered.length === 0) {
    tbody.innerHTML = '<tr><td colspan="9"><div class="empty-state"><div class="icon">🎵</div>No tracks match your filters</div></td></tr>';
    return;
  }

  tbody.innerHTML = filtered.map(t => {
    const statusList = ['idea','rough','recorded','mixed','mastered','released','demo'];
    const statusOpts = statusList.map(s =>
      `<option value="${s}" ${s===t.status?'selected':''}>${s}</option>`
    ).join('');
    const albumOpts = `<option value=""${!t.album_id ? ' selected' : ''}>—</option>` +
      albums.map(a =>
        `<option value="${a.id}" ${a.id===t.album_id?'selected':''}>${esc(a.title)}</option>`
      ).join('');
    const dis = editUnlocked ? '' : 'disabled';
    return `
    <tr>
      <td><input class="inline-edit num-input" value="${t.track_number ?? ''}"
                 data-id="${t.id}" data-field="track_number" type="number"
                 onchange="saveField(this)" ${dis}></td>
      <td><input class="inline-edit title-input" value="${esc(t.title)}"
                 data-id="${t.id}" data-field="title"
                 onchange="saveField(this)" ${dis}></td>
      <td>
        <select class="album-select" data-id="${t.id}" data-field="album_id"
                onchange="saveField(this)" ${dis}>
          ${albumOpts}
        </select>
      </td>
      <td>
        <select class="status-select" data-id="${t.id}" data-field="status"
                onchange="saveField(this)" ${dis}>
          ${statusOpts}
        </select>
      </td>
      <td><input class="inline-edit key-input" value="${esc(t.key_signature||'')}"
                 data-id="${t.id}" data-field="key_signature"
                 onchange="saveField(this)" ${dis}></td>
      <td><input class="inline-edit bpm-input" value="${t.tempo_bpm ? Math.round(t.tempo_bpm) : ''}"
                 data-id="${t.id}" data-field="tempo_bpm" type="number"
                 onchange="saveField(this)" ${dis}></td>
      <td><input class="inline-edit genre-input" value="${esc(t.genre||'')}"
                 data-id="${t.id}" data-field="genre"
                 onchange="saveField(this)" ${dis}></td>
      <td class="listen-cell">${renderAudioButtons(t)}</td>
      <td>
        <button class="delete-btn ${editUnlocked ? 'enabled' : ''}"
                onclick="requestDelete(${t.id})"
                ${dis}>
          🗑
        </button>
      </td>
    </tr>`;
  }).join('');
}

function esc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function toggleSafety() {
  editUnlocked = !editUnlocked;
  const toggle = document.getElementById('safetyToggle');
  const icon = document.getElementById('lockIcon');
  const label = document.getElementById('lockLabel');
  if (editUnlocked) {
    toggle.classList.add('unlocked');
    icon.textContent = '🔓';
    label.textContent = 'Edit / Delete unlocked';
  } else {
    toggle.classList.remove('unlocked');
    icon.textContent = '🔒';
    label.textContent = 'Edit / Delete locked';
  }
  render();
}

function setStatusFilter(status, btn) {
  currentFilter = status;
  document.querySelectorAll('#statusFilters .filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  applyFilters();
}

function applyFilters() {
  currentSearch = document.getElementById('searchBox').value;
  render();
}

function sortBy(col) {
  if (sortCol === col) { sortAsc = !sortAsc; }
  else { sortCol = col; sortAsc = true; }
  render();
}

function requestDelete(id) {
  if (!editUnlocked) return;
  pendingDeleteId = id;
  const t = tracks.find(x => x.id === id);
  const info = document.getElementById('deleteTrackInfo');
  info.textContent = '';
  const strong = document.createElement('strong');
  strong.textContent = t ? t.title : 'Unknown';
  info.appendChild(strong);
  if (t && t.album) {
    info.appendChild(document.createTextNode(' — ' + t.album));
  }
  document.getElementById('deleteModal').classList.add('show');
}

function closeModal() {
  document.getElementById('deleteModal').classList.remove('show');
  pendingDeleteId = null;
}

async function confirmDelete() {
  if (pendingDeleteId === null) return;
  const id = pendingDeleteId;
  closeModal();
  try {
    const res = await fetch(`/api/tracks/${id}`, { method: 'DELETE' });
    const data = await res.json();
    if (data.ok) {
      showToast('Track deleted', 'success');
      tracks = tracks.filter(t => t.id !== id);
      render();
    } else {
      showToast(data.error || 'Delete failed', 'error');
    }
  } catch (e) {
    showToast('Network error', 'error');
  }
}

function showToast(msg, type) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast ' + type + ' show';
  setTimeout(() => { t.classList.remove('show'); }, 3000);
}

async function saveField(el) {
  const id = parseInt(el.dataset.id);
  const field = el.dataset.field;
  let value = el.value.trim();
  if (field === 'tempo_bpm' || field === 'track_number' || field === 'album_id')
    value = value ? parseFloat(value) : null;
  if (value === '') value = null;

  try {
    const res = await fetch(`/api/tracks/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ [field]: value }),
    });
    const data = await res.json();
    if (data.ok) {
      // Update local data
      const t = tracks.find(x => x.id === id);
      if (t) t[field] = value;
      showToast('Saved', 'success');
      // Update album name if album_id changed
      if (field === 'album_id') {
        const alb = albums.find(a => a.id === value);
        t.album = alb ? alb.title : null;
      }
      // Re-render if status or album changed
      if (field === 'status' || field === 'album_id') render();
    } else {
      showToast(data.error || 'Save failed', 'error');
    }
  } catch (e) {
    showToast('Network error', 'error');
  }
}

loadTracks();

// ── Tab switching ──
function switchTab(tab, btn) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-' + tab).classList.add('active');
  if (tab === 'signatures' && !signaturesLoaded) loadSignatures();
  if (tab === 'release-ops' && !releaseOpsLoaded) loadReleaseOps();
  if (tab === 'radio' && !radioLoaded) loadRadio();
}

// ── Signatures ──
let signatures = [];
let signaturesLoaded = false;
let releaseOpsLoaded = false;

async function loadSignatures() {
  const res = await fetch('/api/signatures');
  signatures = await res.json();
  signaturesLoaded = true;
  renderSignatures();
}

function renderSignatures() {
  // Summary
  const platforms = {};
  const formats = {};
  let humanCount = 0, aiCount = 0, quantumCount = 0;
  signatures.forEach(s => {
    platforms[s.source_platform || 'unknown'] = (platforms[s.source_platform || 'unknown'] || 0) + 1;
    formats[s.file_format || '?'] = (formats[s.file_format || '?'] || 0) + 1;
    if (s.source_platform === 'suno') aiCount++;
    else humanCount++;
    if (s.quantum_source === 'ibm_quantum_cache') quantumCount++;
  });
  document.getElementById('sigSummaryGrid').innerHTML = `
    <div class="summary-card sc-total"><div class="num">${signatures.length}</div><div class="label">Signatures</div></div>
    <div class="summary-card sc-progress"><div class="num">${humanCount}</div><div class="label">Human Master</div></div>
    <div class="summary-card sc-released"><div class="num">${aiCount}</div><div class="label">AI Master</div></div>
    <div class="summary-card sc-albums"><div class="num">${quantumCount}</div><div class="label">Quantum Signed</div></div>
  `;

  const grid = document.getElementById('sigGrid');
  if (signatures.length === 0) {
    grid.innerHTML = '<div class="empty-state"><div class="icon">🔐</div>No signatures yet — run sig_analyzer.py</div>';
    return;
  }

  grid.innerHTML = signatures.map(s => {
    const entPct = ((s.entropy_header || 0) / 8 * 100).toFixed(0);
    const entMidPct = ((s.entropy_mid || 0) / 8 * 100).toFixed(0);
    const dur = s.duration_sec ? `${Math.floor(s.duration_sec / 60)}m ${(s.duration_sec % 60).toFixed(0)}s` : '—';
    const fname = (s.file_path || '').split(/[/\\]/).pop();
    const platform = s.source_platform || 'manual';
    const platClass = platform === 'suno' ? 'suno' : 'manual';
    const isAI = platform === 'suno';
    const masterType = isAI ? 'ai' : 'human';
    const masterLabel = isAI ? '🤖 AI Master (Suno)' : '🎸 Human Master (Hyperthreat)';
    const top10 = JSON.parse(s.byte_freq_top10 || '[]');
    const topBytes = top10.slice(0, 5).map(b => `${b.byte}=${b.pct}%`).join(', ');

    // Hash section
    const hashLines = [];
    if (s.md5) hashLines.push(`<span class="hash-label">MD5</span><span class="hash-value">${s.md5}</span>`);
    if (s.sha256) hashLines.push(`<span class="hash-label">SHA-256</span><span class="hash-value">${s.sha256}</span>`);
    if (s.blake2s) hashLines.push(`<span class="hash-label">BLAKE2s</span><span class="hash-value">${s.blake2s}</span>`);
    if (s.sha512) hashLines.push(`<span class="hash-label">SHA-512</span><span class="hash-value">${(s.sha512||'').slice(0,64)}…</span>`);
    if (s.sha512_224) hashLines.push(`<span class="hash-label">SHA-512/224</span><span class="hash-value">${s.sha512_224}</span>`);
    if (s.sha512_256) hashLines.push(`<span class="hash-label">SHA-512/256</span><span class="hash-value">${s.sha512_256}</span>`);
    if (s.shake_128) hashLines.push(`<span class="hash-label">SHAKE-128</span><span class="hash-value">${s.shake_128}</span>`);
    if (s.shake_256) hashLines.push(`<span class="hash-label">SHAKE-256</span><span class="hash-value">${(s.shake_256||'').slice(0,64)}…</span>`);
    if (s.whirlpool) hashLines.push(`<span class="hash-label">Whirlpool</span><span class="hash-value">${(s.whirlpool||'').slice(0,64)}…</span>`);
    const hashHtml = hashLines.length > 0
      ? `<div class="sig-section"><div class="sig-section-title">Deterministic Hashes (9)</div><div class="hash-list">${hashLines.join('<br>')}</div></div>`
      : '';

    // Quantum + AEAD section
    let quantumHtml = '';
    if (s.quantum_salt) {
      const qLines = [];
      qLines.push(`<span class="hash-label">Q-Salt</span><span class="hash-value">${s.quantum_salt}</span>`);
      qLines.push(`<span class="hash-label">BLAKE2b</span><span class="hash-value">${(s.quantum_blake2b||'').slice(0,64)}…</span>`);
      qLines.push(`<span class="hash-label">SHA3-512</span><span class="hash-value">${(s.quantum_sha3_512||'').slice(0,64)}…</span>`);
      if (s.chacha20_poly1305_seal) qLines.push(`<span class="hash-label">ChaCha20</span><span class="hash-value">${(s.chacha20_poly1305_seal||'').slice(0,48)}…</span>`);
      if (s.aesgcm_seal) qLines.push(`<span class="hash-label">AES-GCM</span><span class="hash-value">${(s.aesgcm_seal||'').slice(0,48)}…</span>`);
      const badges = [];
      if (s.chacha20_poly1305_seal) badges.push('<span class="aead-badge">ChaCha20-Poly1305</span>');
      if (s.aesgcm_seal) badges.push('<span class="aead-badge">AES-256-GCM</span>');
      badges.push(`<span class="quantum-badge">${s.quantum_source === 'ibm_quantum_cache' ? '⚛ IBM Quantum' : '⚠ Classical'} · ${s.quantum_entropy_bits}b</span>`);
      quantumHtml = `<div class="sig-section"><div class="sig-section-title">Quantum + AEAD Seals</div>
        <div style="margin-bottom:6px">${badges.join(' ')}</div>
        <div class="hash-list">${qLines.join('<br>')}</div>
        <div style="margin-top:4px;font-size:10px;color:var(--text-dim)">Signed: ${s.quantum_signed_at || '—'}</div>
      </div>`;
    }

    return `
    <div class="sig-card">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px">
        <h4>${esc(s.track_title || fname)}</h4>
        <div style="display:flex;align-items:center;gap:6px">
          <span class="master-type-badge ${masterType}">${masterLabel}</span>
          <span class="sig-format">${esc(s.file_format)} · ${esc(s.codec || '?')}</span>
          ${s.sig_version ? '<span class="sig-version-badge">v' + esc(s.sig_version) + '</span>' : ''}
        </div>
      </div>
      <dl class="sig-meta">
        <dt>File</dt><dd style="font-size:11px">${esc(fname)}</dd>
        <dt>Size</dt><dd>${(s.file_size_bytes/1024/1024).toFixed(2)} MB · ${dur}</dd>
        <dt>Audio</dt><dd>${s.sample_rate_hz ? s.sample_rate_hz.toLocaleString() + ' Hz' : '—'} · ${s.channels || '?'}ch${s.bits_per_sample ? ' · ' + s.bits_per_sample + '-bit' : ''} · ${s.bitrate_kbps ? s.bitrate_kbps + ' kbps' : '—'}</dd>
        <dt>Entropy</dt><dd>
          hdr ${s.entropy_header}/8.0 <div class="entropy-bar"><div class="entropy-fill" style="width:${entPct}%"></div></div>
          mid ${s.entropy_mid}/8.0 <div class="entropy-bar"><div class="entropy-fill" style="width:${entMidPct}%"></div></div>
        </dd>
        <dt>Crossings</dt><dd>${s.boundary_crossings ? s.boundary_crossings.toLocaleString() : '—'} (${s.crossing_rate_pct || 0}%)</dd>
      </dl>
      ${hashHtml}
      ${quantumHtml}
      <div class="sig-provenance">
        <span class="platform-badge ${platClass}">${platform}</span>
        ${s.provenance_id ? '<span>ID: ' + esc(s.provenance_id) + '</span>' : ''}
        ${s.created_timestamp ? ' · ' + esc(s.created_timestamp) : ''}
        ${s.pipeline ? '<br>Release Path: ' + esc(s.pipeline) : ''}
      </div>
    </div>`;
  }).join('');
}

// ── Release Ops ──
async function loadReleaseOps() {
  const res = await fetch('/api/release_ops');
  const data = await res.json();
  releaseOpsLoaded = true;
  renderReleaseOps(data);
}

function renderReleaseOps(data) {
  const bloomAlbums = data.bloom_albums || [];
  const rows = data.release_rows || [];
  const missing = data.missing_columns || [];
  const schemaChips = [];
  if (data.releases_table_exists) schemaChips.push('<span class="ops-chip ok">Releases table present</span>');
  else schemaChips.push('<span class="ops-chip warn">Releases table missing</span>');
  if (missing.length) schemaChips.push(`<span class="ops-chip warn">Missing ${missing.length} release-op columns</span>`);
  else schemaChips.push('<span class="ops-chip ok">Recommended release-op columns present</span>');
  if (bloomAlbums.length) schemaChips.push(`<span class="ops-chip ok">Bloom album found (${bloomAlbums.length})</span>`);
  else schemaChips.push('<span class="ops-chip warn">Bloom album not found</span>');
  document.getElementById('releaseOpsSchema').innerHTML = schemaChips.join('');

  document.getElementById('releaseOpsSummary').innerHTML = `
    <div class="summary-card sc-total"><div class="num">${rows.length}</div><div class="label">Release Rows</div></div>
    <div class="summary-card sc-progress"><div class="num">${data.bloom_track_count || 0}</div><div class="label">Bloom Tracks</div></div>
    <div class="summary-card sc-albums"><div class="num">${data.bloom_signature_count || 0}</div><div class="label">Bloom Signatures</div></div>
    <div class="summary-card sc-released"><div class="num">${data.confirmed_platform_count || 0}</div><div class="label">Confirmed Platforms</div></div>
  `;

  const noteBits = [];
  if (data.status_note) noteBits.push(esc(data.status_note));
  if (missing.length) noteBits.push(`Schema gaps: ${missing.map(esc).join(', ')}`);
  document.getElementById('releaseOpsNote').textContent = noteBits.join(' | ');

  const body = document.getElementById('releaseOpsBody');
  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="6" style="color:var(--text-dim)">No release rows yet. The tab is ready, but release records still need to be populated.</td></tr>';
    return;
  }

  body.innerHTML = rows.map(row => {
    const title = esc(row.title || row.release_title || row.album_title || row.name || `Release ${row.id || '?'}`);
    const status = esc(row.status || row.release_status || row.distribution_status || 'unknown');
    const date = esc(row.release_date || row.released_at || row.created_at || row.updated_at || '—');
    const platformHtml = renderPlatforms(row, data.confirmation_columns || []);
    const linkCount = countLinks(row.platform_urls);
    const linkLabel = linkCount ? `${linkCount} link${linkCount === 1 ? '' : 's'}` : '—';
    const notes = [];
    if (row.soundexchange_id) notes.push('SoundExchange ID set');
    if (!platformHtml) notes.push('No platform confirmations recorded');
    return `
      <tr>
        <td>${title}</td>
        <td>${status}</td>
        <td>${date}</td>
        <td>${platformHtml || '<span class="ops-links">—</span>'}</td>
        <td><span class="ops-links">${linkLabel}</span></td>
        <td><span class="ops-links">${notes.join(' · ') || '—'}</span></td>
      </tr>`;
  }).join('');
}

function renderPlatforms(row, cols) {
  const items = cols.map(col => {
    const name = col.replace(/_confirmed$/, '').replace(/_/g, ' ');
    const value = !!row[col];
    return `<span class="ops-platform ${value ? 'ok' : 'off'}">${value ? '●' : '○'} ${esc(name)}</span>`;
  });
  return items.length ? `<div class="ops-platforms">${items.join('')}</div>` : '';
}

function countLinks(raw) {
  if (!raw) return 0;
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
    if (parsed && typeof parsed === 'object') return Object.keys(parsed).length;
  } catch (e) {}
  return 0;
}

// ── Radio ──
const RADIO_URL = 'http://localhost:8100';
let radioLoaded = false;
let radioPlaying = false;
let radioAudio = new Audio();
radioAudio.volume = 0.7;
let radioPoller = null;

async function loadRadio() {
  radioLoaded = true;
  await pollRadio();
  await loadRadioPlaylist();
  if (!radioPoller) radioPoller = setInterval(pollRadio, 3000);
}

async function pollRadio() {
  try {
    const r = await fetch('/api/radio/now_playing');
    const d = await r.json();
    if (d.error) {
      document.getElementById('radioDot').className = 'radio-dot offline';
      document.getElementById('radioStatusText').textContent = 'Offline';
      document.getElementById('radioTrackTitle').textContent = '—';
      document.getElementById('radioTrackAlbum').innerHTML = '&nbsp;';
      document.getElementById('radioSummary').innerHTML = mkSummaryCard('Status', 'Offline') + mkSummaryCard('Stream', RADIO_URL);
      return;
    }
    document.getElementById('radioDot').className = 'radio-dot online';
    document.getElementById('radioStatusText').textContent = 'LIVE';
    document.getElementById('radioTrackTitle').textContent = d.title || 'Starting...';
    document.getElementById('radioTrackAlbum').textContent = d.album || '';
    const m = Math.floor((d.uptime_sec||0) / 60);
    const s = Math.floor((d.uptime_sec||0) % 60);
    document.getElementById('radioStats').innerHTML =
      `<div>Listeners: <span class="stat-val">${d.listeners}</span></div>` +
      `<div>Tracks: <span class="stat-val">${d.total_tracks}</span></div>` +
      `<div>Uptime: <span class="stat-val">${m}:${String(s).padStart(2,'0')}</span></div>`;
    document.getElementById('radioSummary').innerHTML =
      mkSummaryCard('Status', '<span style=\"color:#22c55e\">● LIVE</span>') +
      mkSummaryCard('Listeners', d.listeners) +
      mkSummaryCard('Catalog', d.total_tracks + ' tracks') +
      mkSummaryCard('Uptime', m + ':' + String(s).padStart(2,'0'));
    // History
    const hist = (d.history || []).slice().reverse();
    const hEl = document.getElementById('radioHistoryList');
    if (hist.length) {
      hEl.innerHTML = hist.map(h =>
        `<div class="rh-item"><div><span class="rh-title">${esc(h.title)}</span><br><span class="rh-album">${esc(h.album)}</span></div><span class="rh-time">${esc(h.started_at)}</span></div>`
      ).join('');
    }
  } catch(e) {
    document.getElementById('radioDot').className = 'radio-dot offline';
    document.getElementById('radioStatusText').textContent = 'Offline';
  }
}

function mkSummaryCard(label, val) {
  return `<div class="summary-card"><div class="summary-value">${val}</div><div class="summary-label">${label}</div></div>`;
}

async function loadRadioPlaylist() {
  try {
    const r = await fetch('/api/radio/playlist');
    const tracks = await r.json();
    const el = document.getElementById('radioPlaylistList');
    if (tracks.length) {
      el.innerHTML = tracks.map((t, i) =>
        `<div class="rpl-item">${i+1}. ${esc(t.title)} <span style="color:var(--text-muted)">· ${esc(t.album)}</span></div>`
      ).join('');
    }
  } catch(e) {}
}

function toggleRadio() {
  if (radioPlaying) {
    radioAudio.pause();
    radioAudio.src = '';
    radioPlaying = false;
    document.getElementById('radioPlayBtn').innerHTML = '&#9654;';
  } else {
    radioAudio.src = RADIO_URL + '/stream?t=' + Date.now();
    radioAudio.play().catch(e => console.error('Radio play error:', e));
    radioPlaying = true;
    document.getElementById('radioPlayBtn').innerHTML = '&#9724;';
  }
}
function setRadioVol(v) { radioAudio.volume = v / 100; }
</script>
</body>
</html>
"""


# ── API Routes ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)


@app.route("/api/albums")
def api_albums():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, title, status FROM albums ORDER BY title"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/tracks")
def api_tracks():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT t.id, t.track_number, t.title, t.key_signature,
                   t.tempo_bpm, t.genre, t.status, t.notes,
                   t.album_id, a.title AS album
            FROM tracks t
            LEFT JOIN albums a ON a.id = t.album_id
            ORDER BY a.title, t.track_number
            """
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/signatures")
def api_signatures():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT rs.*, t.title AS track_title, a.title AS album_title
            FROM release_signatures rs
            LEFT JOIN tracks t ON t.id = rs.track_id
            LEFT JOIN albums a ON a.id = t.album_id
            ORDER BY rs.analyzed_at DESC
            """
        ).fetchall()
    return jsonify([dict(r) for r in rows])


def _table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


_ALLOWED_TABLES = frozenset({"tracks", "albums", "releases", "recordings", "lyrics", "catalog_index",
                              "artist_profiles", "release_signatures", "catalog_audio_files"})


def _table_columns(conn, table_name: str) -> list[str]:
    if table_name not in _ALLOWED_TABLES:
        raise ValueError(f"Unknown table: {table_name!r}")
    pragma_sql = "PRAGMA table_info(" + table_name + ")"
    return [row[1] for row in conn.execute(pragma_sql).fetchall()]


def _row_mentions_bloom(row: dict) -> bool:
    for value in row.values():
        if isinstance(value, str) and "bloom" in value.lower():
            return True
    return False


@app.route("/api/release_ops")
def api_release_ops():
    recommended_columns = [
        "spotify_confirmed", "apple_confirmed", "amazon_confirmed", "youtube_confirmed",
        "deezer_confirmed", "pandora_confirmed", "iheart_confirmed", "bandcamp_confirmed",
        "audius_confirmed", "platform_urls", "soundexchange_id",
    ]

    with get_connection() as conn:
        bloom_albums = conn.execute(
            "SELECT id, title, status FROM albums WHERE lower(title) LIKE '%bloom%' ORDER BY title"
        ).fetchall() if _table_exists(conn, "albums") else []
        bloom_album_ids = [row["id"] for row in bloom_albums]

        bloom_track_count = 0
        bloom_signature_count = 0
        if bloom_album_ids and _table_exists(conn, "tracks"):
            placeholders = ",".join("?" for _ in bloom_album_ids)
            count_tracks_sql = "SELECT COUNT(*) FROM tracks WHERE album_id IN (" + placeholders + ")"
            bloom_track_count = conn.execute(
                count_tracks_sql,
                bloom_album_ids,
            ).fetchone()[0]
            if _table_exists(conn, "release_signatures"):
                count_signatures_sql = (
                    "SELECT COUNT(*) "
                    "FROM release_signatures rs "
                    "JOIN tracks t ON t.id = rs.track_id "
                    "WHERE t.album_id IN (" + placeholders + ")"
                )
                bloom_signature_count = conn.execute(
                    count_signatures_sql,
                    bloom_album_ids,
                ).fetchone()[0]

        releases_table_exists = _table_exists(conn, "releases")
        release_columns = _table_columns(conn, "releases") if releases_table_exists else []
        missing_columns = [col for col in recommended_columns if col not in release_columns]
        confirmation_columns = [col for col in release_columns if col.endswith("_confirmed")]
        release_rows: list[dict] = []
        status_note = ""

        if releases_table_exists:
            rows = conn.execute("SELECT * FROM releases ORDER BY id DESC LIMIT 25").fetchall()
            release_rows = [dict(row) for row in rows]
            bloom_rows = [row for row in release_rows if _row_mentions_bloom(row)]
            if bloom_rows:
                release_rows = bloom_rows
                status_note = "Showing Bloom-related release rows."
            elif release_rows:
                status_note = "No Bloom-specific release rows detected; showing recent release rows instead."
            else:
                status_note = "Releases table exists, but no release rows were found yet."
        else:
            status_note = "Releases table does not exist yet."

        confirmed_platform_count = 0
        for row in release_rows:
            for col in confirmation_columns:
                if row.get(col):
                    confirmed_platform_count += 1

    return jsonify({
        "releases_table_exists": releases_table_exists,
        "release_columns": release_columns,
        "missing_columns": missing_columns,
        "confirmation_columns": confirmation_columns,
        "bloom_albums": [dict(row) for row in bloom_albums],
        "bloom_track_count": bloom_track_count,
        "bloom_signature_count": bloom_signature_count,
        "release_rows": release_rows,
        "confirmed_platform_count": confirmed_platform_count,
        "status_note": status_note,
    })


def _slugify_name(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def _audio_label(path: Path) -> str:
    stem = path.stem.replace("$", " ").replace("+", " ").replace("_", " ")
    return " ".join(stem.split())


def _classify_audio_type(file_name: str, source_platform: str | None, fallback: str) -> str:
    lower_name = file_name.lower()
    platform = (source_platform or "").lower()
    if platform == "suno" or "suno" in lower_name or " ai " in f" {lower_name} ":
        return "ai"
    if platform and platform != "suno":
        return "human"
    if "human" in lower_name or "protools" in lower_name or "ptx" in lower_name:
        return "human"
    return fallback


def _relative_audio_path(path_value: str | Path) -> str | None:
    path = Path(path_value)
    resolved_root = CATALOG_ROOT.resolve()
    resolved = path.resolve() if path.is_absolute() else (resolved_root / path).resolve()
    try:
        return resolved.relative_to(resolved_root).as_posix()
    except ValueError:
        return None


@app.route("/api/audio/discover")
def api_audio_discover():
    with get_connection() as conn:
        tracks = conn.execute(
            """
            SELECT t.id, t.title, a.title AS album
            FROM tracks t
            LEFT JOIN albums a ON a.id = t.album_id
            ORDER BY a.title, t.track_number, t.title
            """
        ).fetchall()
        signatures = conn.execute(
            """
            SELECT rs.track_id, rs.file_path, rs.file_format, rs.source_platform,
                   t.title AS track_title, a.title AS album_title
            FROM release_signatures rs
            LEFT JOIN tracks t ON t.id = rs.track_id
            LEFT JOIN albums a ON a.id = t.album_id
            WHERE rs.track_id IS NOT NULL AND rs.file_path IS NOT NULL
            ORDER BY rs.analyzed_at DESC
            """
        ).fetchall()

    track_index = {
        int(track["id"]): {
            "title": track["title"] or "",
            "album": track["album"] or "",
        }
        for track in tracks
    }
    audio_by_track: dict[str, list[dict[str, object]]] = {str(track_id): [] for track_id in track_index}
    seen_paths: dict[str, set[str]] = {str(track_id): set() for track_id in track_index}

    for row in signatures:
        track_id = str(row["track_id"])
        rel_path = _relative_audio_path(row["file_path"])
        if not rel_path:
            continue
        abs_path = (CATALOG_ROOT / rel_path).resolve()
        if not abs_path.exists() or abs_path.suffix.lower() != ".mp3":
            continue
        if rel_path in seen_paths[track_id]:
            continue
        seen_paths[track_id].add(rel_path)
        audio_by_track[track_id].append({
            "path": rel_path,
            "type": _classify_audio_type(abs_path.name, row["source_platform"], "human"),
            "format": (row["file_format"] or abs_path.suffix.lstrip(".")).lower(),
            "label": _audio_label(abs_path),
            "size_kb": round(abs_path.stat().st_size / 1024, 1),
        })

    masters_root = CATALOG_ROOT / "masters"
    ep_root = CATALOG_ROOT / "ep"
    for track_id, meta in track_index.items():
        key = str(track_id)
        if audio_by_track[key]:
            continue
        track_slug = _slugify_name(meta["title"])
        album_slug = _slugify_name(meta["album"])
        candidate_dirs: list[Path] = []
        if masters_root.exists():
            if album_slug:
                candidate_dirs.extend(
                    path for path in masters_root.glob("*/*")
                    if path.is_dir()
                    and _slugify_name(path.parent.name) == album_slug
                    and _slugify_name(path.name) == track_slug
                )
            candidate_dirs.extend(
                path for path in masters_root.glob("*/*")
                if path.is_dir() and _slugify_name(path.name) == track_slug and path not in candidate_dirs
            )
        if ep_root.exists():
            candidate_dirs.extend(
                path for path in ep_root.iterdir()
                if path.is_dir() and _slugify_name(path.name) == track_slug and path not in candidate_dirs
            )

        for directory in candidate_dirs:
            for file_path in sorted(directory.glob("*.mp3")):
                rel_path = _relative_audio_path(file_path)
                if not rel_path or rel_path in seen_paths[key]:
                    continue
                seen_paths[key].add(rel_path)
                audio_by_track[key].append({
                    "path": rel_path,
                    "type": _classify_audio_type(file_path.name, None, "human"),
                    "format": file_path.suffix.lstrip(".").lower(),
                    "label": _audio_label(file_path),
                    "size_kb": round(file_path.stat().st_size / 1024, 1),
                })

        audio_by_track[key].sort(key=lambda item: (item["type"] != "ai", str(item["label"])))

    return jsonify(audio_by_track)


@app.route("/audio/<path:filepath>")
def serve_audio(filepath: str):
    resolved_root = CATALOG_ROOT.resolve()
    requested = (resolved_root / filepath).resolve()
    if resolved_root not in requested.parents:
        return jsonify({"ok": False, "error": "Invalid path"}), 400
    if not requested.exists() or not requested.is_file():
        return jsonify({"ok": False, "error": "Audio file not found"}), 404
    if requested.suffix.lower() != ".mp3":
        return jsonify({"ok": False, "error": "Unsupported audio format"}), 400
    return send_file(requested, mimetype="audio/mpeg")


# ── Radio proxy routes (forward to TJD Radio on port 8100) ────────────────────

RADIO_BASE = "http://localhost:8100"


@app.route("/api/radio/now_playing")
def api_radio_now_playing():
    try:
        req = urllib.request.urlopen(f"{RADIO_BASE}/api/now_playing", timeout=2)
        data = json.loads(req.read())
        return jsonify(data)
    except (urllib.error.URLError, OSError):
        return jsonify({"error": "Radio offline", "title": "Offline", "listeners": 0})


@app.route("/api/radio/playlist")
def api_radio_playlist():
    try:
        req = urllib.request.urlopen(f"{RADIO_BASE}/api/playlist", timeout=2)
        data = json.loads(req.read())
        return jsonify(data)
    except (urllib.error.URLError, OSError):
        return jsonify([])


@app.route("/api/tracks/<int:track_id>", methods=["PATCH"])
def api_update_track(track_id: int):
    ALLOWED_FIELDS = {"title", "track_number", "album_id", "key_signature", "tempo_bpm", "genre", "status"}
    ALLOWED_STATUSES = {"idea", "rough", "recorded", "mixed", "mastered", "released", "demo"}

    data = request.get_json(silent=True) or {}
    updates = {k: v for k, v in data.items() if k in ALLOWED_FIELDS}
    if not updates:
        return jsonify({"ok": False, "error": "No valid fields to update"}), 400

    if "status" in updates and updates["status"] not in ALLOWED_STATUSES:
        return jsonify({"ok": False, "error": f"Invalid status: {updates['status']}"}), 400

    if "tempo_bpm" in updates and updates["tempo_bpm"] is not None:
        try:
            updates["tempo_bpm"] = float(updates["tempo_bpm"])
        except (ValueError, TypeError):
            return jsonify({"ok": False, "error": "BPM must be a number"}), 400

    if "track_number" in updates and updates["track_number"] is not None:
        try:
            updates["track_number"] = int(updates["track_number"])
        except (ValueError, TypeError):
            return jsonify({"ok": False, "error": "Track number must be an integer"}), 400

    if "album_id" in updates and updates["album_id"] is not None:
        try:
            updates["album_id"] = int(updates["album_id"])
        except (ValueError, TypeError):
            return jsonify({"ok": False, "error": "Invalid album"}), 400

    if "title" in updates and not updates.get("title"):
        return jsonify({"ok": False, "error": "Title cannot be empty"}), 400

    with get_connection() as conn:
        track = conn.execute("SELECT id FROM tracks WHERE id = ?", (track_id,)).fetchone()
        if not track:
            return jsonify({"ok": False, "error": "Track not found"}), 404

        set_clause = ", ".join(k + " = ?" for k in updates)
        update_sql = "UPDATE tracks SET " + set_clause + " WHERE id = ?"
        values = list(updates.values()) + [track_id]
        conn.execute(update_sql, values)
        conn.commit()

    return jsonify({"ok": True, "updated": updates})


@app.route("/api/tracks/<int:track_id>", methods=["DELETE"])
def api_delete_track(track_id: int):
    with get_connection() as conn:
        track = conn.execute("SELECT id, title FROM tracks WHERE id = ?", (track_id,)).fetchone()
        if not track:
            return jsonify({"ok": False, "error": "Track not found"}), 404

        # Cascade: remove related rows first
        conn.execute("DELETE FROM recordings WHERE track_id = ?", (track_id,))
        conn.execute("DELETE FROM lyrics WHERE track_id = ?", (track_id,))
        conn.execute("DELETE FROM catalog_index WHERE track_id = ?", (track_id,))
        conn.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
        conn.commit()

    return jsonify({"ok": True, "deleted_id": track_id})


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="❤Music Interactive Dashboard")
    parser.add_argument("--port", type=int, default=5051, help="Port to run on (default: 5051)")
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open browser")
    args = parser.parse_args()

    if not args.no_open:
        import threading
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{args.port}")).start()

    print(f"❤Music Dashboard → http://localhost:{args.port}")
    app.run(host="127.0.0.1", port=args.port, debug=False)


if __name__ == "__main__":
    main()
