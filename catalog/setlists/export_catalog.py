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

Run this after any DB update (seed, migration, manual edit) to refresh the portal.
"""
import json
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

PORTAL_PATH  = Path(r"f:\⊕Workspace\reports\portal.html")
SHEET_MUSIC  = Path(r"f:\❤Music\catalog\sheet_music")
BM_START     = "// <!--BM_DATA_START-->"
BM_END       = "// <!--BM_DATA_END-->"

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from utils.init_db import get_connection  # noqa: E402

OUT_DIR = Path(__file__).parent


# ── Sheet music matching ──────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    """Lowercase, strip accents, remove punctuation for fuzzy matching."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return "".join(c for c in s.lower() if c.isalnum() or c.isspace()).strip()


def build_sheet_music_index() -> dict:
    """
    Walk SHEET_MUSIC dir. Parse filenames of the form:
        <Title> - <Artist> [(<variant>)].<ext>
        <Title>.<ext>   (for originals)
    Returns dict keyed by normalized title -> list of file:/// URIs.
    """
    index = {}
    if not SHEET_MUSIC.exists():
        return index
    for f in SHEET_MUSIC.rglob("*"):
        if not f.is_file() or f.suffix.lower() in (".txt",):
            continue
        stem = f.stem  # e.g. "Celebration - Kool & The Gang (Horns)"
        title_part = stem.split(" - ")[0].strip() if " - " in stem else stem.strip()
        key = _normalize(title_part)
        index.setdefault(key, []).append(f.as_uri())
    return index


def sheet_music_for(title: str, index: dict) -> list:
    return index.get(_normalize(title), [])


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
                  cs.bpm_source, cs.genre
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
                  cs.bpm_source, cs.id
           FROM setlist_songs ss
           JOIN catalog_songs cs    ON cs.id = ss.catalog_song_id
           LEFT JOIN band_song_arrangements bsa
             ON bsa.catalog_song_id = cs.id AND bsa.band_id = ?
           WHERE ss.setlist_id = ?
           ORDER BY ss.set_number, ss.position""",
        (band_id, sl[0]),
    ).fetchall()
    songs = [
        {"set": r[0], "order": r[1], "title": r[2], "artist": r[3],
         "key": r[4], "bpm": r[5], "bpm_source": r[6], "catalog_id": r[7]}
        for r in rows
    ]
    return meta, songs


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
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
    main()
