"""auto_tagger.py — BPM / Key auto-tagger CLI.

Usage::

    C:\\G\\python.exe tools\\auto_tagger.py --smoke-test N
    C:\\G\\python.exe tools\\auto_tagger.py --apply [--skip-masters]
    C:\\G\\python.exe tools\\auto_tagger.py --dry-run

Flags::

    --smoke-test N   Sample N files randomly. Run integrity check on each.
                     Print a tabular report. NO DB or ID3 writes.
                     Exit 0 if all pass, 1 if any fail.
    --dry-run        Scan all sources, detect BPM/key, print what would change.
                     No DB writes, no ID3 writes.
    --apply          Full run: detect + write DB + write ID3 tags.
    --skip-masters   With --apply: skip ID3 write-back for f:\\Masters files only.
                     DB is still updated for those files.

FR-20260526-bpm-key-auto-tagger
"""

from __future__ import annotations

import argparse
import html
import random
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure src/ is importable regardless of working directory.
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from services.audio_tagger import AUDIO_EXTENSIONS, check_integrity, detect  # noqa: E402
from utils.init_db import get_connection  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_AUDIO_ROOTS = [
    Path(r"G:\Muzic"),
    Path(r"f:\Masters"),
    Path(r"f:\recordings"),
]
_MASTERS_ROOT = Path(r"f:\Masters").resolve()
_REPORT_DIR = _ROOT / "reports"


# ---------------------------------------------------------------------------
# Source collection
# ---------------------------------------------------------------------------


def _iter_audio(root: Path):
    """Yield all audio files under *root* recursively."""
    if not root.exists():
        return
    for p in root.rglob("*"):
        if p.suffix.lower() in AUDIO_EXTENSIONS and p.is_file():
            yield p


def collect_sources() -> list[Path]:
    """Return a deduplicated, sorted list of audio file paths from all sources."""
    seen: set[Path] = set()
    result: list[Path] = []

    def _add(path_str: str | None) -> None:
        if not path_str:
            return
        p = Path(path_str).resolve()
        if p not in seen and p.suffix.lower() in AUDIO_EXTENSIONS:
            seen.add(p)
            result.append(p)

    # Static filesystem roots.
    for root in _AUDIO_ROOTS:
        for p in _iter_audio(root):
            _add(str(p))

    # DB-linked paths.
    try:
        with get_connection() as conn:
            for row in conn.execute(
                "SELECT file_path FROM recordings WHERE file_path IS NOT NULL"
            ):
                _add(row[0])
            for row in conn.execute(
                "SELECT source_file FROM catalog_songs WHERE source_file IS NOT NULL"
            ):
                _add(row[0])
    except Exception as exc:
        print(f"  [warn] Could not read DB-linked paths: {exc}", file=sys.stderr)

    return sorted(result, key=lambda p: p.name.lower())


# ---------------------------------------------------------------------------
# DB write helpers (importable for tests)
# ---------------------------------------------------------------------------


def _write_catalog_songs(
    scan_results: list[dict], conn, dry_run: bool = False
) -> dict:
    """Update catalog_songs rows from *scan_results*.

    Skips rows where ``bpm_source = 'manual'``.
    Marks ``row["db_updated"] = True`` for each row written.

    Returns:
        ``{"updated": int, "skipped_manual": int}``
    """
    updated = 0
    skipped = 0
    if dry_run:
        return {"updated": 0, "skipped_manual": 0}

    for row in scan_results:
        path_str = str(row["path"])
        bpm = row.get("bpm")
        key = row.get("key")
        if bpm is None and key is None:
            continue
        try:
            cur = conn.execute(
                "SELECT id, bpm_source FROM catalog_songs WHERE source_file = ?",
                (path_str,),
            )
            db_row = cur.fetchone()
            if db_row is None:
                continue
            song_id, existing_source = db_row
            if existing_source == "manual":
                skipped += 1
                continue

            fields: list[str] = []
            params: list = []
            if bpm is not None:
                fields.append("bpm = ?")
                params.append(bpm)
            if key is not None:
                fields.append("key_sig = ?")
                params.append(key)
            fields.append("bpm_source = 'auto_tagger'")
            fields.append("updated_at = datetime('now')")
            params.append(song_id)

            conn.execute(
                f"UPDATE catalog_songs SET {', '.join(fields)} WHERE id = ?",
                params,
            )
            row["db_updated"] = True
            updated += 1
        except Exception as exc:
            print(
                f"  [warn] catalog_songs update failed for {path_str}: {exc}",
                file=sys.stderr,
            )

    conn.commit()
    return {"updated": updated, "skipped_manual": skipped}


