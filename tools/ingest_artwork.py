#!/usr/bin/env python3
"""
Ingest artwork from a tmp drop folder into catalog/artwork/originals/.

Naming convention used in originals/:
    {Title} - Tyler James Drake.{ext}

Duplicate handling:
  COPY_NEW       — no existing match; copy with canonical name + update DB
  SKIP_EXACT_DUP — SHA-256 matches an existing file in originals/
  SKIP_SEMANTIC  — same canonical name (title+ext) already exists
  MANUAL_REVIEW  — could not match filename to any Tyler James Drake catalog song

Usage:
    python tools/ingest_artwork.py            # dry run (default)
    python tools/ingest_artwork.py --apply    # copy files + update DB + embed covers
    python tools/ingest_artwork.py --tmp C:\\path\\to\\other\\folder
"""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT  = Path(__file__).resolve().parents[1]
ORIGINALS_DIR = PROJECT_ROOT / "catalog" / "artwork" / "originals"
DEFAULT_TMP   = Path(r"C:\Users\tyler\Desktop\tmp")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
ARTIST = "Tyler James Drake"

# Common filename suffixes that should be stripped before title matching.
_ARTWORK_SUFFIX_RE = re.compile(
    r"\s+(?:song\s+art\s+image|song\s+art|art\s+image|album\s+art|cover)$",
    re.IGNORECASE,
)

