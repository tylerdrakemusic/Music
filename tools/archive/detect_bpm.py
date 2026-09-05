# DEPRECATED: superseded by tools/auto_tagger.py (FR-20260526-bpm-key-auto-tagger)
"""
detect_bpm.py — Detect BPM for songs missing it in the DB.

Strategy:
  1. librosa beat_track on the G:\Muzic source file
  2. Cross-verify via songbpm.com web lookup
  3. If both agree within ±5 BPM → use consensus average (rounded)
     If only librosa → use librosa result
     If discrepancy > 5 → report both, use librosa (warn user)
  4. Write confirmed BPM values to catalog_songs via --apply flag

Usage:
    python tools/detect_bpm.py          # dry-run — print results only
    python tools/detect_bpm.py --apply  # write to DB
"""
from __future__ import annotations
import argparse, re, sys, time
from pathlib import Path

import librosa
import numpy as np
import urllib.request

sys.path.insert(0, "src")
from utils.init_db import get_connection

AUDIO_ROOT = Path(r"G:\Muzic")

# Same map as update_audio_sources.py — title → filename in G:\Muzic
AUDIO_MAP: dict[str, str] = {
    "I'm Alright":          "I'm Alright - Kenny Loggins.mp3",
    "Talk Me Into It":      "Talk Me Into It - Kevin Redmond.mp3",
    "Shaded Jade":          "Shaded Jade - Tamala Cameron and Gene Ngo.mp3",
    "Play That Funky Music": "Play That Funky Music - Wild Cherry.mp3",
    "On the Dark Side":     "On the Darkside - John Cafferty.mp3",
    "Celebrate":            "Celebration - Kool and The Gang.mp3",
}

# Web cross-verification slugs for known songs
# Format: (artist_slug, title_slug) for songbpm.com
WEB_SLUGS: dict[str, str] = {
    "I'm Alright":          "kenny-loggins/im-alright",
    "Talk Me Into It":      None,   # obscure — skip web
    "Shaded Jade":          None,   # original — skip web
    "Play That Funky Music": "wild-cherry/play-that-funky-music",
    "On the Dark Side":     "john-cafferty-and-the-beaver-brown-band/on-the-dark-side",
    "Celebrate":            "kool-the-gang/celebration",
}

SONGBPM_URL = "https://songbpm.com/@{slug}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}
BPM_PATTERN = re.compile(r'"bpm"\s*:\s*(\d+)', re.IGNORECASE)
BPM_SPAN_PATTERN = re.compile(r'<[^>]*class="[^"]*bpm[^"]*"[^>]*>\s*(\d{2,3})', re.IGNORECASE)


def librosa_bpm(path: Path) -> float:
    """Load up to 3 minutes of audio and return beat-tracked BPM."""
    y, sr = librosa.load(str(path), sr=22050, mono=True, duration=180.0)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr, units="time")
    # librosa may return an array; take the first value
    bpm = float(np.atleast_1d(tempo)[0])
    return round(bpm, 1)


def web_bpm(slug: str | None) -> int | None:
    """Fetch BPM from songbpm.com. Returns int or None."""
    if not slug:
        return None
    url = SONGBPM_URL.format(slug=slug)
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        # Try JSON-LD / data attribute first
        m = BPM_PATTERN.search(html)
        if m:
            return int(m.group(1))
        # Fallback: span with bpm class
        m = BPM_SPAN_PATTERN.search(html)
        if m:
            return int(m.group(1))
        return None
    except Exception as e:
        print(f"      web lookup failed ({e})")
        return None


def consensus(librosa_val: float, web_val: int | None) -> tuple[int, str]:
    """Return (bpm, source_label). Source is 'librosa', 'web', or 'consensus'."""
    if web_val is None:
        return (round(librosa_val), "librosa")
    diff = abs(librosa_val - web_val)
    if diff <= 5:
        avg = round((librosa_val + web_val) / 2)
        return (avg, f"consensus ({librosa_val} lib / {web_val} web)")
    else:
        print(f"      ⚠ discrepancy {diff:.1f} BPM — using librosa, flagging")
        return (round(librosa_val), f"librosa (web={web_val}, diff={diff:.1f})")


def get_song_id(conn, title: str) -> int | None:
    cur = conn.execute(
        "SELECT id FROM catalog_songs WHERE title = ?", (title,)
    )
    row = cur.fetchone()
    return row[0] if row else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write BPM to DB")
    args = parser.parse_args()

    results: list[tuple[str, int, str]] = []

    for title, filename in AUDIO_MAP.items():
        path = AUDIO_ROOT / filename
        print(f"\n{'='*55}")
        print(f"  {title}")
        print(f"  File: {filename}")

        if not path.exists():
            print(f"  ✗ Audio file not found: {path}")
            continue

        print("  → librosa analysis (up to 3 min)…", end="", flush=True)
        lb = librosa_bpm(path)
        print(f" {lb:.1f} BPM")

        slug = WEB_SLUGS.get(title)
        print(f"  → web lookup ({slug or 'skip'})…", end="", flush=True)
        wb = web_bpm(slug)
        if wb:
            print(f" {wb} BPM")
        else:
            print(" n/a")
        time.sleep(0.5)  # polite delay

        bpm, source = consensus(lb, wb)
        print(f"  ✓ Final BPM: {bpm}  [{source}]")
        results.append((title, bpm, source))

    print(f"\n{'='*55}")
    print("Summary:")
    for title, bpm, source in results:
        print(f"  {bpm:3d}  {title}  ({source})")

    if args.apply:
        print("\nApplying to DB…")
        conn = get_connection()
        updated = 0
        for title, bpm, _ in results:
            song_id = get_song_id(conn, title)
            if song_id is None:
                print(f"  ✗ Song not found in DB: {title}")
                continue
            conn.execute("UPDATE catalog_songs SET bpm = ? WHERE id = ?", (bpm, song_id))
            print(f"  ✓ [{song_id}] {title} → {bpm} BPM")
            updated += 1
        conn.commit()
        conn.close()
        print(f"\n{updated} song(s) updated.")
    else:
        print("\nDry-run — pass --apply to write to DB.")


if __name__ == "__main__":
    main()

