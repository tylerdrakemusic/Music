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
import re
import subprocess
import sys
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, render_template, render_template_string, request, send_file

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.init_db import get_connection
from analysis.rhyme_utils import build_suffix_map, get_phonetic_group, last_word

CATALOG_ROOT = Path(__file__).resolve().parent.parent.parent / "catalog"

# ── Ollama (optional) ─────────────────────────────────────────────────────────
_OLLAMA_AVAILABLE = False
_OLLAMA_BASE_URL = None
_OLLAMA_MODEL = "llama3.3:70b"
_OLLAMA_FALLBACK_MODEL_ORDER = ["llama3:70b", "llama3.1:8b"]
_OLLAMA_HOOK_LINE_LIMIT = 30
try:
    import os as _os
    _workspace_root = None
    _workspace_env = _os.environ.get("WORKSPACE_ROOT")
    if _workspace_env:
        _workspace_path = Path(_workspace_env)
        if _workspace_path.is_dir():
            _workspace_root = _workspace_path

    if _workspace_root is None:
        file_path = Path(__file__).resolve()
        for parent in [file_path, *file_path.parents]:
            candidate = parent / "⊕Workspace"
            if candidate.is_dir():
                _workspace_root = candidate
                break
            candidate = parent / "workspace"
            if candidate.is_dir():
                _workspace_root = candidate
                break

    if _workspace_root is None:
        _drive_root = Path(__file__).resolve().anchor
        for _entry in Path(_drive_root).iterdir():
            if _entry.is_dir() and (
                _entry.name == "⊕Workspace"
                or _entry.name.endswith("Workspace")
                or _entry.name.lower() == "workspace"
            ):
                _workspace_root = _entry
                break

    if _workspace_root is not None:
        sys.path.insert(0, str(_workspace_root))

    _OLLAMA_MODEL = _os.environ.get("OLLAMA_MODEL") or _OLLAMA_MODEL
    from src.integrations.ollama.client import OllamaClient as _OllamaClient
    try:
        client = _OllamaClient(model=_OLLAMA_MODEL)
        if client.health_check():
            if client.ensure_model_available(_OLLAMA_MODEL):
                _OLLAMA_AVAILABLE = True
            else:
                available_models: list[str] = []
                try:
                    available_models = [
                        m.get("name") or m.get("model")
                        for m in client.list_models()
                    ]
                except Exception:
                    available_models = []

                fallback_model: str | None = None
                for candidate in available_models:
                    if candidate and "70b" in candidate:
                        fallback_model = candidate
                        break
                if fallback_model is None and available_models:
                    fallback_model = available_models[0]

                if fallback_model is not None:
                    client = _OllamaClient(model=fallback_model)
                    if client.ensure_model_available(fallback_model):
                        _OLLAMA_MODEL = fallback_model
                        _OLLAMA_AVAILABLE = True
            if _OLLAMA_AVAILABLE:
                _OLLAMA_BASE_URL = client.base_url
    except Exception:
        _OLLAMA_AVAILABLE = False
        _OLLAMA_BASE_URL = None
except Exception as exc:
    _OLLAMA_AVAILABLE = False
    _OLLAMA_IMPORT_ERROR = exc

# ── make_chord_sheet (optional) ───────────────────────────────────────────────
try:
    _CHORD_SHEET_TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
    if str(_CHORD_SHEET_TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(_CHORD_SHEET_TOOLS_DIR))
    from make_chord_sheet import build_docx, compute_output_path  # type: ignore[import]
    _CHORD_SHEET_AVAILABLE = True
except Exception as exc:
    _CHORD_SHEET_AVAILABLE = False
    _CHORD_SHEET_IMPORT_ERROR = exc

_CS_ROOT = Path(__file__).resolve().parents[2]
_CATALOG_ROOT = Path(__file__).resolve().parents[2].parent / "catalog"
_CHORD_SHEET_TEMPLATES_DIR = _CS_ROOT / "studio_master" / "song_templates"
_CHORD_SHEET_DOCS_DIR = _CATALOG_ROOT / "sheet_music" / "covers"


def _cs_sanitize(name: str) -> str:
    """Sanitize a string to a safe filename component."""
    keep = " _-.()[]{}+"
    return "".join(c for c in name if c.isalnum() or c in keep).strip().replace(" ", "_")


def _select_fallback_ollama_models(client, selected_model: str) -> list[str]:
    try:
        available = [
            m.get("name") or m.get("model")
            for m in client.list_models()
            if m is not None
        ]
    except Exception:
        available = []

    candidates: list[str] = []
    for candidate in _OLLAMA_FALLBACK_MODEL_ORDER:
        if candidate and candidate != selected_model and candidate not in candidates:
            candidates.append(candidate)
    for candidate in available:
        if candidate and candidate != selected_model and candidate not in candidates:
            candidates.append(candidate)
    return candidates


def _generate_with_ollama_fallback(prompt: str, timeout: float | None = None) -> str:
    selected_model = _OLLAMA_MODEL
    models_to_try = [selected_model]
    client = _OllamaClient(model=selected_model)
    models_to_try.extend(_select_fallback_ollama_models(client, selected_model))

    def _should_fallback(exc: Exception) -> bool:
        message = str(exc).lower()
        return any(
            phrase in message
            for phrase in [
                "not found",
                "unavailable",
                "no such model",
                "timed out",
                "timeout",
                "cannot reach ollama",
            ]
        )

    last_exc: Exception | None = None
    for model in models_to_try:
        client = _OllamaClient(model=model)
        try:
            return client.generate(prompt, timeout=timeout)
        except Exception as exc:
            last_exc = exc
            if _should_fallback(exc):
                continue
            raise

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Ollama generation failed: no fallback model could produce output.")


