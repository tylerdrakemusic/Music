"""Fundamental-frequency detection for the live guitar tuner."""

from __future__ import annotations

from functools import lru_cache
import math
from typing import Sequence, TypedDict

import librosa
import numpy as np

SAMPLE_RATE = 44100
FRAME_SIZE = 8192
MIN_FREQUENCY = 75.0
MAX_FREQUENCY = 1400.0
MIN_PERIODICITY = 0.9
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


class PitchEstimate(TypedDict):
    note: str
    octave: int
    frequency_hz: float
    cents: int
    feedback: str


@lru_cache(maxsize=1)
def prepare_pitch_detector() -> None:
    """Warm YIN's first-call setup before the audio stream starts."""
    sample_indexes = np.arange(FRAME_SIZE, dtype=np.float32)
    warmup = np.sin(2 * np.pi * 440.0 * sample_indexes / SAMPLE_RATE)
    librosa.yin(
        warmup,
        fmin=MIN_FREQUENCY,
        fmax=MAX_FREQUENCY,
        sr=SAMPLE_RATE,
        frame_length=FRAME_SIZE,
        hop_length=FRAME_SIZE,
        center=False,
    )


def detect_pitch(samples: Sequence[float]) -> PitchEstimate | None:
    """Estimate one confident guitar fundamental from a single audio frame."""
    frame = np.asarray(samples, dtype=np.float32)
    if frame.ndim != 1 or frame.size != FRAME_SIZE:
        return None

    frame = frame - np.mean(frame)
    energy = float(np.dot(frame, frame))
    if not math.isfinite(energy) or energy <= 1e-8:
        return None

    estimates = librosa.yin(
        frame,
        fmin=MIN_FREQUENCY,
        fmax=MAX_FREQUENCY,
        sr=SAMPLE_RATE,
        frame_length=FRAME_SIZE,
        hop_length=FRAME_SIZE,
        center=False,
    )
    frequency = float(estimates[0])
    if not math.isfinite(frequency) or frequency <= 0:
        return None

    lag = round(SAMPLE_RATE / frequency)
    if lag < 2 or lag >= FRAME_SIZE:
        return None
    leading = frame[:-lag]
    delayed = frame[lag:]
    denominator = math.sqrt(float(np.dot(leading, leading)) * float(np.dot(delayed, delayed)))
    if denominator <= 0:
        return None
    periodicity = float(np.dot(leading, delayed)) / denominator
    if not math.isfinite(periodicity) or periodicity < MIN_PERIODICITY:
        return None

    midi_note = round(69 + 12 * math.log2(frequency / 440.0))
    if midi_note < 40 or midi_note > 88:
        return None
    target_frequency = 440.0 * 2 ** ((midi_note - 69) / 12)
    cents = round(1200 * math.log2(frequency / target_frequency))
    feedback = "flat" if cents < -5 else "sharp" if cents > 5 else "in_tune"
    return {
        "note": NOTE_NAMES[midi_note % 12],
        "octave": midi_note // 12 - 1,
        "frequency_hz": frequency,
        "cents": cents,
        "feedback": feedback,
    }
