"""Suno stem isolation via Demucs htdemucs_6s.

FR-20260516-suno-stem-isolation

Usage:
    python tools/stem_isolate.py <input_dir> [--output-dir <dir>] [--device <auto|cuda|cpu>]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Instrument detection
# ---------------------------------------------------------------------------

INSTRUMENT_MAP = {
    "drums": "drums",
    "bass": "bass",
    "guitar": "guitar",
    "vocals": "vocals",
    "vox": "vocals",
    "vocal": "vocals",
}

_NUMERIC_PREFIX_MAP = {
    "0": "drums",
    "9": "bass",
}


def detect_instrument(filename: str) -> str | None:
    """Return the Demucs stem name for a WAV filename, or None if unrecognised.

    Detection order:
    1. Numeric prefix (``0 ...`` → drums, ``9 ...`` → bass).
    2. Case-insensitive keyword scan of the full stem name.
    """
    stem = Path(filename).stem  # strip .wav
    # Numeric prefix check
    first_token = stem.split()[0] if stem.split() else ""
    if first_token in _NUMERIC_PREFIX_MAP:
        return _NUMERIC_PREFIX_MAP[first_token]

    lower = stem.lower()
    for keyword, instrument in INSTRUMENT_MAP.items():
        if keyword in lower:
            return instrument

    return None


# ---------------------------------------------------------------------------
# Demucs runner
# ---------------------------------------------------------------------------

def _demucs_output_stem(outdir: Path, track_stem: str, instrument: str) -> Path:
    """Return the expected Demucs output WAV path for htdemucs_6s."""
    return outdir / "htdemucs_6s" / track_stem / f"{instrument}.wav"


def _run_demucs(wav_path: Path, outdir: Path, device: str) -> bool:
    """Run Demucs on *wav_path*, writing output to *outdir*.

    Returns True on success, False on failure.
    Tries CUDA first when device is 'auto'; falls back to CPU on failure.
    """
    base_cmd = [
        sys.executable, "-m", "demucs",
        "--model", "htdemucs_6s",
        "--out", str(outdir),
        str(wav_path),
    ]

    devices_to_try: list[str]
    if device == "auto":
        devices_to_try = ["cuda", "cpu"]
    else:
        devices_to_try = [device]

    for dev in devices_to_try:
        cmd = base_cmd + ["--device", dev]
        print(f"  [demucs] Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=False)
        if result.returncode == 0:
            return True
        if dev == "cuda":
            print("  [demucs] CUDA failed, falling back to CPU…")
        else:
            print(f"  [demucs] Error: demucs exited with code {result.returncode}")
    return False


# ---------------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------------

def process_folder(input_dir: Path, output_dir: Path, device: str) -> None:
    """Process all WAV files in *input_dir*, writing isolated stems to *output_dir*.

    For each WAV:
    - Detect target instrument from filename.
    - Run Demucs htdemucs_6s.
    - Copy the matching stem to output_dir/<original_filename>.
    - Clean up the temporary Demucs output directory.
    """
    wav_files = sorted(input_dir.glob("*.wav"))
    if not wav_files:
        print(f"No .wav files found in {input_dir}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    demucs_tmp = input_dir / ".demucs_tmp"

    for wav_path in wav_files:
        instrument = detect_instrument(wav_path.name)
        if instrument is None:
            print(f"  [SKIP] {wav_path.name} — unrecognised instrument, skipping")
            continue

        print(f"\n[{wav_path.name}] → instrument: {instrument}")

        demucs_tmp.mkdir(parents=True, exist_ok=True)
        success = _run_demucs(wav_path, demucs_tmp, device)

        if not success:
            print(f"  [ERROR] Demucs failed for {wav_path.name}")
            _cleanup(demucs_tmp)
            continue

        stem_src = _demucs_output_stem(demucs_tmp, wav_path.stem, instrument)
        if not stem_src.exists():
            print(f"  [ERROR] Expected Demucs output not found: {stem_src}")
            _cleanup(demucs_tmp)
            continue

        dest = output_dir / wav_path.name
        shutil.copy2(stem_src, dest)
        print(f"  [OK] Isolated stem → {dest}")

        _cleanup(demucs_tmp)

    print(f"\nDone. Isolated stems in: {output_dir}")


def _cleanup(path: Path) -> None:
    """Remove *path* tree if it exists."""
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Isolate stems from Suno-exported WAVs using Demucs htdemucs_6s.",
    )
    parser.add_argument(
        "input_dir",
        type=Path,
        help="Folder containing Suno-exported WAV stem files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Where to write isolated WAVs (default: <input_dir>/isolated).",
    )
    parser.add_argument(
        "--device",
        choices=["auto", "cuda", "cpu"],
        default="auto",
        help="Compute device (default: auto — tries CUDA, falls back to CPU).",
    )
    return parser


def main() -> None:
    """Entry point for the stem isolation CLI."""
    parser = _build_parser()
    args = parser.parse_args()

    input_dir: Path = args.input_dir.resolve()
    if not input_dir.is_dir():
        parser.error(f"input_dir does not exist or is not a directory: {input_dir}")

    output_dir: Path = args.output_dir.resolve() if args.output_dir else input_dir / "isolated"

    print(f"Input  : {input_dir}")
    print(f"Output : {output_dir}")
    print(f"Device : {args.device}")

    process_folder(input_dir, output_dir, args.device)


if __name__ == "__main__":
    main()