app = Flask(__name__, template_folder="templates")

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

  /* ── Artist Links Tab (FR-20260515-artist-links-pill-music-dashboard) ────── */
  .links-section { margin-bottom: 32px; }
  .links-section-header {
    font-size: 11px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.08em; color: var(--text-dim);
    padding: 8px 0; margin-bottom: 12px; border-bottom: 1px solid var(--border);
  }
  .links-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }
  .link-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 16px; transition: border-color 0.15s;
  }
  .link-card:hover { border-color: rgba(225,29,72,0.4); }
  .link-card-header {
    display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;
  }
  .link-card-platform { font-size: 15px; font-weight: 700; }
  .link-card-badges { display: flex; gap: 4px; align-items: center; }
  .pending-badge {
    display: inline-flex; align-items: center; gap: 3px;
    padding: 2px 7px; border-radius: 8px; font-size: 10px; font-weight: 700;
    background: rgba(245,158,11,0.15); color: var(--warning); border: 1px solid rgba(245,158,11,0.3);
  }
  .link-rows { display: flex; flex-direction: column; gap: 6px; }
  .link-row {
    display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 7px 10px;
  }
  .link-row-label {
    font-size: 12px; color: var(--text-muted); flex: 1; min-width: 80px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 120px;
  }
  .link-anchor {
    font-size: 12px; color: var(--accent2); text-decoration: none;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 150px;
    display: inline-block;
  }
  .link-anchor:hover { text-decoration: underline; }
  .link-status-badge {
    padding: 1px 6px; border-radius: 6px; font-size: 9px; font-weight: 700; white-space: nowrap;
  }
  .lsb-confirmed { background: rgba(34,197,94,0.12); color: #86efac; }
  .lsb-pending   { background: rgba(245,158,11,0.12); color: #fbbf24; }
  .lsb-broken    { background: rgba(239,68,68,0.12);  color: #fca5a5; }
  .copy-btn {
    background: transparent; border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 3px 7px; font-size: 10px;
    color: var(--text-dim); cursor: pointer; transition: all 0.15s; white-space: nowrap;
  }
  .copy-btn:hover { border-color: var(--accent); color: var(--accent2); }
  .link-row-actions { display: flex; gap: 4px; }
  .link-action-btn {
    background: transparent; border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 3px 7px; font-size: 11px;
    color: var(--text-dim); cursor: pointer; transition: all 0.15s;
  }
  .link-action-btn:hover { border-color: var(--accent); color: var(--text); }
  .link-action-btn.del:hover { border-color: var(--danger); color: var(--danger); }
  .embed-toggle {
    display: block; width: 100%; background: transparent; border: 1px dashed var(--border);
    border-radius: var(--radius-sm); padding: 6px 12px; font-size: 11px;
    color: var(--text-dim); cursor: pointer; text-align: left; margin-top: 8px; transition: all 0.15s;
  }
  .embed-toggle:hover { border-color: var(--accent); color: var(--text); }
  .embed-container { margin-top: 8px; display: none; }
  .embed-container.open { display: block; }
  .embed-container iframe { max-width: 100%; border-radius: 8px; }
  .links-add-btn {
    display: inline-flex; align-items: center; gap: 6px;
    background: var(--accent); color: white; border: none;
    border-radius: var(--radius-sm); padding: 8px 18px;
    font-size: 13px; font-weight: 600; cursor: pointer; margin-bottom: 20px;
    transition: background 0.15s;
  }
  .links-add-btn:hover { background: #be123c; }
  .link-modal {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 28px; max-width: 520px; width: 90%;
    max-height: 90vh; overflow-y: auto;
  }
  .link-modal h3 { font-size: 16px; margin-bottom: 16px; color: var(--accent2); }
  .form-group { margin-bottom: 14px; }
  .form-group label { display: block; font-size: 12px; color: var(--text-dim); margin-bottom: 5px; }
  .form-input {
    width: 100%; background: var(--surface2); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 8px 12px; font-size: 13px;
    color: var(--text); outline: none; transition: border-color 0.15s; box-sizing: border-box;
  }
  .form-input:focus { border-color: var(--accent); }
  .form-textarea { min-height: 80px; resize: vertical; font-family: inherit; }
  .form-select {
    width: 100%; background: var(--surface2); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 8px 12px; font-size: 13px;
    color: var(--text); outline: none; box-sizing: border-box;
  }
  .form-select:focus { border-color: var(--accent); }
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
  <button class="tab-btn" onclick="switchTab('chord-sheets', this); csLoadSongs()">📄 Chord Sheets</button>
  <a href="/rhymes" class="tab-btn" style="text-decoration:none;">🎼 Rhyme Grouper</a>
  <a href="/links" class="tab-btn" style="text-decoration:none;">🔗 Artist Links</a>
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

<div id="tab-links" class="tab-content">
  <button class="links-add-btn" onclick="openLinkModal()">＋ Add Link</button>
  <div id="linksContainer"></div>
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

<div id="tab-chord-sheets" class="tab-content">
  <div style="max-width:900px;">
    <h3 style="color:var(--accent2);margin-bottom:20px;">📄 Chord Sheets</h3>

    <!-- Section A: parse raw text ─────────────────────────────────────────── -->
    <div style="background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:20px;margin-bottom:24px;">
      <h4 style="color:var(--text);margin-bottom:12px;">A — New Song (Parse → Review → Generate)</h4>
      <div style="margin-bottom:12px;">
        <label style="color:var(--text-muted);font-size:12px;display:block;margin-bottom:6px;">Paste raw chord chart</label>
        <textarea id="cs-raw-text" rows="8" style="width:100%;background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;color:var(--text);font-family:monospace;font-size:13px;resize:vertical;" placeholder="C G Am F&#10;Hello darkness my old friend..."></textarea>
      </div>
      <button class="btn" onclick="csParseText()" style="background:var(--accent);color:white;margin-bottom:16px;">Parse with AI</button>
      <div style="margin-bottom:12px;">
        <label style="color:var(--text-muted);font-size:12px;display:block;margin-bottom:6px;">Review / Edit JSON</label>
        <textarea id="cs-json-review" rows="10" style="width:100%;background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px;color:var(--text);font-family:monospace;font-size:12px;resize:vertical;" placeholder="Parsed JSON will appear here..."></textarea>
      </div>
      <button class="btn" onclick="csGenerateFromJson('A')" style="background:var(--accent2);color:white;">Save &amp; Generate DOCX</button>
    </div>

    <!-- Section B: existing template ──────────────────────────────────────── -->
    <div style="background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:20px;margin-bottom:24px;">
      <h4 style="color:var(--text);margin-bottom:12px;">B — Regenerate from Existing Template</h4>
      <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:12px;">
        <select id="cs-song-select" style="background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 12px;color:var(--text);font-size:13px;flex:1;min-width:200px;">
          <option value="">Loading songs…</option>
        </select>
        <label style="display:flex;align-items:center;gap:8px;color:var(--text-muted);font-size:13px;cursor:pointer;">
          <input type="checkbox" id="cs-lyrics-only" style="width:14px;height:14px;"> Lyrics Only
        </label>
      </div>
      <button class="btn" onclick="csGenerateFromJson('B')" style="background:var(--accent2);color:white;">Generate DOCX</button>
    </div>

    <!-- Result panel ───────────────────────────────────────────────────────── -->
    <div id="cs-result-panel" style="display:none;background:var(--surface);border:1px solid var(--ok);border-radius:var(--radius);padding:20px;">
      <h4 style="color:var(--ok);margin-bottom:12px;">✓ Generated</h4>
      <div style="margin-bottom:8px;color:var(--text-muted);">File: <span id="cs-result-filename" style="color:var(--text);font-family:monospace;"></span></div>
      <div style="margin-bottom:8px;color:var(--text-muted);">Path: <span id="cs-result-path" style="color:var(--text);font-family:monospace;"></span></div>
      <a id="cs-download-link" href="#" target="_blank" class="btn" style="display:inline-block;background:var(--ok);color:white;text-decoration:none;margin-right:10px;">📥 Open DOCX</a>
      <div id="cs-pr-section" style="display:none;margin-top:14px;">
        <div style="margin-bottom:8px;color:var(--text-muted);">PR: <a id="cs-pr-url" href="#" target="_blank" style="color:var(--accent);"></a></div>
        <button class="btn" onclick="csMergePR()" style="background:var(--accent);">🔀 Merge PR</button>
      </div>
    </div>

    <div id="cs-status" style="margin-top:12px;font-size:13px;color:var(--text-muted);"></div>
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

<!-- Link add/edit modal -->
<div class="modal-overlay" id="linkModal">
  <div class="link-modal">
    <h3 id="linkModalTitle">＋ Add Link</h3>
    <div class="form-group">
      <label>Platform *</label>
      <input class="form-input" id="lf_platform" placeholder="e.g. Spotify, Bandcamp">
    </div>
    <div class="form-group">
      <label>Category *</label>
      <select class="form-select" id="lf_category">
        <option value="email">email</option>
        <option value="social">social</option>
        <option value="payment">payment</option>
        <option value="distribution" selected>distribution</option>
      </select>
    </div>
    <div class="form-group">
      <label>Label *</label>
      <input class="form-input" id="lf_label" placeholder="e.g. Artist page, Payment link">
    </div>
    <div class="form-group">
      <label>URL</label>
      <input class="form-input" id="lf_url" placeholder="https://...">
    </div>
    <div class="form-group">
      <label>Embed HTML</label>
      <textarea class="form-input form-textarea" id="lf_embed_html" placeholder="<iframe ...></iframe>"></textarea>
    </div>
    <div class="form-group">
      <label>Song Title (optional)</label>
      <input class="form-input" id="lf_song_title" placeholder="e.g. What I Do">
    </div>
    <div class="form-group">
      <label>Status</label>
      <select class="form-select" id="lf_status">
        <option value="confirmed" selected>confirmed</option>
        <option value="pending">pending</option>
        <option value="broken">broken</option>
      </select>
    </div>
    <div class="modal-actions">
      <button class="btn btn-cancel" onclick="closeLinkModal()">Cancel</button>
      <button class="btn" style="background:var(--accent);color:white;" onclick="saveLinkModal()">Save</button>
    </div>
  </div>
</div>

<!-- Link delete confirmation modal -->
<div class="modal-overlay" id="linkDeleteModal">
  <div class="modal">
    <h3>⚠ Delete Link</h3>
    <p>This will permanently remove the link.</p>
    <div class="track-info" id="deleteLinkInfo"></div>
    <div class="modal-actions">
      <button class="btn btn-cancel" onclick="closeLinkDeleteModal()">Cancel</button>
      <button class="btn btn-danger" onclick="confirmLinkDelete()">Delete forever</button>
    </div>
  </div>
</div>

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
let linksLoaded = false;
let editingLinkId = null;
let pendingDeleteLinkId = null;
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
  if (tab === 'links' && !linksLoaded) loadLinks();
}

// ── Signatures ──
let signatures = [];
let signaturesLoaded = false;
let releaseOpsLoaded = false;

async function loadSignatures() {
  try {
    const res = await fetch('/api/signatures');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    signatures = await res.json();
    signaturesLoaded = true;
    renderSignatures();
  } catch (err) {
    signaturesLoaded = false;
    const sigGrid = document.getElementById('sigGrid');
    if (sigGrid) sigGrid.innerHTML = '<div class="empty-state"><div class="icon">⚠️</div>Failed to load signatures — check server logs</div>';
    console.error('loadSignatures error:', err);
  }
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
    } else {
      hEl.innerHTML = '<div style="color:var(--text-dim);padding:12px;">Nothing played yet</div>';
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
// ── Artist Links ──────────────────────────────────────────────────────────────
let allLinks = [];

async function loadLinks() {
  const res = await fetch('/api/links');
  allLinks = await res.json();
  linksLoaded = true;
  renderLinks();
}

function renderLinks() {
  const container = document.getElementById('linksContainer');
  if (!allLinks.length) {
    container.innerHTML = '<div class="empty-state"><div class="icon">🔗</div>No links yet — add one!</div>';
    return;
  }
  const sections = [
    { title: '📧 Emails',                cats: ['email'] },
    { title: '💳 Social & Payment',      cats: ['social', 'payment'] },
    { title: '🎵 Distribution Platforms', cats: ['distribution'] },
  ];
  let html = '';
  for (const section of sections) {
    const slinks = allLinks.filter(l => section.cats.includes(l.category));
    if (!slinks.length) continue;
    const byPlat = {};
    for (const l of slinks) {
      const p = l.platform || 'Other';
      (byPlat[p] = byPlat[p] || []).push(l);
    }
    html += `<div class="links-section"><div class="links-section-header">${esc(section.title)}</div><div class="links-cards">`;
    for (const [plat, platLinks] of Object.entries(byPlat)) {
      const hasPending = platLinks.some(l => l.status === 'pending');
      const embedLinks = platLinks.filter(l => l.embed_html);
      html += `<div class="link-card">
        <div class="link-card-header">
          <div class="link-card-platform">${esc(plat)}</div>
          <div class="link-card-badges">${hasPending ? '<span class="pending-badge">⚠️ pending</span>' : ''}</div>
        </div>
        <div class="link-rows">`;
      for (const link of platLinks) {
        const sClass = 'lsb-' + link.status;
        const dispText = link.url
          ? (link.url.length > 50 ? link.url.slice(0, 50) + '…' : link.url)
          : '(embed)';
        const copyVal = link.url || link.embed_html || '';
        html += `<div class="link-row">
          <div class="link-row-label" title="${esc(link.label || '')}">${esc(link.label || link.song_title || '—')}</div>
          ${link.url ? `<a class="link-anchor" href="${esc(link.url)}" target="_blank" rel="noopener noreferrer" title="${esc(link.url)}">${esc(dispText)}</a>` : ''}
          <span class="link-status-badge ${sClass}">${esc(link.status)}</span>
          <button class="copy-btn" data-copy="${esc(copyVal)}" onclick="copyLink(this.dataset.copy)">Copy</button>
          <div class="link-row-actions">
            <button class="link-action-btn" onclick="openLinkModal(${link.id})" title="Edit">✏️</button>
            <button class="link-action-btn del" onclick="requestLinkDelete(${link.id})" title="Delete">🗑️</button>
          </div>
        </div>`;
      }
      html += '</div>'; // .link-rows
      if (embedLinks.length) {
        const eid = 'emb_' + plat.replace(/[^a-z0-9]/gi, '_');
        // embed_html is trusted-content-only (artist's own platform iframes).
        // Do not render user-supplied HTML here without sanitization.
        html += `<button class="embed-toggle" onclick="toggleEmbeds('${eid}')">▶ Show embeds (${embedLinks.length})</button>`
             +  `<div class="embed-container" id="${eid}">${embedLinks.map(e => e.embed_html).join('\n')}</div>`;
      }
      html += '</div>'; // .link-card
    }
    html += '</div></div>'; // .links-cards, .links-section
  }
  container.innerHTML = html;
}

function toggleEmbeds(id) {
  const el = document.getElementById(id);
  if (!el) return;
  const open = el.classList.toggle('open');
  const btn = el.previousElementSibling;
  const n = el.querySelectorAll('iframe').length || el.children.length;
  btn.textContent = open ? `▼ Hide embeds (${n})` : `▶ Show embeds (${n})`;
}

function copyLink(text) {
  if (!text) return;
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text)
      .then(() => showToast('Copied!', 'success'))
      .catch(() => _fallbackCopy(text));
  } else {
    _fallbackCopy(text);
  }
}

function _fallbackCopy(text) {
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.select();
  document.execCommand('copy');
  document.body.removeChild(ta);
  showToast('Copied!', 'success');
}

function openLinkModal(id) {
  editingLinkId = id != null ? id : null;
  document.getElementById('linkModalTitle').textContent = id != null ? '✏️ Edit Link' : '＋ Add Link';
  if (id != null) {
    const link = allLinks.find(l => l.id === id);
    if (link) {
      document.getElementById('lf_platform').value   = link.platform   || '';
      document.getElementById('lf_category').value   = link.category   || 'distribution';
      document.getElementById('lf_label').value      = link.label      || '';
      document.getElementById('lf_url').value        = link.url        || '';
      document.getElementById('lf_embed_html').value = link.embed_html || '';
      document.getElementById('lf_song_title').value = link.song_title || '';
      document.getElementById('lf_status').value     = link.status     || 'confirmed';
    }
  } else {
    document.getElementById('lf_platform').value   = '';
    document.getElementById('lf_category').value   = 'distribution';
    document.getElementById('lf_label').value      = '';
    document.getElementById('lf_url').value        = '';
    document.getElementById('lf_embed_html').value = '';
    document.getElementById('lf_song_title').value = '';
    document.getElementById('lf_status').value     = 'confirmed';
  }
  document.getElementById('linkModal').classList.add('show');
}

function closeLinkModal() {
  document.getElementById('linkModal').classList.remove('show');
  editingLinkId = null;
}

async function saveLinkModal() {
  const platform   = document.getElementById('lf_platform').value.trim();
  const category   = document.getElementById('lf_category').value;
  const label      = document.getElementById('lf_label').value.trim();
  const url        = document.getElementById('lf_url').value.trim() || null;
  const embed_html = document.getElementById('lf_embed_html').value.trim() || null;
  const song_title = document.getElementById('lf_song_title').value.trim() || null;
  const status     = document.getElementById('lf_status').value;
  if (!platform || !label) {
    showToast('Platform and label are required', 'error');
    return;
  }
  const body = { platform, category, label, url, embed_html, song_title, status };
  try {
    let res;
    if (editingLinkId != null) {
      res = await fetch(`/api/links/${editingLinkId}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
    } else {
      res = await fetch('/api/links', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
    }
    const data = await res.json();
    if (res.ok) {
      closeLinkModal();
      if (editingLinkId != null) {
        const idx = allLinks.findIndex(l => l.id === editingLinkId);
        if (idx >= 0) allLinks[idx] = data;
        showToast('Link updated', 'success');
      } else {
        allLinks.push(data);
        showToast('Link added', 'success');
      }
      renderLinks();
    } else {
      showToast(data.error || 'Save failed', 'error');
    }
  } catch (_) {
    showToast('Network error', 'error');
  }
}

function requestLinkDelete(id) {
  pendingDeleteLinkId = id;
  const link = allLinks.find(l => l.id === id);
  const info = document.getElementById('deleteLinkInfo');
  info.textContent = '';
  const strong = document.createElement('strong');
  strong.textContent = link ? (link.platform + ' — ' + link.label) : 'Unknown';
  info.appendChild(strong);
  if (link && link.url) {
    info.appendChild(document.createTextNode(' · ' + link.url.slice(0, 60)));
  }
  document.getElementById('linkDeleteModal').classList.add('show');
}

function closeLinkDeleteModal() {
  document.getElementById('linkDeleteModal').classList.remove('show');
  pendingDeleteLinkId = null;
}

async function confirmLinkDelete() {
  if (pendingDeleteLinkId == null) return;
  const id = pendingDeleteLinkId;
  closeLinkDeleteModal();
  try {
    const res = await fetch(`/api/links/${id}`, { method: 'DELETE' });
    const data = await res.json();
    if (data.ok) {
      allLinks = allLinks.filter(l => l.id !== id);
      renderLinks();
      showToast('Link deleted', 'success');
    } else {
      showToast(data.error || 'Delete failed', 'error');
    }
  } catch (_) {
    showToast('Network error', 'error');
  }
}

function setRadioVol(v) { radioAudio.volume = v / 100; }

// ── Chord Sheets Tab ─────────────────────────────────────────────────────────

async function csLoadSongs() {
  try {
    const r = await fetch('/chord-sheet/songs');
    const songs = await r.json();
    const sel = document.getElementById('cs-song-select');
    sel.innerHTML = songs.length
      ? songs.map(s => `<option value="${esc(s)}">${esc(s)}</option>`).join('')
      : '<option value="">No templates found</option>';
  } catch (_) {
    const sel = document.getElementById('cs-song-select');
    if (sel) sel.innerHTML = '<option value="">Error loading songs</option>';
  }
}

async function csParseText() {
  const raw = document.getElementById('cs-raw-text').value.trim();
  if (!raw) { showToast('Paste a chord chart first', 'error'); return; }
  csSetStatus('Parsing with AI\u2026');
  try {
    const r = await fetch('/chord-sheet/parse', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({raw_text: raw})
    });
    const data = await r.json();
    if (!r.ok) { csSetStatus('Error: ' + (data.error || r.status)); return; }
    document.getElementById('cs-json-review').value =
      JSON.stringify(JSON.parse(data.json_string), null, 2);
    csSetStatus('Parsed. Review and edit the JSON, then click Save & Generate DOCX.');
  } catch (e) { csSetStatus('Network error: ' + e.message); }
}

async function csGenerateFromJson(workflow) {
  csSetStatus('Generating\u2026');
  const payload = {workflow};
  if (workflow === 'A') {
    const jsonStr = document.getElementById('cs-json-review').value.trim();
    if (!jsonStr) { showToast('No JSON to generate from', 'error'); return; }
    payload.json_content = jsonStr;
  } else {
    const sel = document.getElementById('cs-song-select');
    if (!sel.value) { showToast('Select a song first', 'error'); return; }
    payload.song_path = sel.value;
    payload.lyrics_only = document.getElementById('cs-lyrics-only').checked;
  }
  try {
    const r = await fetch('/chord-sheet/generate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await r.json();
    if (!r.ok) { csSetStatus('Error: ' + (data.error || r.status)); return; }
    document.getElementById('cs-result-filename').textContent = data.filename || '';
    const filePath = data.file_path || '';
    const pathEl = document.getElementById('cs-result-path');
    if (pathEl) pathEl.textContent = filePath;
    const dl = document.getElementById('cs-download-link');
    dl.href = data.download_url || '#';
    document.getElementById('cs-result-panel').style.display = 'block';
    const prSection = document.getElementById('cs-pr-section');
    if (data.pr_url) {
      _csPrUrl = data.pr_url.trim();
      const prLink = document.getElementById('cs-pr-url');
      prLink.href = _csPrUrl;
      prLink.textContent = _csPrUrl;
      prSection.style.display = 'block';
    } else {
      prSection.style.display = 'none';
    }
    csSetStatus('Done! DOCX generated.');
    csLoadSongs();
  } catch (e) { csSetStatus('Network error: ' + e.message); }
}

let _csPrUrl = '';

async function csMergePR() {
  if (!_csPrUrl) { csSetStatus('No PR to merge.'); return; }
  csSetStatus('Merging PR...');
  try {
    const r = await fetch('/chord-sheet/merge', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({pr_url: _csPrUrl})
    });
    const data = await r.json();
    if (!r.ok) { csSetStatus('Merge error: ' + (data.error || r.status)); return; }
    csSetStatus('PR merged! ✓');
    document.getElementById('cs-pr-section').style.display = 'none';
    _csPrUrl = '';
  } catch (e) { csSetStatus('Network error: ' + e.message); }
}

function csSetStatus(msg) {
  const el = document.getElementById('cs-status');
  if (el) el.textContent = msg;
}
</script>
</body>
</html>
"""


# ── API Routes ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "ready": True})


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
    try:
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
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


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
            count_tracks_sql = "SELECT COUNT(*) FROM tracks WHERE album_id IN (" + placeholders + ")"  # nosec B608
            bloom_track_count = conn.execute(
                count_tracks_sql,
                bloom_album_ids,
            ).fetchone()[0]
            if _table_exists(conn, "release_signatures"):
                count_signatures_sql = (
                    "SELECT COUNT(*) "
                    "FROM release_signatures rs "
                    "JOIN tracks t ON t.id = rs.track_id "
                    "WHERE t.album_id IN (" + placeholders + ")"  # nosec B608
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
        req = urllib.request.urlopen(f"{RADIO_BASE}/api/now_playing", timeout=2)  # nosec B310
        data = json.loads(req.read())
        return jsonify(data)
    except (urllib.error.URLError, OSError):
        return jsonify({"error": "Radio offline", "title": "Offline", "listeners": 0})


@app.route("/api/radio/playlist")
def api_radio_playlist():
    try:
        req = urllib.request.urlopen(f"{RADIO_BASE}/api/playlist", timeout=2)  # nosec B310
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
        update_sql = "UPDATE tracks SET " + set_clause + " WHERE id = ?"  # nosec B608
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


# ── Artist Links API (FR-20260515-artist-links-pill-music-dashboard) ──────────

_LINK_ALLOWED_CATEGORIES: frozenset[str] = frozenset({"email", "social", "payment", "distribution"})
_LINK_ALLOWED_STATUSES: frozenset[str] = frozenset({"confirmed", "pending", "broken"})
# Explicit allowlist for DB column names used in dynamic SET clauses (B608 guard).
_LINK_ALLOWED_COLUMNS: frozenset[str] = frozenset({
    "category", "status", "platform", "label",
    "url", "embed_html", "song_title", "sort_order",
})


def _validate_link_payload(data: dict) -> tuple[dict, str | None]:
    """Return (cleaned_fields, error_str).  error_str is None on success."""
    out: dict = {}
    if "category" in data:
        if data["category"] not in _LINK_ALLOWED_CATEGORIES:
            return {}, f"Invalid category: {data['category']!r}"
        out["category"] = data["category"]
    if "status" in data:
        if data["status"] not in _LINK_ALLOWED_STATUSES:
            return {}, f"Invalid status: {data['status']!r}"
        out["status"] = data["status"]
    for field in ("platform", "label"):
        if field in data:
            val = str(data[field]).strip() if data[field] else ""
            if not val:
                return {}, f"'{field}' cannot be empty"
            out[field] = val
    for field in ("url", "embed_html", "song_title"):
        if field in data:
            # NOTE: embed_html is TRUSTED-CONTENT-ONLY — it is injected directly via
            # innerHTML in the browser to render <iframe> embeds from music platforms.
            # Never expose this CRUD endpoint to untrusted/multi-user traffic without
            # adding server-side HTML sanitization (e.g. bleach) first.
            out[field] = str(data[field]).strip() if data[field] else None
    if "sort_order" in data:
        try:
            out["sort_order"] = int(data["sort_order"])
        except (ValueError, TypeError):
            return {}, "sort_order must be an integer"
    return out, None


@app.route("/api/links")
def api_links_get():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM artist_links ORDER BY category, platform, sort_order, id"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/links", methods=["POST"])
def api_links_post():
    data = request.get_json(silent=True) or {}
    for field in ("category", "platform", "label"):
        if not data.get(field):
            return jsonify({"error": f"'{field}' is required"}), 400
    cleaned, err = _validate_link_payload(data)
    if err:
        return jsonify({"error": err}), 400
    # Ensure required fields are in cleaned (they pass validation above)
    for field in ("category", "platform", "label"):
        if field not in cleaned:
            cleaned[field] = str(data[field]).strip()
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO artist_links
               (category, platform, label, url, embed_html, song_title, status, sort_order)
               VALUES (:category, :platform, :label, :url, :embed_html, :song_title, :status, :sort_order)""",
            {
                "category":   cleaned["category"],
                "platform":   cleaned["platform"],
                "label":      cleaned["label"],
                "url":        cleaned.get("url"),
                "embed_html": cleaned.get("embed_html"),
                "song_title": cleaned.get("song_title"),
                "status":     cleaned.get("status", "confirmed"),
                "sort_order": cleaned.get("sort_order", 0),
            },
        )
        conn.commit()
        row = conn.execute("SELECT * FROM artist_links WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@app.route("/api/links/<int:link_id>", methods=["PUT"])
def api_links_put(link_id: int):
    data = request.get_json(silent=True) or {}
    cleaned, err = _validate_link_payload(data)
    if err:
        return jsonify({"error": err}), 400
    if not cleaned:
        return jsonify({"error": "No valid fields to update"}), 400
    with get_connection() as conn:
        if not conn.execute("SELECT id FROM artist_links WHERE id = ?", (link_id,)).fetchone():
            return jsonify({"error": "Link not found"}), 404
        safe_cleaned = {k: v for k, v in cleaned.items() if k in _LINK_ALLOWED_COLUMNS}
        set_parts = [f"{k} = ?" for k in safe_cleaned] + ["updated_at = datetime('now')"]
        conn.execute(
            f"UPDATE artist_links SET {', '.join(set_parts)} WHERE id = ?",  # nosec B608
            list(safe_cleaned.values()) + [link_id],
        )
        conn.commit()
        row = conn.execute("SELECT * FROM artist_links WHERE id = ?", (link_id,)).fetchone()
    return jsonify(dict(row))


@app.route("/api/links/<int:link_id>", methods=["DELETE"])
def api_links_delete(link_id: int):
    with get_connection() as conn:
        if not conn.execute("SELECT id FROM artist_links WHERE id = ?", (link_id,)).fetchone():
            return jsonify({"error": "Link not found"}), 404
        conn.execute("DELETE FROM artist_links WHERE id = ?", (link_id,))
        conn.commit()
    return jsonify({"ok": True})


# ── Rhyme Grouper helpers ──────────────────────────────────────────────────────

_VAULT_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS vault_lines (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    line       TEXT NOT NULL UNIQUE,
    is_hook    INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS phonetic_groups (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    suffixes TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vault_line_groups (
    line_id  INTEGER REFERENCES vault_lines(id) ON DELETE CASCADE,
    group_id INTEGER REFERENCES phonetic_groups(id) ON DELETE CASCADE,
    PRIMARY KEY (line_id, group_id)
);
"""


def _ensure_vault_schema() -> None:
    """Create vault tables if they don't already exist."""
    with get_connection() as conn:
        conn.executescript(_VAULT_SCHEMA)
        existing = [row[1] for row in conn.execute("PRAGMA table_info(vault_lines)").fetchall()]
        if "is_hook" not in existing:
            conn.execute("ALTER TABLE vault_lines ADD COLUMN is_hook INTEGER NOT NULL DEFAULT 0")
        conn.commit()


def _load_phonetics() -> tuple[list[list[str]], dict[str, int]]:
    """Load all phonetic groups from DB and build the suffix map.

    Returns:
        Tuple of (phonetics list, suffix_map dict).
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, suffixes FROM phonetic_groups ORDER BY id"
        ).fetchall()

    phonetics: list[list[str]] = []
    group_db_ids: list[int] = []
    for row_id, sfx_json in rows:
        try:
            slist = json.loads(sfx_json)
        except (json.JSONDecodeError, TypeError):
            slist = []
        phonetics.append(slist)
        group_db_ids.append(row_id)

    suffix_map = build_suffix_map(phonetics)
    # Remap: suffix → DB row id (not list index)
    db_suffix_map: dict[str, int] = {}
    for idx, slist in enumerate(phonetics):
        for s in slist:
            if isinstance(s, str) and s.strip():
                db_suffix_map[s.strip().lower()] = group_db_ids[idx]

    return phonetics, db_suffix_map


def _match_line_to_db_groups(
    line: str, db_suffix_map: dict[str, int]
) -> list[int]:
    """Return DB group IDs that match the last word of a lyric line."""
    word = last_word(line)
    if not word:
        return []
    # Try suffix lengths 2–9
    for length in range(2, min(len(word) + 1, 10)):
        sfx = word[-length:]
        if sfx in db_suffix_map:
            return [db_suffix_map[sfx]]
    # Try singular form
    if word.endswith("s") and len(word) > 1:
        singular = word[:-1]
        for length in range(2, min(len(singular) + 1, 10)):
            sfx = singular[-length:]
            if sfx in db_suffix_map:
                return [db_suffix_map[sfx]]
    return []


def _get_vault_stats() -> dict:
    """Return counts for stats pills."""
    with get_connection() as conn:
        total_lines = (
            conn.execute("SELECT COUNT(*) FROM vault_lines").fetchone()[0]
        )
        total_groups = (
            conn.execute("SELECT COUNT(*) FROM phonetic_groups").fetchone()[0]
        )
        matched_lines = conn.execute(
            "SELECT COUNT(DISTINCT line_id) FROM vault_line_groups"
        ).fetchone()[0]
        hook_lines = conn.execute(
            "SELECT COUNT(*) FROM vault_lines WHERE is_hook = 1"
        ).fetchone()[0]
    return {
        "total_lines": total_lines,
        "total_groups": total_groups,
        "matched_lines": matched_lines,
        "ungrouped_lines": total_lines - matched_lines,
        "hook_lines": hook_lines,
    }


def _parse_ollama_candidates(raw: str, valid_lines: set[str]) -> list[str]:
    """Extract exact hook-worthy lines from Ollama output."""
    candidates: list[str] = []
    for line in raw.splitlines():
        text = line.strip()
        if not text:
            continue
        text = re.sub(r'^\s*[\d]+[\).:-]*\s*', '', text)
        if text.startswith(('•', '-', '*')):
            text = text[1:].strip()
        if text in valid_lines and text not in candidates:
            candidates.append(text)
    return candidates


# ── Rhyme Grouper routes ───────────────────────────────────────────────────────

@app.route("/rhymes")
def rhymes_page():
    """Render the Rhyme Grouper main page."""
    _ensure_vault_schema()
    _, db_suffix_map = _load_phonetics()

    with get_connection() as conn:
        group_rows = conn.execute(
            "SELECT id, suffixes FROM phonetic_groups ORDER BY id"
        ).fetchall()

        line_rows = conn.execute(
            "SELECT id, line, is_hook FROM vault_lines ORDER BY line COLLATE NOCASE"
        ).fetchall()

        join_rows = conn.execute(
            "SELECT line_id, group_id FROM vault_line_groups"
        ).fetchall()

    # Build group_id → line list mapping
    line_by_id = {r[0]: {"id": r[0], "line": r[1], "is_hook": bool(r[2])} for r in line_rows}
    group_lines: dict[int, list[dict]] = {}
    grouped_line_ids: set[int] = set()
    for line_id, group_id in join_rows:
        group_lines.setdefault(group_id, []).append(line_by_id[line_id])
        grouped_line_ids.add(line_id)

    groups = []
    for group_id, sfx_json in group_rows:
        try:
            suffixes = json.loads(sfx_json)
        except (json.JSONDecodeError, TypeError):
            suffixes = []
        lines_in_group = group_lines.get(group_id, [])
        if lines_in_group:
            groups.append({
                "id": group_id,
                "suffixes": suffixes,
                "lines": lines_in_group,
            })

    ungrouped = [
        line_by_id[lid] for lid in sorted(line_by_id)
        if lid not in grouped_line_ids
    ]

    stats = _get_vault_stats()
    return render_template(
        "rhymes.html",
        groups=groups,
        ungrouped=ungrouped,
        stats=stats,
    )


@app.route("/links")
def links_page():
    """Serve the generated Artist Links panel (clean accordion by platform)."""
    from datetime import datetime, timezone
    from artist_links.generate_artist_links_panel import build_sections, render_html, LINKS_JSON
    import json as _json
    data = _json.loads(LINKS_JSON.read_text(encoding="utf-8"))
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sections = build_sections(data)
    return render_html(sections, generated_at), 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/rhymes/lines", methods=["POST"])
def rhymes_add_line():
    """Add a new lyric line and run phonetic matching."""
    _ensure_vault_schema()
    data = request.get_json(silent=True) or {}
    line = (data.get("line") or "").strip()
    if not line:
        return jsonify({"error": "line is required"}), 400

    is_hook = int(bool(data.get("is_hook")))
    _, db_suffix_map = _load_phonetics()
    group_ids = _match_line_to_db_groups(line, db_suffix_map)

    with get_connection() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO vault_lines (line, is_hook) VALUES (?, ?)",
                (line, is_hook),
            )
            line_id = cur.lastrowid
        except Exception:
            existing = conn.execute(
                "SELECT id FROM vault_lines WHERE line = ?", (line,)
            ).fetchone()
            if existing:
                return jsonify({"error": "Line already exists"}), 409
            raise

        for gid in group_ids:
            conn.execute(
                "INSERT OR IGNORE INTO vault_line_groups (line_id, group_id) VALUES (?, ?)",
                (line_id, gid),
            )
        conn.commit()

    return jsonify({
        "id": line_id,
        "line": line,
        "groups": group_ids,
        "is_hook": bool(is_hook),
    }), 201


@app.route("/rhymes/lines/<int:line_id>", methods=["PUT"])
def rhymes_edit_line(line_id: int):
    """Update a lyric line and re-run phonetic matching."""
    _ensure_vault_schema()
    data = request.get_json(silent=True) or {}
    new_line = (data.get("line") or "").strip()
    is_hook = data.get("is_hook")
    is_hook_value = None if is_hook is None else int(bool(is_hook))

    _, db_suffix_map = _load_phonetics()

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id, line, is_hook FROM vault_lines WHERE id = ?", (line_id,)
        ).fetchone()
        if not existing:
            return jsonify({"error": "Line not found"}), 404
        current_line = existing[1]
        current_hook = bool(existing[2])

        if new_line:
            conn.execute(
                "UPDATE vault_lines SET line = ? WHERE id = ?", (new_line, line_id)
            )
            conn.execute(
                "DELETE FROM vault_line_groups WHERE line_id = ?", (line_id,)
            )
            new_groups = _match_line_to_db_groups(new_line, db_suffix_map)
            for gid in new_groups:
                conn.execute(
                    "INSERT OR IGNORE INTO vault_line_groups (line_id, group_id) VALUES (?, ?)",
                    (line_id, gid),
                )
        else:
            new_groups = [r[0] for r in conn.execute(
                "SELECT group_id FROM vault_line_groups WHERE line_id = ?", (line_id,)
            ).fetchall()]

        if is_hook_value is not None and is_hook_value != current_hook:
            conn.execute(
                "UPDATE vault_lines SET is_hook = ? WHERE id = ?",
                (is_hook_value, line_id),
            )
        conn.commit()

    response_line = new_line or current_line
    response_hook = bool(is_hook_value) if is_hook_value is not None else current_hook
    return jsonify({
        "id": line_id,
        "line": response_line,
        "groups": new_groups,
        "is_hook": response_hook,
    })


@app.route("/rhymes/lines/<int:line_id>", methods=["DELETE"])
def rhymes_delete_line(line_id: int):
    """Delete a lyric line (cascades to vault_line_groups)."""
    _ensure_vault_schema()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM vault_lines WHERE id = ?", (line_id,)
        ).fetchone()
        if not existing:
            return jsonify({"error": "Line not found"}), 404

        conn.execute("DELETE FROM vault_line_groups WHERE line_id = ?", (line_id,))
        conn.execute("DELETE FROM vault_lines WHERE id = ?", (line_id,))
        conn.commit()

    return jsonify({"ok": True, "deleted_id": line_id})


@app.route("/rhymes/suggest")
def rhymes_suggest():
    """Suggest rhyming lines for a given query line.

    Query params:
        q: The lyric line to find rhymes for.
        fallback: Set to 'ollama' to force Ollama fallback.
    """
    _ensure_vault_schema()
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"error": "q parameter is required"}), 400

    use_ollama = request.args.get("fallback") == "ollama"
    word = last_word(q)
    _, db_suffix_map = _load_phonetics()
    group_ids = _match_line_to_db_groups(q, db_suffix_map)

    suggestions: list[str] = []
    source = "phonetics"

    if group_ids and not use_ollama:
        placeholders = ",".join("?" * len(group_ids))
        with get_connection() as conn:
            rows = conn.execute(
                f"SELECT DISTINCT vl.line FROM vault_lines vl "  # nosec B608
                f"JOIN vault_line_groups vlg ON vl.id = vlg.line_id "  # nosec B608
                f"WHERE vlg.group_id IN ({placeholders}) "  # nosec B608
                f"AND vl.line != ? LIMIT 20",  # nosec B608
                group_ids + [q],
            ).fetchall()
        suggestions = [r[0] for r in rows]

    if (not suggestions or use_ollama) and _OLLAMA_AVAILABLE:
        source = "ollama"
        try:
            prompt = (
                f"List 5 lyric lines from a songwriter's vault that rhyme with: "
                f"'{word}'. Return only the lines, one per line."
            )
            raw = _generate_with_ollama_fallback(prompt)
            suggestions = [
                ln.strip().lstrip("0123456789.-) ")
                for ln in raw.strip().splitlines()
                if ln.strip()
            ][:5]
        except Exception as exc:
            source = "ollama_error"
            suggestions = [f"Ollama unavailable: {exc}"]
    elif not suggestions and not _OLLAMA_AVAILABLE:
        source = "none"

    return jsonify({"suggestions": suggestions, "source": source})


@app.route("/rhymes/hook-candidates", methods=["POST"])
def rhymes_hook_candidates():
    """Use Ollama to mark unhooked vault lines as hook-worthy."""
    _ensure_vault_schema()
    if not _OLLAMA_AVAILABLE:
        return jsonify({"error": "Ollama not available"}), 503

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, line FROM vault_lines WHERE is_hook = 0 ORDER BY line COLLATE NOCASE"
        ).fetchall()

    if not rows:
        return jsonify({
            "marked_ids": [],
            "marked_lines": [],
            "source": "none",
            "message": "No unhooked lines available to score.",
        })

    lines = [row[1] for row in rows]
    valid_lines = set(lines)
    if len(lines) > _OLLAMA_HOOK_LINE_LIMIT:
        lines = lines[:_OLLAMA_HOOK_LINE_LIMIT]
        valid_lines = set(lines)
        prompt_intro = (
            f"You are a songwriting assistant. Here are the first {_OLLAMA_HOOK_LINE_LIMIT} unhooked lyric lines from a songwriter's vault:\n"
        )
    else:
        prompt_intro = (
            "You are a songwriting assistant. Here are lyric lines from a songwriter's vault:\n"
        )

    prompt = (
        prompt_intro
        + "\n".join(f"{index + 1}. {line}" for index, line in enumerate(lines))
        + "\n\nIdentify only the lines that would make the strongest chorus hook. "
        + "Return only the exact lines as they appear above, one per line, without explanation."
    )

    try:
        raw = _generate_with_ollama_fallback(prompt, timeout=90.0)
        candidates = _parse_ollama_candidates(str(raw), valid_lines)
    except Exception as exc:
        return jsonify({"error": f"Ollama error: {exc}"}), 503

    marked_ids: list[int] = []
    line_to_ids: dict[str, list[int]] = {}
    for row_id, line in rows:
        line_to_ids.setdefault(line, []).append(row_id)

    for candidate in candidates:
        marked_ids.extend(line_to_ids.get(candidate, []))

    marked_ids = list(dict.fromkeys(marked_ids))
    if marked_ids:
        with get_connection() as conn:
            conn.executemany(
                "UPDATE vault_lines SET is_hook = 1 WHERE id = ?",
                [(line_id,) for line_id in marked_ids],
            )
            conn.commit()

    return jsonify({
        "marked_ids": marked_ids,
        "marked_lines": candidates,
        "source": "ollama",
        "message": f"Marked {len(marked_ids)} hook-worthy line(s).",
    })


@app.route("/rhymes/regroup", methods=["POST"])
def rhymes_regroup():
    """Clear and re-run full phonetic grouping for all vault lines."""
    _ensure_vault_schema()
    _, db_suffix_map = _load_phonetics()

    with get_connection() as conn:
        conn.execute("DELETE FROM vault_line_groups")
        lines = conn.execute("SELECT id, line FROM vault_lines").fetchall()
        groups_updated = 0
        for line_id, line in lines:
            group_ids = _match_line_to_db_groups(line, db_suffix_map)
            for gid in group_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO vault_line_groups (line_id, group_id) VALUES (?, ?)",
                    (line_id, gid),
                )
                groups_updated += 1
        conn.commit()

    return jsonify({"groups_updated": groups_updated})


@app.route("/rhymes/stats")
def rhymes_stats():
    """Return vault statistics as JSON."""
    _ensure_vault_schema()
    return jsonify(_get_vault_stats())


# ── Chord Sheet Routes ────────────────────────────────────────────────────────

@app.route("/chord-sheet/songs")
def chord_sheet_songs():
    """Return sorted list of .json filenames from studio_master/song_templates/."""
    templates = sorted(p.name for p in _CHORD_SHEET_TEMPLATES_DIR.glob("*.json"))
    return jsonify(templates)


@app.route("/chord-sheet/parse", methods=["POST"])
def chord_sheet_parse():
    """Parse raw chord chart text via Ollama → return JSON string."""
    if not _OLLAMA_AVAILABLE:
        return jsonify({"error": "Ollama not available"}), 503

    data = request.get_json(silent=True) or {}
    raw_text = str(data.get("raw_text", "")).strip()
    if not raw_text:
        return jsonify({"error": "raw_text is required"}), 400

    # Build schema example from an existing template
    schema_example = ""
    try:
        sample = next(_CHORD_SHEET_TEMPLATES_DIR.glob("*.json"))
        schema_example = sample.read_text(encoding="utf-8")
    except StopIteration:
        pass

    prompt = (
        "You are a music data parser. Convert the following chord chart to JSON.\n"
        "Return ONLY valid JSON matching this schema example:\n"
        f"{schema_example}\n\n"
        "The JSON must have these fields: title, artist, key, bpm, sections "
        "(array of section objects with name and lines). "
        "Each line is either a string or an object with chords and lyrics keys.\n\n"
        f"Raw chord chart:\n{raw_text}\n\n"
        "Return ONLY the JSON object, no explanation, no code block markers."
    )

    try:
        llm_response = _generate_with_ollama_fallback(prompt)
    except Exception as exc:
        return jsonify({"error": f"Ollama error: {exc}"}), 503

    try:
        parsed = json.loads(llm_response)
        return jsonify({"json_string": json.dumps(parsed, ensure_ascii=False)})
    except (json.JSONDecodeError, ValueError):
        return jsonify({"error": "LLM parse failed", "raw": llm_response}), 422


@app.route("/chord-sheet/save-json", methods=["POST"])
def chord_sheet_save_json():
    """Write reviewed JSON to disk in studio_master/song_templates/."""
    data = request.get_json(silent=True) or {}
    json_content = data.get("json_content", "")
    try:
        song = json.loads(json_content)
    except (json.JSONDecodeError, ValueError):
        return jsonify({"error": "Invalid JSON content"}), 400

    title = _cs_sanitize(song.get("title", "Untitled"))
    artist = _cs_sanitize(song.get("artist", "Unknown"))
    key = _cs_sanitize(song.get("key", "?"))
    filename = f"{title}_{artist}_Key_{key}.json"
    _CHORD_SHEET_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _CHORD_SHEET_TEMPLATES_DIR / filename
    out_path.write_text(json.dumps(song, indent=2, ensure_ascii=False), encoding="utf-8")
    return jsonify({"path": str(out_path), "filename": filename})


@app.route("/chord-sheet/generate", methods=["POST"])
def chord_sheet_generate():
    """Generate DOCX from template or new JSON. Returns download URL."""
    if not _CHORD_SHEET_AVAILABLE:
        details = str(_CHORD_SHEET_IMPORT_ERROR) if '_CHORD_SHEET_IMPORT_ERROR' in globals() else None
        payload = {"error": "make_chord_sheet not available"}
        if details:
            payload["details"] = details
        return jsonify(payload), 503

    data = request.get_json(silent=True) or {}
    workflow = data.get("workflow", "B")
    lyrics_only = bool(data.get("lyrics_only", False))

    if workflow == "A":
        json_content = data.get("json_content", "")
        try:
            song = json.loads(json_content)
        except (json.JSONDecodeError, ValueError):
            return jsonify({"error": "Invalid JSON content"}), 400

        title_s = _cs_sanitize(song.get("title", "Untitled"))
        artist_s = _cs_sanitize(song.get("artist", "Unknown"))
        key_s = _cs_sanitize(song.get("key", "?"))
        json_filename = f"{title_s}_{artist_s}_Key_{key_s}.json"
        _CHORD_SHEET_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
        json_path = _CHORD_SHEET_TEMPLATES_DIR / json_filename
        json_path.write_text(json.dumps(song, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        song_filename = Path(str(data.get("song_path", "")).strip()).name
        if not song_filename:
            return jsonify({"error": "song_path is required for workflow B"}), 400
        json_path = _CHORD_SHEET_TEMPLATES_DIR / song_filename
        if not json_path.exists():
            return jsonify({"error": f"JSON file not found: {song_filename}"}), 404
        with json_path.open(encoding="utf-8") as fh:
            song = json.load(fh)

    # Generate DOCX
    try:
        _CHORD_SHEET_DOCS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = compute_output_path(song, _CHORD_SHEET_DOCS_DIR, lyrics_only=lyrics_only)
        build_docx(song, out_path)
    except Exception as exc:
        return jsonify({"error": f"DOCX generation failed: {exc}"}), 500

    # Git commit + push + open PR (best-effort; failures don't block DOCX download)
    pr_url = ""
    try:
        repo_root = _CS_ROOT
        subprocess.run(
            ["git", "add", str(json_path), str(out_path)],
            cwd=str(repo_root), check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m",
             f"chord-sheet: add {out_path.name}"],
            cwd=str(repo_root), check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "push"],
            cwd=str(repo_root), check=True, capture_output=True,
        )
        gh = subprocess.run(
            ["gh", "pr", "create", "--fill", "--base", "main"],
            cwd=str(repo_root), capture_output=True, text=True,
        )
        pr_url = gh.stdout.strip()
    except Exception:
        pass  # PR creation is optional; DOCX is already generated

    return jsonify({
        "filename": out_path.name,
        "file_path": str(out_path),
        "json_path": str(json_path),
        "download_url": f"/chord-sheet/download/{out_path.name}",
        "pr_url": pr_url,
    })


@app.route("/chord-sheet/merge", methods=["POST"])
def chord_sheet_merge():
    """Merge a chord-sheet PR via `gh pr merge`."""
    data = request.get_json(silent=True) or {}
    pr_url = str(data.get("pr_url", "")).strip()
    if not pr_url:
        return jsonify({"error": "pr_url is required"}), 400
    try:
        result = subprocess.run(
            ["gh", "pr", "merge", pr_url, "--merge", "--auto"],
            cwd=str(_CS_ROOT), capture_output=True, text=True,
        )
        if result.returncode != 0:
            return jsonify({"error": result.stderr.strip() or "gh pr merge failed"}), 500
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"merged": True, "pr_url": pr_url})


@app.route("/chord-sheet/download/<path:filename>")
def chord_sheet_download(filename: str):
    """Serve a generated chord sheet DOCX for download."""
    safe_name = Path(filename).name
    file_path = _CHORD_SHEET_DOCS_DIR / safe_name
    if not file_path.exists():
        return jsonify({"error": "File not found"}), 404
    return send_file(file_path, as_attachment=True, download_name=safe_name)


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