def _write_tracks(scan_results: list[dict], conn, dry_run: bool = False) -> dict:
    """Update tracks rows joined via recordings.file_path → track_id.

    Note: ``tracks`` has no ``bpm_source`` column, so all matched rows are
    updated unconditionally.

    Marks ``row["db_updated"] = True`` for each row written.

    Returns:
        ``{"updated": int}``
    """
    updated = 0
    if dry_run:
        return {"updated": 0}

    for row in scan_results:
        path_str = str(row["path"])
        bpm = row.get("bpm")
        key = row.get("key")
        if bpm is None and key is None:
            continue
        try:
            cur = conn.execute(
                "SELECT track_id FROM recordings WHERE file_path = ?",
                (path_str,),
            )
            rec = cur.fetchone()
            if rec is None:
                continue
            track_id = rec[0]

            fields: list[str] = []
            params: list = []
            if bpm is not None:
                fields.append("tempo_bpm = ?")
                params.append(float(bpm))
            if key is not None:
                fields.append("key_signature = ?")
                params.append(key)
            params.append(track_id)

            conn.execute(
                f"UPDATE tracks SET {', '.join(fields)} WHERE id = ?",
                params,
            )
            row["db_updated"] = True
            updated += 1
        except Exception as exc:
            print(
                f"  [warn] tracks update failed for {path_str}: {exc}",
                file=sys.stderr,
            )

    conn.commit()
    return {"updated": updated}


def _write_id3_for_file(path: Path, suffix: str, bpm: int | None, key: str | None) -> None:
    """Write BPM and/or key into a single audio file's metadata."""
    if suffix == ".mp3":
        from mutagen.id3 import ID3, TBPM, TKEY

        try:
            tags = ID3(str(path))
        except Exception:
            tags = ID3()
        if bpm is not None:
            tags.add(TBPM(encoding=3, text=[str(bpm)]))
        if key is not None:
            tags.add(TKEY(encoding=3, text=[key]))
        tags.save(str(path))

    elif suffix == ".flac":
        from mutagen.flac import FLAC

        audio = FLAC(str(path))
        if bpm is not None:
            audio["bpm"] = [str(bpm)]
        if key is not None:
            audio["key"] = [key]
        audio.save()

    elif suffix == ".m4a":
        from mutagen.mp4 import MP4, MP4FreeForm

        audio = MP4(str(path))
        if audio.tags is None:
            audio.add_tags()
        if bpm is not None:
            audio.tags["tmpo"] = [bpm]
        if key is not None:
            audio.tags["----:com.apple.iTunes:KEY"] = [
                MP4FreeForm(key.encode("utf-8"))
            ]
        audio.save()
    # .wav / .ogg — no universal ID3 write-back standard; skip.


def _write_id3(scan_results: list[dict], skip_masters: bool = False) -> dict:
    """Write BPM / key back into audio file metadata.

    Marks ``row["id3_written"] = True`` for each file successfully written.

    Returns:
        ``{"written": int, "skipped_masters": int, "errors": int}``
    """
    written = skipped_masters = errors = 0
    for row in scan_results:
        path = row["path"]
        bpm = row.get("bpm")
        key = row.get("key")
        if bpm is None and key is None:
            continue
        try:
            resolved = path.resolve()
            if skip_masters and str(resolved).lower().startswith(
                str(_MASTERS_ROOT).lower()
            ):
                skipped_masters += 1
                continue
            suffix = path.suffix.lower()
            if suffix not in {".mp3", ".flac", ".m4a"}:
                continue
            _write_id3_for_file(path, suffix, bpm, key)
            row["id3_written"] = True
            written += 1
        except Exception as exc:
            errors += 1
            print(f"  [warn] ID3 write failed for {path}: {exc}", file=sys.stderr)
    return {"written": written, "skipped_masters": skipped_masters, "errors": errors}


