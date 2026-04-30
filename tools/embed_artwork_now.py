#!/usr/bin/env python3
"""
One-shot: embed cover art into every MP3 in catalog/masters/Bloom/ and catalog/ep/.

Artwork lookup order per song folder:
  1. catalog/artwork/originals/{FolderName} - Tyler James Drake.jpg/.jpeg/.png/.webp
  2. Any .jpg/.jpeg/.png found directly inside the song folder itself (fallback)

Usage:
    C:\G\python.exe tools\embed_artwork_now.py           # dry run
    C:\G\python.exe tools\embed_artwork_now.py --apply   # embed
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT  = Path(__file__).resolve().parents[1]
ORIGINALS_DIR = PROJECT_ROOT / "catalog" / "artwork" / "originals"
ARTIST        = "Tyler James Drake"
IMAGE_EXTS    = {".jpg", ".jpeg", ".png", ".webp"}
AUDIO_EXTS    = {".mp3", ".flac", ".m4a", ".mp4"}

SONG_ROOTS = [
    PROJECT_ROOT / "catalog" / "masters" / "Bloom",
    PROJECT_ROOT / "catalog" / "ep",
]


def _find_artwork(song_folder: Path) -> Path | None:
    """Return artwork path for a song folder, or None if not found."""
    song_name = song_folder.name
    # 1. Canonical originals location
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        candidate = ORIGINALS_DIR / f"{song_name} - {ARTIST}{ext}"
        if candidate.exists():
            return candidate
    # 2. Fallback: any image directly in the song folder
    for f in sorted(song_folder.iterdir()):
        if f.is_file() and f.suffix.lower() in IMAGE_EXTS:
            return f
    return None


def _embed(audio_path: Path, image_path: Path) -> str:
    """Embed image_path as cover art into audio_path. Returns status string."""
    try:
        import mutagen  # noqa: F401
    except ImportError:
        return "SKIPPED_NO_MUTAGEN"

    ext = audio_path.suffix.lower()
    image_data = image_path.read_bytes()
    mime = "image/jpeg" if image_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"

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
            fmt = MP4Cover.FORMAT_JPEG if image_path.suffix.lower() in (".jpg", ".jpeg") else MP4Cover.FORMAT_PNG
            audio.tags["covr"] = [MP4Cover(image_data, imageformat=fmt)]
            audio.save()
            return "EMBEDDED"
        else:
            return "SKIPPED_FORMAT"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {exc}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    mode = "★ APPLY" if args.apply else "○ DRY RUN (pass --apply to embed)"
    print(f"\n{'═'*72}")
    print(f"  Cover Art Embed — Bloom + EPs")
    print(f"  Mode: {mode}")
    print(f"{'═'*72}\n")

    for root in SONG_ROOTS:
        if not root.exists():
            continue
        for song_folder in sorted(root.iterdir()):
            if not song_folder.is_dir():
                continue

            artwork = _find_artwork(song_folder)
            audio_files = sorted(
                f for f in song_folder.rglob("*")
                if f.is_file() and f.suffix.lower() in AUDIO_EXTS
            )

            if not audio_files:
                continue

            art_label = artwork.name if artwork else "NO ARTWORK FOUND"
            print(f"  [{song_folder.name}]  art: {art_label}")

            for mp3 in audio_files:
                if artwork is None:
                    print(f"    ✗ SKIP (no art)    {mp3.name}")
                    continue
                if args.apply:
                    status = _embed(mp3, artwork)
                    icon = "✓" if status == "EMBEDDED" else "✗"
                    print(f"    {icon} {status:<20} {mp3.name}")
                else:
                    print(f"    → would embed       {mp3.name}")
            print()

    print(f"{'═'*72}")
    if not args.apply:
        print("  Run with --apply to embed.\n")


if __name__ == "__main__":
    sys.exit(main())
