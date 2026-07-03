"""Output-path resolution, run logging, and validation reporting for the
❤music-chord-sheets agentic workflow (FR-20260703-music-agentic-chord-sheets).

Used by the ❤music-chord-sheets skill (`.github/skills/❤music-chord-sheets/`) to
decide where a generated chord-sheet .docx / JSON template / process log should
land, and to render a source-vs-generated accuracy report for Playwright review.

Output convention:
  - Covers    -> catalog/sheet_music/covers/{Artist} - {Title} (variant).docx
  - Originals -> catalog/sheet_music/originals/{Artist} - {Title} (variant).docx
  - Templates -> studio_master/song_templates/{Artist} - {Title}.json
  - Run logs  -> catalog/sheet_music/_process_logs/chord_sheets_runs.jsonl
"""
from __future__ import annotations

import html
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_TYLER_NAMES = {"tyler james drake", "tyler drake", "tyler"}


def is_tyler_original(artist: str) -> bool:
    """Return True when `artist` refers to Tyler James Drake (an original)."""
    return (artist or "").strip().lower() in _TYLER_NAMES


def _sanitize_filename(name: str) -> str:
    keep = " _-.()[]{}+"
    return "".join(c for c in name if c.isalnum() or c in keep).strip()


def canonical_docx_name(title: str, artist: str, variant: str = "", ext: str = ".docx") -> str:
    """Build the canonical `Artist - Title (variant).ext` filename.

    Matches the naming convention already used in `tools/ingest_sheet_music.py`.
    """
    title = _sanitize_filename(title or "Untitled")
    artist = _sanitize_filename(artist or "")
    variant = _sanitize_filename(variant or "")
    base = f"{artist} - {title}" if artist else title
    if variant:
        base = f"{base} ({variant})"
    return f"{base}{ext}"


@dataclass
class ChordSheetPaths:
    is_original: bool
    sheet_music_path: Path
    template_path: Path
    log_path: Path


def resolve_chord_sheet_paths(
    title: str,
    artist: str,
    project_root: Path,
    variant: str = "",
) -> ChordSheetPaths:
    """Resolve all output paths for one processed song.

    `project_root` is the ❤Music repository root (contains catalog/, studio_master/).
    """
    project_root = Path(project_root)
    original = is_tyler_original(artist)
    docx_name = canonical_docx_name(title, artist, variant=variant, ext=".docx")
    template_name = canonical_docx_name(title, artist, ext=".json")

    sheet_music_dir = project_root / "catalog" / "sheet_music" / ("originals" if original else "covers")
    template_path = project_root / "studio_master" / "song_templates" / template_name
    log_path = project_root / "catalog" / "sheet_music" / "_process_logs" / "chord_sheets_runs.jsonl"

    return ChordSheetPaths(
        is_original=original,
        sheet_music_path=sheet_music_dir / docx_name,
        template_path=template_path,
        log_path=log_path,
    )


def log_chord_sheet_run(log_path: Path, entry: dict) -> Path:
    """Append a JSONL entry (with a `logged_at` UTC timestamp) to `log_path`."""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = dict(entry)
    record.setdefault("logged_at", datetime.now(timezone.utc).isoformat())
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return log_path


def render_validation_html(
    title: str,
    artist: str,
    source_lines: list[str],
    generated_lines: list[str],
    out_path: Path,
) -> Path:
    """Render a side-by-side source-vs-generated accuracy report as HTML.

    Each aligned line pair is marked `ok` (exact match) or `mismatch`. Used as
    the Playwright-inspected validation artifact before presenting a generated
    chord sheet to Tyler for review.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    max_len = max(len(source_lines), len(generated_lines))
    rows = []
    mismatch_count = 0
    for i in range(max_len):
        src = source_lines[i] if i < len(source_lines) else ""
        gen = generated_lines[i] if i < len(generated_lines) else ""
        status = "ok" if src == gen else "mismatch"
        if status == "mismatch":
            mismatch_count += 1
        rows.append(
            f'<div class="diff-row {status}">'
            f'<span class="src">{html.escape(src)}</span>'
            f'<span class="gen">{html.escape(gen)}</span>'
            f"</div>"
        )

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Chord Sheet Validation — {html.escape(title)}</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, sans-serif; background:#0d0f14; color:#e2e8f0; padding:24px; }}
  h1 {{ font-size:18px; }}
  .summary {{ margin-bottom:16px; color:#94a3b8; }}
  .diff-row {{ display:flex; gap:16px; padding:4px 8px; border-bottom:1px solid #252a3a; font-family:monospace; font-size:13px; }}
  .diff-row .src, .diff-row .gen {{ flex:1; white-space:pre-wrap; }}
  .diff-row.ok {{ color:#86efac; }}
  .diff-row.mismatch {{ background:#2e0808; color:#fca5a5; }}
</style>
</head>
<body>
  <h1>Chord Sheet Validation — {html.escape(title)} ({html.escape(artist)})</h1>
  <div class="summary">{len(rows) - mismatch_count} / {len(rows)} lines match · {mismatch_count} mismatch(es)</div>
  <div class="diff-header diff-row"><span class="src"><strong>Source</strong></span><span class="gen"><strong>Generated</strong></span></div>
  {''.join(rows)}
</body>
</html>
"""
    out_path.write_text(doc, encoding="utf-8")
    return out_path