# ---------------------------------------------------------------------------
# HTML report generator
# ---------------------------------------------------------------------------

_HTML_CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 13px; color: #e0e0e0; background: #0d0d0d; line-height: 1.5;
}
.page { max-width: 1160px; margin: 24px auto; }
.header {
  background: linear-gradient(135deg, #1a0505 0%, #2a0808 60%, #3a0a0a 100%);
  border-bottom: 2px solid #cc2222;
  padding: 28px 36px 22px; border-radius: 8px 8px 0 0;
}
.header h1 { font-size: 22px; font-weight: 800; color: #fff; }
.header h1 span { color: #e83333; }
.header .sub { font-size: 12px; color: rgba(255,255,255,.6); margin-top: 6px; }
.summary {
  display: flex; gap: 16px; flex-wrap: wrap;
  padding: 18px 36px; background: #131313; border-bottom: 1px solid #2a2a2a;
}
.stat {
  background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 6px;
  padding: 10px 20px; text-align: center; min-width: 110px;
}
.stat .num { font-size: 24px; font-weight: 700; color: #e83333; }
.stat .lbl { font-size: 11px; color: #888; margin-top: 2px; }
.table-wrap { overflow-x: auto; padding: 0 0 24px; background: #0d0d0d; }
table { width: 100%; border-collapse: collapse; }
thead th {
  background: #1a0505; color: #e83333; font-size: 11px; font-weight: 700;
  text-transform: uppercase; letter-spacing: .06em;
  padding: 10px 12px; text-align: left; border-bottom: 1px solid #cc2222;
  white-space: nowrap;
}
tbody tr { border-bottom: 1px solid #1e1e1e; }
tbody tr:hover { background: #181818; }
tbody td { padding: 7px 12px; font-size: 12px; color: #d0d0d0; }
td.filename {
  color: #fff; font-size: 11px; max-width: 280px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.pass { color: #44cc44; font-weight: 600; }
.fail { color: #e83333; font-weight: 600; }
.yes  { color: #44cc44; }
.no   { color: #555; }
.src-id3  { color: #f0a830; }
.src-lib  { color: #30a8f0; }
.src-unk  { color: #555; }
.src-auto { color: #44cc44; }
"""


def generate_report(
    scan_results: list[dict],
    stats: dict,
    output_path: Path,
) -> None:
    """Write an HTML auto-tagger report to *output_path*."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = stats.get("total", len(scan_results))
    updated = stats.get("catalog_updated", 0) + stats.get("tracks_updated", 0)
    skipped = stats.get("catalog_skipped_manual", 0)
    errors = stats.get("errors", 0)

    def _src_cls(s: str) -> str:
        return {
            "id3_tag": "src-id3",
            "librosa": "src-lib",
            "librosa_chroma": "src-lib",
            "auto_tagger": "src-auto",
        }.get(s, "src-unk")

    rows_html = []
    for row in scan_results:
        p = row["path"]
        size_mb = (
            f"{row.get('size_bytes', 0) / 1_048_576:.1f} MB"
            if row.get("size_bytes")
            else "?"
        )
        bpm = str(row["bpm"]) if row.get("bpm") is not None else "—"
        key = html.escape(row.get("key") or "—")
        bsrc = html.escape(row.get("bpm_source", "unknown"))
        ksrc = html.escape(row.get("key_source", "unknown"))
        err = html.escape(row.get("error") or "")
        p_name = html.escape(p.name)
        p_str = html.escape(str(p))
        integrity = row.get("integrity", False)
        db_upd = row.get("db_updated", False)
        id3_wr = row.get("id3_written", False)

        rows_html.append(
            f"        <tr>"
            f'<td class="filename" title="{p_str}">{p_name}</td>'
            f"<td>{size_mb}</td>"
            f'<td class="{"pass" if integrity else "fail"}">{"PASS" if integrity else "FAIL"}</td>'
            f"<td>{bpm}</td>"
            f'<td class="{_src_cls(bsrc)}">{bsrc}</td>'
            f"<td>{key}</td>"
            f'<td class="{_src_cls(ksrc)}">{ksrc}</td>'
            f'<td class="{"yes" if db_upd else "no"}">{"Y" if db_upd else "N"}</td>'
            f'<td class="{"yes" if id3_wr else "no"}">{"Y" if id3_wr else "N"}</td>'
            f'<td style="color:#e07070;font-size:11px">{err}</td>'
            f"</tr>"
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>&#10084;Music &#x2014; BPM/Key Auto-Tagger Report</title>
<style>{_HTML_CSS}</style>
</head>
<body>
<div class="page">
  <div class="header">
    <h1>&#10084;Music &#x2014; <span>BPM / Key Auto-Tagger</span></h1>
    <div class="sub">Generated {ts} &middot; FR-20260526-bpm-key-auto-tagger</div>
  </div>
  <div class="summary">
    <div class="stat"><div class="num">{total}</div><div class="lbl">Total Files</div></div>
    <div class="stat"><div class="num">{updated}</div><div class="lbl">DB Updated</div></div>
    <div class="stat"><div class="num">{skipped}</div><div class="lbl">Skipped (manual)</div></div>
    <div class="stat"><div class="num">{errors}</div><div class="lbl">Errors</div></div>
  </div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Filename</th><th>Size</th><th>Integrity</th>
          <th>BPM</th><th>BPM Source</th>
          <th>Key</th><th>Key Source</th>
          <th>DB Updated</th><th>ID3 Written</th><th>Error</th>
        </tr>
      </thead>
      <tbody>
{"".join(rows_html)}
      </tbody>
    </table>
  </div>
</div>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"  Report written: {output_path}")


# ---------------------------------------------------------------------------
# CLI modes
# ---------------------------------------------------------------------------


def run_smoke_test(n: int) -> int:
    """Sample *n* files, run integrity check + detection. No DB writes.

    Returns:
        Exit code 0 (all pass) or 1 (any fail).
    """
    all_paths = collect_sources()
    if not all_paths:
        print("[smoke-test] No audio files found across all sources.")
        return 0

    sample = random.sample(all_paths, min(n, len(all_paths)))
    print(f"\n[smoke-test] Sampling {len(sample)} / {len(all_paths)} files\n")

    col_w = 48
    print(
        f"  {'File':<{col_w}}  {'Size':>7}  {'Integ':>5}  {'BPM':>5}  "
        f"{'Key':<15}  {'BPM Src':<14}  Key Src"
    )
    print("  " + "-" * 115)

    any_fail = False
    for p in sample:
        try:
            size_mb = f"{p.stat().st_size / 1_048_576:.1f}M"
        except OSError:
            size_mb = "?"

        integrity = check_integrity(p)
        if not integrity:
            any_fail = True

        if integrity:
            det = detect(p)
        else:
            det = {"bpm": None, "key": None, "bpm_source": "—", "key_source": "—"}

        bpm_str = str(det["bpm"]) if det["bpm"] is not None else "—"
        key_str = det["key"] or "—"
        integ_str = "PASS" if integrity else "FAIL"
        name = p.name[: col_w - 1] if len(p.name) >= col_w else p.name
        print(
            f"  {name:<{col_w}}  {size_mb:>7}  {integ_str:>5}  {bpm_str:>5}  "
            f"{key_str:<15}  {det['bpm_source']:<14}  {det['key_source']}"
        )

    print()
    if any_fail:
        print("[smoke-test] RESULT: FAIL — one or more files did not pass integrity check.")
        return 1
    print("[smoke-test] RESULT: PASS — all sampled files are healthy.")
    return 0


def run_dry_run() -> None:
    """Scan all sources, detect BPM/key, print what would change. No writes."""
    paths = collect_sources()
    print(f"\n[dry-run] Found {len(paths)} audio files. Detecting (no writes)...\n")

    for i, p in enumerate(paths, 1):
        size = p.stat().st_size if p.exists() else 0
        print(f"  [{i}/{len(paths)}] {p.name}", end="  ", flush=True)
        det = detect(p)
        print(
            f"BPM={det['bpm'] or '—'}  Key={det['key'] or '—'}"
            f"  [{det['bpm_source']} / {det['key_source']}]"
        )

    print(f"\n[dry-run] Complete.")


def run_apply(skip_masters: bool = False) -> None:
    """Full run: detect + write DB + write ID3 tags + generate HTML report."""
    paths = collect_sources()
    print(f"\n[apply] Found {len(paths)} audio files. Detecting...\n")

    scan_results: list[dict] = []
    for i, p in enumerate(paths, 1):
        size = p.stat().st_size if p.exists() else 0
        print(f"  [{i}/{len(paths)}] {p.name}", end="  ", flush=True)
        integrity = check_integrity(p)
        error = None
        if integrity:
            try:
                det = detect(p)
            except Exception as exc:
                det = {
                    "bpm": None,
                    "key": None,
                    "bpm_source": "unknown",
                    "key_source": "unknown",
                }
                error = str(exc)
        else:
            det = {
                "bpm": None,
                "key": None,
                "bpm_source": "unknown",
                "key_source": "unknown",
            }
            error = "integrity_fail"

        det_row: dict = {
            "path": p,
            "size_bytes": size,
            "bpm": det["bpm"],
            "key": det["key"],
            "bpm_source": det["bpm_source"],
            "key_source": det["key_source"],
            "integrity": integrity,
            "db_updated": False,
            "id3_written": False,
            "error": error,
        }
        print(
            f"BPM={det['bpm'] or '—'}  Key={det['key'] or '—'}"
            f"  integ={'ok' if integrity else 'FAIL'}"
        )
        scan_results.append(det_row)

    # DB writes.
    print("\n[apply] Writing to DB...")
    try:
        with get_connection() as conn:
            cat_stats = _write_catalog_songs(scan_results, conn)
            trk_stats = _write_tracks(scan_results, conn)
    except Exception as exc:
        print(f"  [error] DB write failed: {exc}", file=sys.stderr)
        cat_stats = {"updated": 0, "skipped_manual": 0}
        trk_stats = {"updated": 0}

    # ID3 write-back.
    print("[apply] Writing ID3 tags...")
    id3_stats = _write_id3(scan_results, skip_masters=skip_masters)

    # Generate HTML report.
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = _REPORT_DIR / f"auto_tagger_{ts}.html"
    stats = {
        "total": len(scan_results),
        "catalog_updated": cat_stats.get("updated", 0),
        "catalog_skipped_manual": cat_stats.get("skipped_manual", 0),
        "tracks_updated": trk_stats.get("updated", 0),
        "errors": sum(1 for r in scan_results if r.get("error")),
    }
    generate_report(scan_results, stats, report_path)

    print("\n[apply] Done.")
    print(f"  Catalog rows updated  : {cat_stats.get('updated', 0)}")
    print(f"  Tracks rows updated   : {trk_stats.get('updated', 0)}")
    print(f"  Manual skipped        : {cat_stats.get('skipped_manual', 0)}")
    print(f"  ID3 tags written      : {id3_stats.get('written', 0)}")
    print(f"  ID3 masters skipped   : {id3_stats.get('skipped_masters', 0)}")
    print(f"  Errors                : {stats['errors']}")
    print(f"  Report                : {report_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="auto_tagger.py",
        description="BPM / Key auto-tagger for the ❤Music catalog",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--smoke-test",
        metavar="N",
        type=int,
        help="Sample N files, integrity check only — no DB or ID3 writes",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect only — no DB or ID3 writes",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Full run: detect + write DB + ID3",
    )
    parser.add_argument(
        "--skip-masters",
        action="store_true",
        help=r"With --apply: skip ID3 write-back for f:\Masters files only",
    )
    args = parser.parse_args(argv)

    if args.smoke_test is not None:
        return run_smoke_test(args.smoke_test)
    elif args.dry_run:
        run_dry_run()
        return 0
    else:
        run_apply(skip_masters=args.skip_masters)
        return 0


if __name__ == "__main__":
    sys.exit(main())