# Similarity threshold for fuzzy title matching.
_MATCH_THRESHOLD = 0.75


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalize(s: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    s = s.lower()
    s = re.sub(r"[^\w\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _extract_title_from_stem(stem: str) -> str:
    """Strip common artwork naming suffixes to surface the candidate song title."""
    return _ARTWORK_SUFFIX_RE.sub("", stem).strip()


def canonical_name(title: str, ext: str) -> str:
    """Return the canonical artwork filename for a Tyler James Drake original.

    Args:
        title: The canonical song title from the DB.
        ext:   File extension including the leading dot, e.g. '.jpg'.

    Returns:
        Filename string, e.g. 'Bloom - Tyler James Drake.jpg'.
    """
    return f"{title} - {ARTIST}{ext}"


def _safe_path(p: Path, allowed_roots: tuple[Path, ...]) -> bool:
    """Return True only if *p* resolves to inside one of *allowed_roots*.

    Guards against symlink-based path traversal attacks.
    """
    resolved = p.resolve()
    return any(
        str(resolved).startswith(str(root.resolve()) + ("" if str(root.resolve()).endswith("\\") or str(root.resolve()).endswith("/") else ("/" if "/" in str(root.resolve()) else "\\")))
        for root in allowed_roots
    )


def _match_song(candidate_title: str, originals: list[dict]) -> dict | None:
    """Find the best matching catalog song for a candidate title string.

    Args:
        candidate_title: Title extracted from the filename.
        originals:       List of song dicts from the DB.

    Returns:
        The matching song dict, or None if no sufficiently close match exists.
    """
    norm_query = _normalize(candidate_title)
    best_score = 0.0
    best_song: dict | None = None

    for song in originals:
        norm_db = _normalize(song["title"])
        if norm_query == norm_db:
            return song  # exact normalized match — no need to continue
        score = SequenceMatcher(None, norm_query, norm_db).ratio()
        if score > best_score:
            best_score = score
            best_song = song

    if best_score >= _MATCH_THRESHOLD:
        return best_song
    return None


# ---------------------------------------------------------------------------
# Action plan (pure — no side effects)
# ---------------------------------------------------------------------------

class IngestAction(NamedTuple):
    action: str        # COPY_NEW | SKIP_EXACT_DUP | SKIP_SEMANTIC | MANUAL_REVIEW
    src: Path
    dest_name: str     # canonical filename, or src.name for MANUAL_REVIEW
    reason: str
    song_id: int | None
    song_title: str
    source_file: str | None


def plan_actions(
    tmp_dir: Path,
    originals_dir: Path,
    originals: list[dict],
    allowed_roots: tuple[Path, ...] | None = None,
) -> list[IngestAction]:
    """Scan *tmp_dir* for image files and return a list of IngestActions.

    Args:
        tmp_dir:       Directory to scan for incoming artwork.
        originals_dir: Destination directory (catalog/artwork/originals/).
        originals:     Tyler James Drake songs from catalog_songs.
        allowed_roots: Paths that source files must resolve within (traversal guard).
                       Defaults to (tmp_dir.resolve(),).

    Returns:
        Ordered list of IngestAction named tuples.
    """
    if allowed_roots is None:
        allowed_roots = (tmp_dir.resolve(),)

    # Index existing artwork.
    existing_by_hash: dict[str, Path] = {}
    existing_names: set[str] = set()
    if originals_dir.exists():
        for f in sorted(originals_dir.iterdir()):
            if f.is_file() and f.name != ".gitkeep":
                existing_by_hash[_sha256(f)] = f
                existing_names.add(f.name.lower())

    actions: list[IngestAction] = []

    for src in sorted(tmp_dir.iterdir()):
        if not src.is_file():
            continue
        ext = src.suffix.lower()
        if ext not in IMAGE_EXTS:
            continue

        # Path traversal guard.
        if not _safe_path(src, allowed_roots):
            continue

        # Exact duplicate by hash.
        h = _sha256(src)
        if h in existing_by_hash:
            actions.append(IngestAction(
                action="SKIP_EXACT_DUP",
                src=src,
                dest_name="",
                reason=f"hash match → {existing_by_hash[h].name}",
                song_id=None,
                song_title="",
                source_file=None,
            ))
            continue

        # Extract candidate title and match against catalog.
        candidate_title = _extract_title_from_stem(src.stem)
        song = _match_song(candidate_title, originals)

        if song is None:
            actions.append(IngestAction(
                action="MANUAL_REVIEW",
                src=src,
                dest_name=src.name,
                reason="no catalog match found",
                song_id=None,
                song_title="",
                source_file=None,
            ))
            continue

        dest = canonical_name(song["title"], ext)

        # Semantic duplicate: canonical name already exists.
        if dest.lower() in existing_names:
            actions.append(IngestAction(
                action="SKIP_SEMANTIC",
                src=src,
                dest_name=dest,
                reason=f"title+ext already exists: {dest}",
                song_id=song["id"],
                song_title=song["title"],
                source_file=song.get("source_file"),
            ))
            continue

        actions.append(IngestAction(
            action="COPY_NEW",
            src=src,
            dest_name=dest,
            reason="",
            song_id=song["id"],
            song_title=song["title"],
            source_file=song.get("source_file"),
        ))

    return actions


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def add_artwork_column_if_missing(conn) -> None:
    """Idempotent migration: add artwork_path TEXT column to catalog_songs."""
    cur = conn.execute("PRAGMA table_info(catalog_songs)")
    cols = {row[1] for row in cur.fetchall()}
    if "artwork_path" not in cols:
        conn.execute("ALTER TABLE catalog_songs ADD COLUMN artwork_path TEXT")
        conn.commit()


def load_originals(conn) -> list[dict]:
    """Return all Tyler James Drake songs from catalog_songs."""
    cur = conn.execute(
        "SELECT id, title, source_file, artwork_path"
        " FROM catalog_songs WHERE artist = ?",
        (ARTIST,),
    )
    return [
        {"id": r[0], "title": r[1], "source_file": r[2], "artwork_path": r[3]}
        for r in cur.fetchall()
    ]


# ---------------------------------------------------------------------------
# Audio cover-art embedding
# ---------------------------------------------------------------------------

def embed_cover(audio_path: Path, image_path: Path) -> str:
    """Embed *image_path* as cover art into *audio_path* using mutagen.

    Args:
        audio_path: Path to the audio file (MP3 / FLAC / MP4 / M4A).
        image_path: Path to the image file to embed.

    Returns:
        Status string: 'EMBEDDED', 'SKIPPED_NO_FILE', 'SKIPPED_NO_MUTAGEN',
        'SKIPPED_FORMAT', or 'ERROR: <message>'.
    """
    if not audio_path.exists():
        return "SKIPPED_NO_FILE"

    try:
        import mutagen  # noqa: F401
    except ImportError:
        return "SKIPPED_NO_MUTAGEN"

    ext = audio_path.suffix.lower()
    image_data = image_path.read_bytes()
    mime = (
        "image/jpeg"
        if image_path.suffix.lower() in (".jpg", ".jpeg")
        else "image/png"
    )

    try:
        if ext == ".mp3":
            from mutagen.id3 import ID3, APIC
            from mutagen.id3 import error as ID3Error
            try:
                tags = ID3(str(audio_path))
            except ID3Error:
                tags = ID3()
            tags.delall("APIC")
            tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=image_data))
            tags.save(str(audio_path))
            return "EMBEDDED"

        elif ext == ".flac":
            from mutagen.flac import FLAC, Picture
            audio = FLAC(str(audio_path))
            pic = Picture()
            pic.type = 3
            pic.mime = mime
            pic.data = image_data
            audio.clear_pictures()
            audio.add_picture(pic)
            audio.save()
            return "EMBEDDED"

        elif ext in (".mp4", ".m4a"):
            from mutagen.mp4 import MP4, MP4Cover
            audio = MP4(str(audio_path))
            fmt = (
                MP4Cover.FORMAT_JPEG
                if image_path.suffix.lower() in (".jpg", ".jpeg")
                else MP4Cover.FORMAT_PNG
            )
            audio.tags["covr"] = [MP4Cover(image_data, imageformat=fmt)]
            audio.save()
            return "EMBEDDED"

        else:
            return "SKIPPED_FORMAT"

    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {exc}"


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def main(
    tmp_dir: Path = DEFAULT_TMP,
    apply: bool = False,
    get_conn=None,
) -> None:
    """Run artwork ingest.

    Args:
        tmp_dir:  Source folder containing incoming artwork files.
        apply:    When True, copy files and update the DB.
        get_conn: Callable returning a DB connection (injectable for tests).
    """
    if get_conn is None:
        sys.path.insert(0, str(PROJECT_ROOT / "src"))
        from utils.init_db import get_connection as get_conn  # type: ignore[assignment]

    if not tmp_dir.exists():
        print(f"ERROR: tmp dir not found: {tmp_dir}")
        sys.exit(1)
    if not ORIGINALS_DIR.exists():
        print(f"ERROR: originals dir not found: {ORIGINALS_DIR}")
        sys.exit(1)

    conn = get_conn()
    add_artwork_column_if_missing(conn)
    originals = load_originals(conn)

    if not originals:
        print("WARNING: no Tyler James Drake songs found in catalog_songs.")

    actions = plan_actions(tmp_dir, ORIGINALS_DIR, originals)

    # ── Report header ──────────────────────────────────────────────────────
    print(f"\n{'═'*72}")
    print(f"  Artwork Ingest — Tyler James Drake Originals")
    print(f"  Source : {tmp_dir}")
    print(f"  Dest   : {ORIGINALS_DIR}")
    print(f"  Mode   : {'★ APPLY' if apply else '○ DRY RUN (pass --apply to copy)'}")
    print(f"{'═'*72}\n")

    _ICONS = {
        "COPY_NEW":       "✓ NEW        ",
        "SKIP_EXACT_DUP": "✗ EXACT DUP  ",
        "SKIP_SEMANTIC":  "✗ SEMANTIC   ",
        "MANUAL_REVIEW":  "? REVIEW     ",
    }
    _ORDER = ["COPY_NEW", "SKIP_EXACT_DUP", "SKIP_SEMANTIC", "MANUAL_REVIEW"]
    by_action: dict[str, list[IngestAction]] = {k: [] for k in _ORDER}
    for a in actions:
        by_action.setdefault(a.action, []).append(a)

    counts: Counter = Counter()
    for action_key in _ORDER:
        rows = by_action.get(action_key, [])
        if not rows:
            continue
        icon = _ICONS.get(action_key, action_key)
        for a in rows:
            print(f"  {icon}  {a.src.name}")
            if a.dest_name and a.dest_name != a.src.name:
                print(f"               → {a.dest_name}")
            if a.reason:
                print(f"               ({a.reason})")
            counts[action_key] += 1
        print()

    print(f"{'─'*72}")
    print(f"  {'Files to copy':<28} {counts['COPY_NEW']}")
    print(f"  {'Needs manual review':<28} {counts['MANUAL_REVIEW']}")
    print(f"  {'Skipped exact dup':<28} {counts['SKIP_EXACT_DUP']}")
    print(f"  {'Skipped semantic dup':<28} {counts['SKIP_SEMANTIC']}")
    print()

    # ── MANUAL_REVIEW table ────────────────────────────────────────────────
    manual = by_action.get("MANUAL_REVIEW", [])
    if manual:
        print(f"{'═'*72}")
        print(f"  MANUAL REVIEW — {len(manual)} file(s) need human intervention")
        print(f"{'═'*72}")
        print(f"  {'File':<44} {'Reason'}")
        print(f"  {'─'*44} {'─'*24}")
        for a in manual:
            print(f"  {a.src.name:<44} {a.reason}")
        print()

    # ── Apply ──────────────────────────────────────────────────────────────
    if not apply:
        print("  Run with --apply to copy files and update the DB.")
        return

    # Remove scaffold .gitkeep after the first real file.
    gitkeep = ORIGINALS_DIR / ".gitkeep"

    copied = 0
    for a in actions:
        if a.action != "COPY_NEW":
            continue
        dest_path = ORIGINALS_DIR / a.dest_name
        if dest_path.exists():
            print(f"  SKIP (already exists): {a.dest_name}")
            continue
        shutil.copy2(a.src, dest_path)

        # Remove .gitkeep now that at least one real file is present.
        if gitkeep.exists():
            gitkeep.unlink()

        # Relative path from project root for DB storage.
        rel_path = str(dest_path.relative_to(PROJECT_ROOT))

        conn.execute(
            "UPDATE catalog_songs SET artwork_path = ?, updated_at = datetime('now')"
            " WHERE id = ?",
            (rel_path, a.song_id),
        )
        conn.commit()
        print(f"  COPIED: {a.dest_name}")

        # Embed cover art into source audio file when available.
        if a.source_file:
            audio_path = Path(a.source_file)
            result = embed_cover(audio_path, dest_path)
            print(f"         embed {audio_path.name}: {result}")

        copied += 1

    print(f"\n  Done — {copied} file(s) copied to originals/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Ingest artwork from tmp folder into catalog/artwork/originals/."
    )
    ap.add_argument(
        "--apply", action="store_true",
        help="Actually copy files and update the DB (default: dry run)",
    )
    ap.add_argument(
        "--tmp", type=Path, default=DEFAULT_TMP,
        help="Source tmp folder (default: C:\\Users\\tyler\\Desktop\\tmp)",
    )
    args = ap.parse_args()
    main(tmp_dir=args.tmp, apply=args.apply)
