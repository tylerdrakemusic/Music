#!/usr/bin/env python3
"""
Ingest sheet music from a tmp drop folder into catalog/sheet_music/covers/.

Naming convention used in covers/:
    {Title} - {Artist} ({variant}).{ext}

Duplicate handling:
  SKIP_TMP_DUP     — identical hash seen in another tmp file (keep best; skip rest)
  SKIP_EXACT_DUP   — SHA-256 matches an existing cover (already there under another name)
  SKIP_SEMANTIC    — same song + same extension already in covers (different source/name)
  COPY_NEW_FORMAT  — same song, different extension (additive — e.g., DOCX chords + PDF score)
  COPY_NEW         — no existing match; copy with canonical name
  MANUAL_REVIEW    — could not parse artist/title; human intervention needed

Usage:
    python tools/ingest_sheet_music.py            # dry run (default)
    python tools/ingest_sheet_music.py --apply    # copy files to covers/
    python tools/ingest_sheet_music.py --tmp C:\\path\\to\\other\\folder
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

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
COVERS_DIR   = PROJECT_ROOT / "catalog" / "sheet_music" / "covers"
DEFAULT_TMP  = Path(r"C:\Users\tyler\Desktop\tmp")

# ---------------------------------------------------------------------------
# Known multi-word artists that appear as hyphenated prefixes in legacy filenames.
# Maps lowercase-hyphenated-prefix → canonical name.
# ---------------------------------------------------------------------------
_ARTIST_TABLE: dict[str, str] = {
    "alabama-shakes":       "Alabama Shakes",
    "b-b-king":             "B.B. King",
    "b.b.-king":            "B.B. King",
    "bon-jovi":             "Bon Jovi",
    "bonnie-raitt":         "Bonnie Raitt",
    "carly-simon":          "Carly Simon",
    "carole-king":          "Carole King",
    "deep-purple":          "Deep Purple",
    "doobie-brothers":      "Doobie Brothers",
    "eric-clapton":         "Eric Clapton",
    "fleetwood-mac":        "Fleetwood Mac",
    "gerry-rafferty":       "Gerry Rafferty",
    "gloria-gaynor":        "Gloria Gaynor",
    "golden-earring":       "Golden Earring",
    "hall-oates":           "Hall & Oates",
    "huey-lewis-the-news":  "Huey Lewis & The News",
    "janis-joplin":         "Janis Joplin",
    "jim-mann":             "Jim Mann",
    "joe-cocker":           "Joe Cocker",
    "joe-walsh":            "Joe Walsh",
    "john-cafferty":        "John Cafferty",
    "kenny-loggins":        "Kenny Loggins",
    "kenny-wayne-shepherd": "Kenny Wayne Shepherd",
    "nancy-sinatra":        "Nancy Sinatra",
    "natalie-merchant":     "Natalie Merchant",
    "reo-speedwagon":       "REO Speedwagon",
    "shania-twain":         "Shania Twain",
    "steely-dan":           "Steely Dan",
    "stevie-nicks":         "Stevie Nicks",
    "the-b-52s":            "The B-52s",
    "the-black-keys":       "The Black Keys",
    "the-romantics":        "The Romantics",
    "tina-turner":          "Tina Turner",
    "tom-petty":            "Tom Petty",
    "tyler-james-drake":    "Tyler James Drake",
    "tyler-drake":          "Tyler James Drake",
    "van-halen":            "Van Halen",
    "lynyrd-skynyrd":       "Lynyrd Skynyrd",
    "chris-isaak":          "Chris Isaak",
    "tg":                   "TG",   # band abbreviation in Copper Creek setlists
}

# Single-word artists that appear in the tmp hyphenated filenames.
_SINGLE_WORD_ARTISTS = {
    "blondie", "boston", "chicago", "journey", "kansas",
    "paramore", "sade", "santana", "styx", "supertramp",
}

# Music key pattern at end of title segment: "-in-Xb" / "-in-X#" / "-in-Xm"
_KEY_SUFFIX_RE = re.compile(
    r"-in-([A-Ga-g][b#]?m?)$", re.IGNORECASE
)

# Known source/site prefixes to strip before parsing artist/title
_SOURCE_PREFIXES = {"harmonytabs"}

# Trailing numeric-download suffix: " (1)", " (2)", etc.
_NUM_SUFFIX_RE = re.compile(r"\s*\(\d+\)\s*$")

# Track-number prefix: "1.02-", "2-", etc.
_TRACK_PREFIX_RE = re.compile(r"^\d+[\.\d]*-")

# Parenthetical variant at end of stem: " (Variant Text)"
_VARIANT_RE = re.compile(r"\s*\(([^)]+)\)\s*$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _smart_title(s: str) -> str:
    """Title-case a string keeping short function words lowercase (after position 0)."""
    _LOWER = {
        "a", "an", "the", "of", "in", "on", "at", "to", "for",
        "and", "or", "but", "nor", "with", "from", "by", "as",
    }
    words = s.split()
    out = []
    for i, w in enumerate(words):
        if i > 0 and w.lower() in _LOWER:
            out.append(w.lower())
        else:
            # Preserve ALL-CAPS acronyms (e.g., "REO", "BB")
            out.append(w if w.isupper() and len(w) > 1 else w.capitalize())
    return " ".join(out)


def _canonical_name(title: str, artist: str, variant: str, ext: str) -> str:
    name = f"{title} - {artist}" if artist else title
    if variant:
        name += f" ({variant})"
    return name + ext


# ---------------------------------------------------------------------------
# Filename parsers
# ---------------------------------------------------------------------------

def _parse_stem(stem: str) -> tuple[str, str, str]:
    """
    Parse a filename stem into (title, artist, variant).
    Returns ("", "", "") on failure → triggers MANUAL_REVIEW.
    """
    # 1. Strip browser-added numeric suffix: " (4)" → ""
    stem = _NUM_SUFFIX_RE.sub("", stem).strip()

    # 2. Strip track-number prefix: "1.02-" → ""
    stem = _TRACK_PREFIX_RE.sub("", stem).strip("-").strip()

    # 3. Extract explicit parenthetical variant BEFORE further parsing
    variant = ""
    vm = _VARIANT_RE.search(stem)
    if vm:
        variant = vm.group(1).strip()
        stem = stem[: vm.start()].strip()

    # --- Strategy A: underscore-delimited "Title_Artist_Key_X" ---
    if "_" in stem:
        parts = [p.strip() for p in stem.split("_")]
        # Expect at least title_artist; optional Key_X at end
        if len(parts) >= 2:
            title_raw  = parts[0].replace("-", " ")
            artist_raw = parts[1].replace("-", " ")
            key_variant = ""
            if len(parts) >= 4 and parts[2].lower() == "key":
                key_variant = f"Key {parts[3]}"
            elif len(parts) == 3 and re.match(r"^key$", parts[2], re.I):
                key_variant = f"Key {parts[3]}" if len(parts) > 3 else ""
            final_variant = key_variant or variant
            title  = _smart_title(title_raw)
            artist = _resolve_artist(artist_raw.replace(" ", "-").lower()) or _smart_title(artist_raw)
            return title, artist, final_variant

    # --- Strategy B: "Title - Artist" (space-dash-space) ---
    if " - " in stem:
        title_part, artist_part = stem.split(" - ", 1)
        title  = title_part.strip()
        artist = artist_part.strip()
        # artist_part might itself be hyphenated (legacy); normalise
        artist = _resolve_artist(artist.replace(" ", "-").lower()) or artist
        return title, artist, variant

    # --- Strategy C: all-hyphen "Artist-Name-Song-Title" ---
    if "-" in stem and " " not in stem:
        # Strip known source prefixes (e.g. "HarmonyTabs-Journey-..."
        lower_stem = stem.lower()
        for src_pfx in _SOURCE_PREFIXES:
            if lower_stem.startswith(src_pfx + "-"):
                stem = stem[len(src_pfx) + 1:]
                break

        # Try key suffix extraction first: "...-in-Bm" → variant "in Bm"
        key_m = _KEY_SUFFIX_RE.search(stem)
        key_str = ""
        if key_m:
            key_str = f"in {key_m.group(1)}"
            stem = stem[: key_m.start()]

        # Try longest artist prefix match (4 → 3 → 2 → 1 words)
        tokens = stem.split("-")
        for n in range(min(4, len(tokens) - 1), 0, -1):
            prefix = "-".join(tokens[:n]).lower()
            artist_canon = _resolve_artist(prefix)
            if artist_canon:
                title_raw = " ".join(tokens[n:]).replace("-", " ")
                title = _smart_title(title_raw)
                final_variant = key_str or variant
                return title, artist_canon, final_variant

    # --- Strategy D: single token, no artist info ---
    # e.g. "Tequila (4)" after cleanup → just return title with empty artist
    if stem:
        return _smart_title(stem.replace("-", " ")), "", variant

    return "", "", ""


def _resolve_artist(hyphen_lower: str) -> str:
    """Return canonical artist name from hyphenated lowercase key, or ''."""
    if hyphen_lower in _ARTIST_TABLE:
        return _ARTIST_TABLE[hyphen_lower]
    # Single-word check
    clean = hyphen_lower.replace("-", "").strip()
    if clean in _SINGLE_WORD_ARTISTS:
        return _smart_title(clean)
    return ""


# ---------------------------------------------------------------------------
# Covers index
# ---------------------------------------------------------------------------

def _covers_key(stem: str) -> str:
    """Normalised lookup key: strip variant, lowercase, strip punctuation."""
    s = _VARIANT_RE.sub("", stem).strip()
    s = re.sub(r"[^\w\s]", "", s).lower().strip()
    return re.sub(r"\s+", " ", s)


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

SEMANTIC_THRESHOLD = 0.80  # fuzzy match score to treat as same song


def main(tmp_dir: Path = DEFAULT_TMP, apply: bool = False) -> None:
    if not tmp_dir.exists():
        print(f"ERROR: tmp dir not found: {tmp_dir}")
        sys.exit(1)
    if not COVERS_DIR.exists():
        print(f"ERROR: covers dir not found: {COVERS_DIR}")
        sys.exit(1)

    # ── Index existing covers ─────────────────────────────────────────────
    covers_by_hash: dict[str, Path] = {}
    covers_by_key:  dict[str, Path] = {}   # normalised_key → path
    for f in sorted(COVERS_DIR.iterdir()):
        if f.is_file():
            covers_by_hash[_sha256(f)] = f
            key = _covers_key(f.stem)
            covers_by_key[key] = f

    # ── Hash tmp files; group exact dupes together ────────────────────────
    tmp_by_hash: dict[str, list[Path]] = {}
    for f in sorted(tmp_dir.iterdir()):
        if f.is_file():
            tmp_by_hash.setdefault(_sha256(f), []).append(f)

    # ── Decide action for each group ──────────────────────────────────────
    # action, src, dest_name, reason
    actions: list[tuple[str, Path, str, str]] = []

    for h, group in sorted(tmp_by_hash.items(), key=lambda x: x[1][0].name):
        # Pick best representative: PDF > DOCX > JPG > PNG; then largest
        _EXT_RANK = {".pdf": 0, ".docx": 1, ".jpg": 2, ".png": 3}
        group_sorted = sorted(
            group, key=lambda p: (_EXT_RANK.get(p.suffix.lower(), 99), -p.stat().st_size)
        )
        rep   = group_sorted[0]
        dupes = group_sorted[1:]

        for d in dupes:
            actions.append(("SKIP_TMP_DUP", d, "", f"exact dup of → {rep.name}"))

        # Exact match against existing cover
        if h in covers_by_hash:
            actions.append(("SKIP_EXACT_DUP", rep, "", f"hash match → {covers_by_hash[h].name}"))
            continue

        # Parse filename
        title, artist, variant = _parse_stem(rep.stem)
        ext = rep.suffix.lower()

        if not title:
            actions.append(("MANUAL_REVIEW", rep, rep.name, "could not parse title from filename"))
            continue

        dest_name = _canonical_name(title, artist, variant, ext)

        # Semantic duplicate check
        query_key = _covers_key(f"{title} {artist}".strip())
        best_score, best_key = 0.0, ""
        for ck in covers_by_key:
            s = _similarity(query_key, ck)
            if s > best_score:
                best_score, best_key = s, ck

        if best_score >= SEMANTIC_THRESHOLD:
            existing = covers_by_key[best_key]
            if existing.suffix.lower() == ext:
                actions.append((
                    "SKIP_SEMANTIC",
                    rep, dest_name,
                    f"fuzzy {best_score:.2f} → {existing.name}",
                ))
                continue
            else:
                # Different format — additive value
                actions.append((
                    "COPY_NEW_FORMAT",
                    rep, dest_name,
                    f"new format vs {existing.name} ({best_score:.2f})",
                ))
                continue

        # Check if dest name already exists
        if (COVERS_DIR / dest_name).exists():
            actions.append(("SKIP_NAME_EXISTS", rep, dest_name, "dest already exists"))
            continue

        actions.append(("COPY_NEW", rep, dest_name, ""))

    # ── Print report ──────────────────────────────────────────────────────
    _ICONS = {
        "COPY_NEW":         "✓ NEW        ",
        "COPY_NEW_FORMAT":  "✓ NEW FORMAT ",
        "MANUAL_REVIEW":    "? REVIEW     ",
        "SKIP_EXACT_DUP":   "✗ EXACT DUP  ",
        "SKIP_SEMANTIC":    "✗ SEMANTIC   ",
        "SKIP_TMP_DUP":     "✗ TMP DUP    ",
        "SKIP_NAME_EXISTS": "✗ NAME EXISTS",
    }

    print(f"\n{'═'*72}")
    print(f"  Sheet Music Ingest")
    print(f"  Source : {tmp_dir}")
    print(f"  Dest   : {COVERS_DIR}")
    print(f"  Mode   : {'★ APPLY' if apply else '○ DRY RUN (pass --apply to copy)'}")
    print(f"{'═'*72}\n")

    # Group output by action for readability
    _ORDER = ["COPY_NEW", "COPY_NEW_FORMAT", "MANUAL_REVIEW",
              "SKIP_SEMANTIC", "SKIP_EXACT_DUP", "SKIP_TMP_DUP", "SKIP_NAME_EXISTS"]
    by_action: dict[str, list] = {k: [] for k in _ORDER}
    for row in actions:
        by_action.setdefault(row[0], []).append(row)

    counts: Counter = Counter()
    for action_key in _ORDER:
        rows = by_action.get(action_key, [])
        if not rows:
            continue
        icon = _ICONS.get(action_key, action_key)
        for action, src, dest, reason in rows:
            print(f"  {icon}  {src.name}")
            if dest and dest != src.name:
                print(f"               → {dest}")
            if reason:
                print(f"               ({reason})")
            counts[action] += 1
        print()

    copy_total = counts["COPY_NEW"] + counts["COPY_NEW_FORMAT"]
    print(f"{'─'*72}")
    print(f"  {'Files to copy':<28} {copy_total}")
    print(f"  {'New (no existing match)':<28} {counts['COPY_NEW']}")
    print(f"  {'New format (additive)':<28} {counts['COPY_NEW_FORMAT']}")
    print(f"  {'Needs manual review':<28} {counts['MANUAL_REVIEW']}")
    print(f"  {'Skipped exact dup in covers':<28} {counts['SKIP_EXACT_DUP']}")
    print(f"  {'Skipped semantic dup':<28} {counts['SKIP_SEMANTIC']}")
    print(f"  {'Skipped dup within tmp':<28} {counts['SKIP_TMP_DUP']}")
    print()

    # ── Apply ─────────────────────────────────────────────────────────────
    if apply:
        copied = 0
        for action, src, dest, _ in actions:
            if action in ("COPY_NEW", "COPY_NEW_FORMAT"):
                dest_path = COVERS_DIR / dest
                if dest_path.exists():
                    print(f"  SKIP (already exists): {dest}")
                    continue
                shutil.copy2(src, dest_path)
                print(f"  COPIED: {dest}")
                copied += 1
        print(f"\n  Done — {copied} file(s) copied to covers/")
    else:
        print("  Run with --apply to copy files to covers/.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Ingest sheet music from tmp folder.")
    ap.add_argument("--apply", action="store_true", help="Actually copy files (default: dry run)")
    ap.add_argument("--tmp", type=Path, default=DEFAULT_TMP, help="Source tmp folder")
    args = ap.parse_args()
    main(tmp_dir=args.tmp, apply=args.apply)
