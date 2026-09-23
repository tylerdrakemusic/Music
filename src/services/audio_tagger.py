"""audio_tagger.py — BPM and musical key detection engine.

Returns a dict::

    {
        "bpm":        int | None,
        "key":        str | None,
        "bpm_source": str,   # "id3_tag" | "librosa" | "unknown"
        "key_source": str,   # "id3_tag" | "librosa_chroma" | "unknown"
    }

FR-20260526-bpm-key-auto-tagger
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Krumhansl-Schmuckler key profiles (Krumhansl & Schmuckler 1990)
# ---------------------------------------------------------------------------
_KK_MAJOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_KK_MINOR = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

#: Audio extensions this module handles.
AUDIO_EXTENSIONS: frozenset[str] = frozenset({".mp3", ".wav", ".flac", ".m4a", ".ogg"})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ks_correlate(chroma_mean: list[float]) -> str:
    """Krumhansl-Schmuckler key estimator.

    Args:
        chroma_mean: 12-element list of mean chroma values (C, C#, … B).

    Returns:
        Key string, e.g. ``"C major"`` or ``"A minor"``.
    """
    import numpy as np

    chroma = np.array(chroma_mean, dtype=float)
    best_r = -2.0
    best_key = "C major"
    for root in range(12):
        # Major
        profile = np.roll(np.array(_KK_MAJOR, dtype=float), root)
        r = float(np.corrcoef(chroma, profile)[0, 1])
        if r > best_r:
            best_r = r
            best_key = f"{_NOTE_NAMES[root]} major"
        # Minor
        profile = np.roll(np.array(_KK_MINOR, dtype=float), root)
        r = float(np.corrcoef(chroma, profile)[0, 1])
        if r > best_r:
            best_r = r
            best_key = f"{_NOTE_NAMES[root]} minor"
    return best_key


def _read_tags(path: Path, suffix: str, result: dict) -> None:
    """Populate *result* in-place with any BPM / key values found in metadata.

    Silently swallows all exceptions so callers can fall back to librosa.
    """
    try:
        if suffix == ".mp3":
            from mutagen.mp3 import MP3

            audio = MP3(str(path))
            tags = audio.tags
            if tags is not None:
                tbpm = tags.get("TBPM")
                if tbpm:
                    try:
                        val = int(float(str(tbpm)))
                        if val > 0:
                            result["bpm"] = val
                            result["bpm_source"] = "id3_tag"
                    except (ValueError, TypeError):
                        pass
                tkey = tags.get("TKEY")
                if tkey:
                    key_val = str(tkey).strip()
                    if key_val:
                        result["key"] = key_val
                        result["key_source"] = "id3_tag"

        elif suffix == ".flac":
            from mutagen.flac import FLAC

            audio = FLAC(str(path))
            bpm_tag = audio.get("bpm") or audio.get("BPM")
            if bpm_tag:
                try:
                    val = int(float(bpm_tag[0]))
                    if val > 0:
                        result["bpm"] = val
                        result["bpm_source"] = "id3_tag"
                except (ValueError, TypeError, IndexError):
                    pass
            key_tag = audio.get("key") or audio.get("KEY")
            if key_tag:
                key_val = key_tag[0].strip()
                if key_val:
                    result["key"] = key_val
                    result["key_source"] = "id3_tag"

        elif suffix == ".m4a":
            from mutagen.mp4 import MP4

            audio = MP4(str(path))
            tags = audio.tags
            if tags is not None:
                tmpo = tags.get("tmpo")
                if tmpo:
                    try:
                        val = int(tmpo[0])
                        if val > 0:
                            result["bpm"] = val
                            result["bpm_source"] = "id3_tag"
                    except (ValueError, TypeError, IndexError):
                        pass
                key_tag = tags.get("----:com.apple.iTunes:KEY")
                if key_tag:
                    try:
                        key_val = key_tag[0].decode("utf-8").strip()
                        if key_val:
                            result["key"] = key_val
                            result["key_source"] = "id3_tag"
                    except (AttributeError, UnicodeDecodeError):
                        pass

    except Exception:
        pass  # Corrupt or missing metadata — caller falls back to librosa.


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect(path: str | Path) -> dict:
    """Detect BPM and musical key for an audio file.

    Strategy:
    1. Read ID3 / FLAC / M4A metadata tags for both BPM and key.
    2. For any still-missing value, load audio once with librosa and run:
       - ``beat_track`` for BPM
       - Chroma CQT + Krumhansl-Schmuckler estimator for key

    Args:
        path: Path to an audio file (.mp3, .wav, .flac, .m4a, .ogg).

    Returns:
        ``{"bpm": int|None, "key": str|None,
           "bpm_source": str, "key_source": str}``
    """
    path = Path(path)
    suffix = path.suffix.lower()

    result: dict = {
        "bpm": None,
        "key": None,
        "bpm_source": "unknown",
        "key_source": "unknown",
    }

    # Step 1 — metadata tags.
    _read_tags(path, suffix, result)

    # Step 2 — librosa for any still-missing value (single audio load).
    if result["bpm"] is None or result["key"] is None:
        try:
            import librosa
            import numpy as np

            y, sr = librosa.load(str(path), sr=22050, mono=True, duration=180.0)

            if result["bpm"] is None:
                tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
                bpm_val = int(round(float(np.atleast_1d(tempo)[0])))
                if bpm_val > 0:
                    result["bpm"] = bpm_val
                    result["bpm_source"] = "librosa"

            if result["key"] is None:
                chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
                chroma_mean = np.mean(chroma, axis=1).tolist()
                result["key"] = _ks_correlate(chroma_mean)
                result["key_source"] = "librosa_chroma"

        except Exception:
            pass  # Leave bpm/key as None with source "unknown".

    return result


def check_integrity(path: str | Path) -> bool:
    """Verify an audio file is readable by both librosa and mutagen.

    Loads the first 5 seconds with librosa and opens the file with mutagen.

    Returns:
        ``True`` if both succeed, ``False`` if either raises.
    """
    try:
        import librosa
        import mutagen

        librosa.load(str(path), sr=22050, mono=True, duration=5.0)
        mutagen.File(str(path))
        return True
    except Exception:
        return False
