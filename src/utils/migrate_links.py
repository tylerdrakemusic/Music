"""One-time migration: read linkTyler.json → insert into artist_links table.

Usage:
    C:\\G\\python.exe f:\\❤Music\\src\\utils\\migrate_links.py

Idempotent: if artist_links already contains rows the script exits without
re-inserting.  Delete rows manually if you need to re-run.

JSON quirks handled:
 - Missing comma between consecutive string values in a JSON array
   (known bug in linkTyler.json Spotify section)
 - Tidal: malformed nested <iframe> stored verbatim as embed_html
 - Bandcamp shortcodes ( [bandcamp ...] ) stored as embed_html
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

PROJECT_SRC = Path(__file__).resolve().parent.parent
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from utils.init_db import get_connection  # noqa: E402

JSON_PATH = Path(__file__).resolve().parents[2] / "studio_master" / "linkTyler.json"
BACKUP_PATH = JSON_PATH.parent / "linkTyler_backup.json"

# Any url/embed_html containing these substrings → status = 'pending'
_PENDING_NEEDLES = ("yourartistid", "yourtrackid", "yourprofile2")


# ── helpers ───────────────────────────────────────────────────────────────────

def _is_iframe(s: str) -> bool:
    return s.strip().startswith("<iframe")


def _is_shortcode(s: str) -> bool:
    return s.strip().startswith("[")


def _detect_status(text: str) -> str:
    low = text.lower()
    return "pending" if any(p in low for p in _PENDING_NEEDLES) else "confirmed"


def _make_row(
    *,
    category: str,
    platform: str,
    label: str,
    url: str | None = None,
    embed_html: str | None = None,
    song_title: str | None = None,
    sort_order: int = 0,
) -> dict:
    check_text = url or embed_html or ""
    return {
        "category": category,
        "platform": platform,
        "label": label,
        "url": url,
        "embed_html": embed_html,
        "song_title": song_title,
        "status": _detect_status(check_text),
        "sort_order": sort_order,
    }


def _item_row(
    item: str,
    *,
    category: str,
    platform: str,
    label: str,
    song_title: str | None = None,
    sort_order: int = 0,
) -> dict:
    """Classify a single JSON string item as url or embed_html."""
    if _is_iframe(item) or _is_shortcode(item):
        return _make_row(
            category=category,
            platform=platform,
            label=label,
            embed_html=item,
            song_title=song_title,
            sort_order=sort_order,
        )
    return _make_row(
        category=category,
        platform=platform,
        label=label,
        url=item,
        song_title=song_title,
        sort_order=sort_order,
    )


# ── public API (importable by tests) ─────────────────────────────────────────

def _fix_json(raw: str) -> str:
    """Fix known JSON issues in linkTyler.json.

    The Spotify section has a missing comma between adjacent string values::

        "spotify:artist:2PCvPDydZKbRUHb6lZMJXv"
        "https://open.spotify.com/artist/..."

    This regex inserts a comma between any two consecutive JSON strings that
    are separated only by whitespace/newlines — safe because JSON arrays of
    strings always need commas between elements.
    """
    return re.sub(r'("(?:[^"\\]|\\.)*")\s*\n(\s*")', r'\1,\n\2', raw)


def load_data() -> dict:
    """Read and parse linkTyler.json, fixing known syntax issues."""
    raw = JSON_PATH.read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return json.loads(_fix_json(raw))


def collect_rows(data: dict) -> list[dict]:
    """Convert the linkTyler data structure into a flat list of DB rows."""
    rows: list[dict] = []
    sort = 0

    # ── emails ───────────────────────────────────────────────────────────────
    for email in data.get("emails", []):
        rows.append(
            _make_row(
                category="email",
                platform="Email",
                label=email,
                url=email,
                sort_order=sort,
            )
        )
        sort += 1

    # ── social_media ─────────────────────────────────────────────────────────
    for platform, urls in data.get("social_media", {}).items():
        for item in urls:
            rows.append(
                _item_row(
                    item,
                    category="social",
                    platform=platform,
                    label="Artist page",
                    sort_order=sort,
                )
            )
            sort += 1

    # ── payment ──────────────────────────────────────────────────────────────
    for platform, urls in data.get("payment", {}).items():
        for item in urls:
            rows.append(
                _item_row(
                    item,
                    category="payment",
                    platform=platform,
                    label="Payment link",
                    sort_order=sort,
                )
            )
            sort += 1

    # ── distribution_platforms ───────────────────────────────────────────────
    for platform, pdata in data.get("distribution_platforms", {}).items():

        # Special: Pandora AMP management block
        if platform == "Pandora" and "amp_management" in pdata:
            amp = pdata["amp_management"]
            rows.append(
                _make_row(
                    category="distribution",
                    platform="Pandora",
                    label="AMP Management",
                    url="https://amp.pandora.com",
                    sort_order=sort,
                )
            )
            sort += 1
            if amp.get("claim_status") == "PENDING":
                submitted = amp.get("claim_submitted", "")
                claim_label = (
                    f"Claim PENDING (submitted {submitted})" if submitted else "Claim PENDING"
                )
                rows.append({
                    "category": "distribution",
                    "platform": "Pandora",
                    "label": claim_label,
                    "url": "https://amp.pandora.com",
                    "embed_html": None,
                    "song_title": None,
                    "status": "pending",
                    "sort_order": sort,
                })
                sort += 1

        # artist_links
        for item in pdata.get("artist_links", []):
            rows.append(
                _item_row(
                    item,
                    category="distribution",
                    platform=platform,
                    label="Artist page",
                    sort_order=sort,
                )
            )
            sort += 1

        # songs
        songs = pdata.get("songs", {})
        for song_title, items in songs.items():
            for item in items:
                rows.append(
                    _item_row(
                        item,
                        category="distribution",
                        platform=platform,
                        label=song_title,
                        song_title=song_title,
                        sort_order=sort,
                    )
                )
                sort += 1

    return rows


def run_migration() -> int:
    """Backup JSON, load data, and insert rows into artist_links.

    Returns the number of rows inserted (0 if already populated).
    """
    # Backup source JSON
    shutil.copy2(JSON_PATH, BACKUP_PATH)
    print(f"Backed up to {BACKUP_PATH}")

    data = load_data()
    rows = collect_rows(data)

    with get_connection() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM artist_links").fetchone()[0]
        if existing > 0:
            print(f"artist_links already has {existing} rows — skipping (idempotent).")
            return 0

        conn.executemany(
            """
            INSERT INTO artist_links
                (category, platform, label, url, embed_html, song_title, status, sort_order)
            VALUES
                (:category, :platform, :label, :url, :embed_html, :song_title, :status, :sort_order)
            """,
            rows,
        )
        conn.commit()
        inserted = conn.execute("SELECT COUNT(*) FROM artist_links").fetchone()[0]

    print(f"Inserted {inserted} rows into artist_links.")
    return inserted


if __name__ == "__main__":
    n = run_migration()
    sys.exit(0)
