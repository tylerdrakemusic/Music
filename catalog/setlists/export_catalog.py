"""
Export band management data from heartmusic.db.

Injects all band/catalog/setlist data inline into portal.html (avoids
fetch() file:// CORS restrictions when the portal is opened as a local file).

Outputs:
  f:\❤Music\catalog\setlists\catalog_export.json      (legacy, kept for reference)
  f:\❤Music\catalog\setlists\setlist_active_export.json (legacy)
  f:\⊕Workspace\reports\portal.html  (BM_INLINE data block updated)

Usage:
    C:\G\python.exe f:\❤Music\catalog\setlists\export_catalog.py
    C:\G\python.exe f:\❤Music\catalog\setlists\export_catalog.py --panel
    C:\G\python.exe f:\❤Music\catalog\setlists\export_catalog.py --watch --panel

Run this after any DB update (seed, migration, manual edit) to refresh the portal.
"""
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

PORTAL_PATH  = Path(r"f:\⊕Workspace\reports\portal.html")
SHEET_MUSIC  = Path(r"f:\❤Music\catalog\sheet_music")
AUDIO_ROOT   = Path(r"G:\Muzic")
BM_START     = "// <!--BM_DATA_START-->"
BM_END       = "// <!--BM_DATA_END-->"

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from utils.init_db import get_connection  # noqa: E402

OUT_DIR = Path(__file__).parent


# ── Sheet music matching ──────────────────────────────────────────────────────

_ARTICLES = frozenset(("the", "a", "an"))


def _normalize(s: str) -> str:
    """Lowercase, strip accents, remove punctuation, strip leading articles."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = "".join(c for c in s.lower() if c.isalnum() or c.isspace()).strip()
    words = s.split()
    if words and words[0] in _ARTICLES:
        s = " ".join(words[1:])
    return s


def _strip_variant(s: str) -> str:
    """Remove trailing parenthetical info like '(in B)', '(Key Gm)', '(Brass)'."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", s).strip()


def build_sheet_music_index() -> dict:
    """
    Walk SHEET_MUSIC dir. Indexes both halves of 'A - B' filenames so that
    either 'Title - Artist' or 'Artist - Title' naming conventions match.
    Returns dict keyed by normalized title -> list of file:/// URIs.
    """
    index = {}
    if not SHEET_MUSIC.exists():
        return index
    for f in SHEET_MUSIC.rglob("*"):
        if not f.is_file() or f.suffix.lower() in (".txt",):
            continue
        stem = f.stem
        parts = [p.strip() for p in stem.split(" - ", 1)] if " - " in stem else [stem.strip()]
        for part in parts:
            key = _normalize(_strip_variant(part))
            if key:
                index.setdefault(key, []).append(f.as_uri())
    return index


def sheet_music_for(title: str, index: dict) -> list:
    return index.get(_normalize(title), [])


def _audio_url(source_file: str | None) -> str | None:
    """Convert a bare source_file filename to a file:/// URI pointing at AUDIO_ROOT."""
    if not source_file:
        return None
    full = AUDIO_ROOT / source_file
    try:
        return full.as_uri()
    except ValueError:
        # On non-Windows CI, AUDIO_ROOT is a relative path (G:\Muzic is not
        # a valid POSIX absolute path). Build the file URI from the raw string.
        from urllib.parse import quote  # noqa: PLC0415
        raw = str(full).replace("\\", "/")
        return "file:///" + quote(raw, safe="/:")


# ── DB queries ────────────────────────────────────────────────────────────────

def export_bands(conn) -> list:
    return [
        {"id": r[0], "name": r[1], "genre": r[2], "active": bool(r[3])}
        for r in conn.execute(
            "SELECT id, name, genre, active FROM bands ORDER BY id"
        ).fetchall()
    ]


def export_catalog_for_band(conn, band_id: int, sm_index: dict) -> list:
    """All songs this band has arrangements for, using band default key/bpm."""
    rows = conn.execute(
        """SELECT cs.id, cs.title, cs.artist,
                  COALESCE(bsa.default_key, cs.key_sig) AS key_sig,
                  COALESCE(bsa.default_bpm, cs.bpm)     AS bpm,
                  cs.bpm_source, cs.genre, cs.source_file
           FROM catalog_songs cs
           JOIN band_song_arrangements bsa
             ON bsa.catalog_song_id = cs.id AND bsa.band_id = ?
           ORDER BY cs.artist, cs.title""",
        (band_id,),
    ).fetchall()
    return [
        {
            "id": r[0], "title": r[1], "artist": r[2],
            "key": r[3], "bpm": r[4], "bpm_source": r[5], "genre": r[6],
            "sheet_music": sheet_music_for(r[1], sm_index),
            "audio_url": _audio_url(r[7]),
        }
        for r in rows
    ]


def export_active_setlist_for_band(conn, band_id: int) -> tuple:
    sl = conn.execute(
        "SELECT id, name, band, gig_date, venue FROM setlists WHERE band_id=? AND active=1 LIMIT 1",
        (band_id,),
    ).fetchone()
    if not sl:
        return {}, []
    meta = {"id": sl[0], "name": sl[1], "band": sl[2], "gig_date": sl[3], "venue": sl[4]}
    rows = conn.execute(
        """SELECT ss.set_number, ss.position,
                  cs.title, cs.artist,
                  COALESCE(ss.key_override, bsa.default_key, cs.key_sig) AS key_sig,
                  COALESCE(ss.bpm_override, bsa.default_bpm, cs.bpm)     AS bpm,
                  cs.bpm_source, cs.id, ss.notes, cs.source_file
           FROM setlist_songs ss
           JOIN catalog_songs cs    ON cs.id = ss.catalog_song_id
           LEFT JOIN band_song_arrangements bsa
             ON bsa.catalog_song_id = cs.id AND bsa.band_id = ?
           WHERE ss.setlist_id = ?
           ORDER BY ss.set_number, ss.position""",
        (band_id, sl[0]),
    ).fetchall()
    songs = []
    for r in rows:
        artist = r[3] or ""
        entry = {
            "set": r[0], "order": r[1], "title": r[2], "artist": artist,
            "key": r[4], "bpm": r[5], "bpm_source": r[6], "catalog_id": r[7],
            "notes": r[8] or None,
            "audio_url": _audio_url(r[9]),
        }
        if artist.startswith("\u26a0"):  # ⚠ NOT IN CATALOG
            entry["catalog_warning"] = True
            entry["artist"] = ""
        else:
            entry["catalog_warning"] = False
        songs.append(entry)
    return meta, songs


