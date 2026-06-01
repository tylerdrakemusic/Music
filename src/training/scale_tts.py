"""
❤Music — ElevenLabs TTS cache for guitar scale instructor phrases.
FR-20260517-guitar-trainer-scale-exercises

Usage:
    from training.scale_tts import get_instructor_audio
    audio_path = get_instructor_audio("Start on the 3rd fret of the A string", cache_dir)
    # Returns Path to .mp3 on success, None on any failure (graceful degradation).
"""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # ElevenLabs Rachel (stable, multilingual)
_API_BASE = "https://api.elevenlabs.io/v1"


def _resolve_cache_dir(cache_dir: Path) -> Path:
    """Resolve and validate the cache dir is within the project output/tts tree."""
    resolved = cache_dir.resolve()
    # Walk up to find project root (contains src/ dir)
    candidate = resolved
    for _ in range(6):
        if (candidate / "src").is_dir():
            break
        candidate = candidate.parent
    project_root = candidate
    tts_root = (project_root / "output" / "tts").resolve()
    if not resolved.is_relative_to(tts_root):
        raise ValueError(
            f"cache_dir {resolved} is outside allowed output/tts/ tree ({tts_root})"
        )
    return resolved


def _normalize_phrase(phrase: str) -> str:
    """Expand music notation so TTS pronounces it correctly.

    '#'      → ' sharp'  (ElevenLabs reads bare '#' as 'hash')
    'A major'→ 'Ay major' (ElevenLabs soft-pronounces the letter A otherwise)
    'A shape'→ 'Ay shape' (ElevenLabs soft-pronounces the letter A otherwise)
    """
    phrase = phrase.replace("#", " sharp")
    phrase = phrase.replace("A major", "Ay major")
    phrase = phrase.replace("A shape", "Ay shape")
    return phrase


def get_instructor_audio(phrase: str, cache_dir: Path) -> Path | None:
    """Return path to cached MP3 for *phrase*, generating it via ElevenLabs if needed.

    Returns None on any failure so callers degrade gracefully (no voice, page still works).
    Never raises.
    """
    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        log.warning("ELEVENLABS_API_KEY not set — instructor audio unavailable")
        return None

    try:
        safe_cache = _resolve_cache_dir(cache_dir)
    except ValueError as exc:
        log.warning("scale_tts: invalid cache_dir — %s", exc)
        return None

    safe_cache.mkdir(parents=True, exist_ok=True)

    # Normalize before cache key + TTS so stale 'hash' audio is bypassed
    tts_text = _normalize_phrase(phrase)

    # Cache key: SHA1 of (voice_id + normalized text) so notation changes invalidate
    _cache_input = f"{_VOICE_ID}:{tts_text}".encode("utf-8")
    cache_key = hashlib.sha1(_cache_input, usedforsecurity=False).hexdigest()  # nosec B324
    cache_path = safe_cache / f"{cache_key}.mp3"

    if cache_path.exists():
        return cache_path

    # Generate via ElevenLabs
    try:
        import urllib.request
        import json as _json

        url = f"{_API_BASE}/text-to-speech/{_VOICE_ID}"
        payload = _json.dumps({
            "text": tts_text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310  # nosec B310
            audio_bytes = resp.read()

        cache_path.write_bytes(audio_bytes)
        log.info("scale_tts: generated and cached instructor audio → %s", cache_path.name)
        return cache_path

    except Exception as exc:  # noqa: BLE001
        log.warning("scale_tts: ElevenLabs request failed — %s", exc)
        return None
