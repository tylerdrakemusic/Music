#!/usr/bin/env python3
"""Import originals lyrics — FR-20260502-import-originals-lyrics.

Extracts lyric text from Tyler James Drake originals DOCX/PDF/TXT sources
and writes them to the encrypted heartmusic.db `lyrics` table. Also moves
``People*.pdf`` from sheet_music/originals/ to sheet_music/covers/ during
``--apply``.

Sources (non-recursive):
  F:\\\u2764Music\\catalog\\sheet_music\\originals\\*.docx, *.pdf
  F:\\\u2764Music\\lyrics\\*.txt

Behavior:
  * Dry-run by default — prints the plan, makes no DB or filesystem writes.
  * ``--apply`` writes lyrics rows + relocates People*.pdf into covers/.
  * Idempotent: re-running ``--apply`` does not duplicate rows or error on
    already-moved files.
  * Fuzzy-matches the parsed title against ``tracks.title``; unmatched
    files are still imported with ``track_id = NULL``.
  * version_label is one of ``originals_docx`` / ``originals_pdf`` /
    ``originals_txt`` with a slug-suffix when more than one file maps to
    the same (track_id, base_label).

Usage:
  C:\\G\\python.exe tools/import_originals_lyrics.py            # dry-run
  C:\\G\\python.exe tools/import_originals_lyrics.py --apply    # write+move
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Default source / destination paths
# ---------------------------------------------------------------------------
_HEART_MUSIC_ROOT = Path("F:/") / "\u2764Music"
ORIGINALS_DIR = _HEART_MUSIC_ROOT / "catalog" / "sheet_music" / "originals"
COVERS_DIR    = _HEART_MUSIC_ROOT / "catalog" / "sheet_music" / "covers"
LYRICS_DIR    = _HEART_MUSIC_ROOT / "lyrics"

FUZZY_THRESHOLD = 0.72  # SequenceMatcher ratio cutoff for accepting a match


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PlannedLyric:
    """Single planned lyrics-row insert."""

    file_path: Path
    ext: str  # 'docx' | 'pdf' | 'txt'
    title_guess: str
    track_id: Optional[int]
    matched_title: Optional[str]
    version_label: str
    content: str
    skip_reason: Optional[str] = None  # 'already_imported' | 'extract_failed:*' | 'people_pdf'


@dataclass
class PlannedMove:
    """Single planned People*.pdf relocation."""

    src: Path
    dst: Path
    skip_reason: Optional[str] = None  # 'already_at_dst'


# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------

_NOISE_TOKENS = {
    "tyler", "james", "drake",
    "key", "lyricsonly", "lyrics", "rough", "tjd",
}


def parse_title_from_filename(path: Path) -> str:
    """Best-effort title from a sheet-music filename.

    Strips author tokens (``Tyler James Drake``) and decoration suffixes
    (``_Key_Bm``, ``_LyricsOnly``, ``- Rough <date>``).
    """
    stem = path.stem
    parts = re.split(r"_", stem)
    cleaned: list[str] = []
    for part in parts:
        low = part.strip().lower()
        if not low:
            continue
        if "tyler" in low and "james" in low and "drake" in low:
            break
        if low in _NOISE_TOKENS:
            break
        cleaned.append(part.strip())
    raw = " ".join(cleaned).strip() if cleaned else stem
    raw = re.sub(r"\s*-\s*Rough\b.*$", "", raw, flags=re.IGNORECASE)
    return raw.strip() or stem


def is_people_pdf(p: Path) -> bool:
    """True for ``People.pdf`` / ``People <variant>.pdf`` (case-insensitive)."""
    if p.suffix.lower() != ".pdf":
        return False
    return bool(re.match(r"^People(\s.+)?\.pdf$", p.name, re.IGNORECASE))


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


# ---------------------------------------------------------------------------
# Fuzzy track matching
# ---------------------------------------------------------------------------

def _normalize(title: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", title.lower())).strip()


def _compact(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", title.lower())


def fuzzy_match_track(
    title_guess: str, tracks: list[tuple[int, str]]
) -> tuple[Optional[int], Optional[str], float]:
    """Return ``(track_id, matched_title, ratio)`` or ``(None, None, ratio)``.

    Compares against each ``tracks(id, title)`` row using a normalized
    SequenceMatcher ratio. A compacted (alphanumeric-only) match counts as
    perfect; a substring overlap where the shorter side covers >=70% of the
    longer side is boosted to 0.9.
    """
    target = _normalize(title_guess)
    target_c = _compact(title_guess)
    if not target:
        return None, None, 0.0
    best: tuple[Optional[int], Optional[str], float] = (None, None, 0.0)
    for tid, t_title in tracks:
        cand = _normalize(t_title)
        cand_c = _compact(t_title)
        if not cand:
            continue
        if target_c and target_c == cand_c:
            return tid, t_title, 1.0
        ratio = SequenceMatcher(None, target, cand).ratio()
        if target in cand or cand in target:
            short, longer = sorted([target, cand], key=len)
            if short and len(short) / max(len(longer), 1) >= 0.70:
                ratio = max(ratio, 0.9)
        if ratio > best[2]:
            best = (tid, t_title, ratio)
    if best[2] >= FUZZY_THRESHOLD:
        return best
    return None, None, best[2]


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_docx(path: Path) -> str:
    import docx  # python-docx
    doc = docx.Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs).strip()


def extract_pdf(path: Path) -> str:
    import pypdf
    reader = pypdf.PdfReader(str(path))
    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return "\n\n".join(pages).strip()


def extract_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def extract(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    if ext == "docx":
        return extract_docx(path)
    if ext == "pdf":
        return extract_pdf(path)
    if ext == "txt":
        return extract_txt(path)
    raise ValueError(f"unsupported extension: {ext}")


# ---------------------------------------------------------------------------
# DB helpers (work with any DB-API connection — sqlcipher3 in prod, sqlite3 in tests)
# ---------------------------------------------------------------------------

def load_tracks(conn) -> list[tuple[int, str]]:
    rows = conn.execute("SELECT id, title FROM tracks").fetchall()
    return [(int(r[0]), str(r[1])) for r in rows]


def load_existing_lyrics(
    conn,
) -> tuple[set[str], dict[Optional[int], set[str]]]:
    rows = conn.execute(
        "SELECT track_id, version_label, file_path FROM lyrics"
    ).fetchall()
    paths: set[str] = set()
    labels_per_track: dict[Optional[int], set[str]] = {}
    for tid, label, fp in rows:
        if fp:
            paths.add(str(fp))
        key = int(tid) if tid is not None else None
        labels_per_track.setdefault(key, set()).add(str(label) if label else "")
    return paths, labels_per_track


def insert_lyric(conn, plan: PlannedLyric) -> None:
    conn.execute(
        "INSERT INTO lyrics (track_id, version_label, content, file_path) "
        "VALUES (?, ?, ?, ?)",
        (plan.track_id, plan.version_label, plan.content, str(plan.file_path)),
    )


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------

def list_originals_files(originals_dir: Path) -> list[Path]:
    if not originals_dir.exists():
        return []
    return sorted(
        p for p in originals_dir.iterdir()
        if p.is_file() and p.suffix.lower() in {".docx", ".pdf"}
    )


def list_lyrics_txt(lyrics_dir: Path) -> list[Path]:
    if not lyrics_dir.exists():
        return []
    return sorted(
        p for p in lyrics_dir.iterdir()
        if p.is_file() and p.suffix.lower() == ".txt"
    )


def plan_moves(originals_dir: Path, covers_dir: Path) -> list[PlannedMove]:
    moves: list[PlannedMove] = []
    if not originals_dir.exists():
        return moves
    for p in sorted(originals_dir.iterdir()):
        if p.is_file() and is_people_pdf(p):
            dst = covers_dir / p.name
            skip = "already_at_dst" if dst.exists() else None
            moves.append(PlannedMove(src=p, dst=dst, skip_reason=skip))
    # Also surface People*.pdf already at the destination so the audit log
    # stays informative on idempotent re-runs.
    if covers_dir.exists():
        for p in sorted(covers_dir.iterdir()):
            if p.is_file() and is_people_pdf(p):
                src = originals_dir / p.name
                if not src.exists():
                    if not any(m.dst == p for m in moves):
                        moves.append(
                            PlannedMove(src=src, dst=p, skip_reason="already_at_dst")
                        )
    return moves


def plan_lyrics(
    originals_dir: Path,
    lyrics_dir: Path,
    tracks: list[tuple[int, str]],
    existing_paths: set[str],
    existing_labels_per_track: dict[Optional[int], set[str]],
) -> list[PlannedLyric]:
    """Return the list of planned lyric inserts (idempotent w.r.t. file_path)."""
    plans: list[PlannedLyric] = []
    used: dict[Optional[int], set[str]] = {
        k: set(v) for k, v in existing_labels_per_track.items()
    }

    def reserve_label(track_id: Optional[int], ext: str, stem: str) -> str:
        base = f"originals_{ext}"
        labels = used.setdefault(track_id, set())
        if base not in labels:
            labels.add(base)
            return base
        candidate = f"{base}_{slug(stem)}"
        i = 2
        while candidate in labels:
            candidate = f"{base}_{slug(stem)}_{i}"
            i += 1
        labels.add(candidate)
        return candidate

    def _plan_one(p: Path, ext: str, title: str) -> None:
        tid, matched, _ratio = fuzzy_match_track(title, tracks)
        if str(p) in existing_paths:
            plans.append(
                PlannedLyric(
                    file_path=p, ext=ext, title_guess=title, track_id=tid,
                    matched_title=matched, version_label="", content="",
                    skip_reason="already_imported",
                )
            )
            return
        try:
            content = extract(p)
        except Exception as exc:  # extraction errors should not abort the run
            plans.append(
                PlannedLyric(
                    file_path=p, ext=ext, title_guess=title, track_id=tid,
                    matched_title=matched, version_label="", content="",
                    skip_reason=f"extract_failed:{exc.__class__.__name__}",
                )
            )
            return
        label = reserve_label(tid, ext, p.stem)
        plans.append(
            PlannedLyric(
                file_path=p, ext=ext, title_guess=title, track_id=tid,
                matched_title=matched, version_label=label, content=content,
            )
        )

    # originals/*.{docx,pdf}
    for p in list_originals_files(originals_dir):
        ext = p.suffix.lower().lstrip(".")
        if ext == "pdf" and is_people_pdf(p):
            plans.append(
                PlannedLyric(
                    file_path=p, ext=ext, title_guess="", track_id=None,
                    matched_title=None, version_label="", content="",
                    skip_reason="people_pdf",
                )
            )
            continue
        _plan_one(p, ext, parse_title_from_filename(p))

    # lyrics/*.txt
    for p in list_lyrics_txt(lyrics_dir):
        _plan_one(p, "txt", p.stem)

    return plans


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def apply_moves(moves: list[PlannedMove], covers_dir: Path) -> list[str]:
    """Execute People*.pdf relocations. Idempotent."""
    log: list[str] = []
    if any(m.skip_reason is None for m in moves):
        covers_dir.mkdir(parents=True, exist_ok=True)
    for m in moves:
        if m.skip_reason == "already_at_dst":
            if m.src.exists() and m.src != m.dst:
                m.src.unlink()
                log.append(f"DELETED duplicate {m.src} (already at {m.dst})")
            else:
                log.append(f"SKIP already_at_dst {m.dst}")
            continue
        m.dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(m.src), str(m.dst))
        log.append(f"MOVED {m.src} -> {m.dst}")
    return log


def apply_lyrics(conn, plans: list[PlannedLyric]) -> int:
    """Insert all non-skipped plans. Caller owns commit/close."""
    written = 0
    for p in plans:
        if p.skip_reason is None:
            insert_lyric(conn, p)
            written += 1
    return written


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def render_summary(plans: list[PlannedLyric], moves: list[PlannedMove]) -> str:
    imported = [p for p in plans if p.skip_reason is None]
    skipped  = [p for p in plans if p.skip_reason is not None]
    lines: list[str] = []
    lines.append("== Lyrics plan ==")
    lines.append(f"  to import : {len(imported)}")
    lines.append(f"  skipped   : {len(skipped)}")
    for p in imported:
        match = p.matched_title or "(unmatched)"
        lines.append(
            f"    [{p.ext}] {p.file_path.name} -> track={match} "
            f"label={p.version_label} ({len(p.content)} chars)"
        )
    for p in skipped:
        lines.append(f"    SKIP({p.skip_reason}) [{p.ext}] {p.file_path.name}")
    lines.append("== People*.pdf moves ==")
    if not moves:
        lines.append("  (none)")
    for m in moves:
        if m.skip_reason:
            lines.append(f"  SKIP({m.skip_reason}) {m.dst.name}")
        else:
            lines.append(f"  MOVE {m.src} -> {m.dst}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import originals lyrics into heartmusic.db (FR-20260502-import-originals-lyrics)."
    )
    parser.add_argument("--apply", action="store_true",
                        help="actually write to DB and move People*.pdf (default: dry-run)")
    parser.add_argument("--originals-dir", default=str(ORIGINALS_DIR))
    parser.add_argument("--covers-dir", default=str(COVERS_DIR))
    parser.add_argument("--lyrics-dir", default=str(LYRICS_DIR))
    parser.add_argument("--db-path", default=None,
                        help="override heartmusic.db location (default: utils.init_db.DB_PATH)")
    args = parser.parse_args(argv)

    originals_dir = Path(args.originals_dir)
    covers_dir    = Path(args.covers_dir)
    lyrics_dir    = Path(args.lyrics_dir)

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from utils import init_db as _init_db  # type: ignore
    if args.db_path:
        _init_db.DB_PATH = Path(args.db_path)
    conn = _init_db.get_connection()
    try:
        tracks = load_tracks(conn)
        existing_paths, existing_labels = load_existing_lyrics(conn)

        plans = plan_lyrics(
            originals_dir, lyrics_dir, tracks, existing_paths, existing_labels
        )
        moves = plan_moves(originals_dir, covers_dir)

        print(render_summary(plans, moves))

        if not args.apply:
            print("\n(dry-run) re-run with --apply to commit.")
            return 0

        written = apply_lyrics(conn, plans)
        conn.commit()
    finally:
        conn.close()

    move_log = apply_moves(moves, covers_dir)
    print(f"\nApplied: inserted {written} lyrics rows.")
    for line in move_log:
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