# ── Main ──────────────────────────────────────────────────────────────────────

def _run_panel_generator() -> None:
    panel_script = Path(__file__).resolve().parents[2] / "src" / "band_mgmt" / "generate_band_mgmt_panel.py"
    if not panel_script.exists():
        print(f"WARNING: panel generator not found at {panel_script} — skipping panel regeneration")
        return

    print(f"Regenerating band management panel HTML via {panel_script}")
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, str(panel_script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if result.returncode != 0:
        print("ERROR: panel generator failed")
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return
    print("Panel regeneration completed.")


def _path_mtime(path: Path) -> float | None:
    try:
        if path.is_file():
            return path.stat().st_mtime
        if path.is_dir():
            mtimes = [f.stat().st_mtime for f in path.rglob("*") if f.is_file()]
            return max(mtimes) if mtimes else path.stat().st_mtime
        return None
    except OSError:
        return None


def run_export(regenerate_panel: bool = False) -> None:
    main()
    if regenerate_panel:
        _run_panel_generator()


def watch_export(regenerate_panel: bool = False, interval: float = 2.0) -> None:
    db_path = Path(__file__).resolve().parents[2] / "src" / "data" / "heartmusic.db"
    watch_paths = [db_path, SHEET_MUSIC]
    last_mtimes = {path: _path_mtime(path) for path in watch_paths}

    print(f"Watching {', '.join(str(p) for p in watch_paths)} for changes...")
    print("Press Ctrl+C to stop.")
    while True:
        time.sleep(interval)
        changed = False
        for path in watch_paths:
            current = _path_mtime(path)
            if current != last_mtimes.get(path):
                changed = True
                last_mtimes[path] = current
        if changed:
            print(f"Change detected at {datetime.now(timezone.utc).isoformat()}; regenerating exports.")
            run_export(regenerate_panel)


def main(regenerate_panel: bool = False) -> None:
    conn = get_connection()
    conn.execute("PRAGMA foreign_keys=ON")

    ts = datetime.now(timezone.utc).isoformat()
    sm_index = build_sheet_music_index()
    print(f"Sheet music index: {len(sm_index)} unique titles found")

    bands = export_bands(conn)
    if not bands:
        print("No bands found. Run migrate_bands.py first.")
        conn.close()
        return

    bands_data = []
    for band in bands:
        catalog_songs = export_catalog_for_band(conn, band["id"], sm_index)
        setlist_meta, setlist_songs = export_active_setlist_for_band(conn, band["id"])
        bands_data.append({
            **band,
            "catalog": {"count": len(catalog_songs), "songs": catalog_songs},
            "setlist": {"setlist": setlist_meta, "count": len(setlist_songs), "songs": setlist_songs},
        })
        sm_count = sum(1 for s in catalog_songs if s["sheet_music"])
        print(f"  {band['name']}: {len(catalog_songs)} catalog, "
              f"{len(setlist_songs)} setlist, {sm_count} with sheet music")

    conn.close()

    # ── Legacy single-band JSON exports ───────────────────────────────────────
    cc = next((b for b in bands_data if b["name"] == "Copper Creek"), None)
    if cc:
        (OUT_DIR / "catalog_export.json").write_text(
            json.dumps({"exported_at": ts, **cc["catalog"]}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        (OUT_DIR / "setlist_active_export.json").write_text(
            json.dumps({"exported_at": ts, **cc["setlist"]}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print("Legacy JSON exports written.")

    # ── Inject all bands inline into portal.html ──────────────────────────────
    if not PORTAL_PATH.exists():
        print(f"WARNING: portal.html not found at {PORTAL_PATH} — skipping injection")
        return

    portal = PORTAL_PATH.read_text(encoding="utf-8")
    inline_payload = {"exported_at": ts, "bands": bands_data}
    js_block = f"  const BM_INLINE = {json.dumps(inline_payload, ensure_ascii=False)};"

    start_idx = portal.find(BM_START)
    end_idx   = portal.find(BM_END)
    if start_idx == -1 or end_idx == -1:
        print("WARNING: BM_DATA markers not found in portal.html — skipping injection")
        return

    new_portal = (
        portal[: start_idx + len(BM_START)]
        + "\n"
        + js_block
        + "\n  "
        + portal[end_idx:]
    )
    PORTAL_PATH.write_text(new_portal, encoding="utf-8")
    print(f"Injected {len(bands_data)} band(s) inline into portal.html ({len(js_block)} chars)")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Export HeartMusic band data and optionally watch for DB changes.")
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch heartmusic.db and sheet_music for changes and regenerate exports automatically.",
    )
    parser.add_argument(
        "--panel",
        action="store_true",
        help="Also regenerate the Band Management panel HTML after each export.",
    )
    args = parser.parse_args()

    if args.watch:
        watch_export(regenerate_panel=args.panel)
    else:
        run_export(regenerate_panel=args.panel)
