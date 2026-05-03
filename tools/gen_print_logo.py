"""Generate ink-friendly print variant of the Hyperthreat logo.

Reads the silver-gradient source PNG and writes an inverted, white-flattened
version suitable for B&W laser printing on dark/silver brand artwork.

Usage:
    python tools/gen_print_logo.py
"""
from __future__ import annotations

from pathlib import Path
import sys

from PIL import Image, ImageOps


SRC = Path(__file__).resolve().parents[1] / "Brand" / "hyperthreat" / "hyperthreat-logo.png"
DST = Path(__file__).resolve().parents[1] / "Brand" / "hyperthreat" / "hyperthreat-logo-print.png"


def make_print_variant(src: Path, dst: Path) -> None:
    img = Image.open(src).convert("RGBA")

    # Flatten transparency onto white so inversion works predictably.
    white_bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
    flat = Image.alpha_composite(white_bg, img).convert("RGB")

    inverted = ImageOps.invert(flat)

    dst.parent.mkdir(parents=True, exist_ok=True)
    inverted.save(dst, format="PNG", optimize=True)
    print(f"wrote {dst} ({dst.stat().st_size} bytes)")


def main() -> int:
    if not SRC.exists():
        print(f"source PNG not found: {SRC}", file=sys.stderr)
        print("save the Hyperthreat logo there and re-run.", file=sys.stderr)
        return 1
    make_print_variant(SRC, DST)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
