# DEPRECATED: superseded by tools/auto_tagger.py (FR-20260526-bpm-key-auto-tagger)
"""
bpm_verify.py — Multi-method BPM analysis using librosa for cross-verification.

Uses 4 independent methods:
  1. beat_track (default)       — standard onset-based beat tracking
  2. beat_track (tight prior)   — constrained around first estimate
  3. tempo from onset envelope  — onset strength aggregation
  4. tempogram median           — Fourier tempogram peaks

Picks median across methods. Flags if half/double-tempo is more plausible
(many beat trackers halve/double when song is ambiguous).
"""
from __future__ import annotations
import sys
from pathlib import Path

import librosa
import numpy as np

AUDIO_ROOT = Path(r"G:\Muzic")

AUDIO_MAP: dict[str, str] = {
    "I'm Alright":          "I'm Alright - Kenny Loggins.mp3",
    "Talk Me Into It":      "Talk Me Into It - Kevin Redmond.mp3",
    "Shaded Jade":          "Shaded Jade - Tamala Cameron and Gene Ngo.mp3",
    "Play That Funky Music": "Play That Funky Music - Wild Cherry.mp3",
    "On the Dark Side":     "On the Darkside - John Cafferty.mp3",
    "Celebrate":            "Celebration - Kool and The Gang.mp3",
}

# Ground-truth BPM from reputable sources for sanity check (0 = unknown)
KNOWN_BPM: dict[str, int] = {
    "I'm Alright":          0,   # will verify
    "Play That Funky Music": 109, # widely cited
    "On the Dark Side":     163,  # widely cited
    "Celebrate":            124,  # widely cited
    "Talk Me Into It":      0,
    "Shaded Jade":          0,
}


def analyze(path: Path, title: str) -> dict:
    print(f"\n  Loading {path.name}…", flush=True)
    y, sr = librosa.load(str(path), sr=22050, mono=True, duration=180.0)

    # Method 1: standard beat_track
    t1, _ = librosa.beat.beat_track(y=y, sr=sr)
    t1 = float(np.atleast_1d(t1)[0])

    # Method 2: beat_track with start_bpm hint from method 1
    t2, _ = librosa.beat.beat_track(y=y, sr=sr, start_bpm=t1)
    t2 = float(np.atleast_1d(t2)[0])

    # Method 3: onset strength tempo
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    t3_arr = librosa.feature.tempo(onset_envelope=onset_env, sr=sr)
    t3 = float(np.atleast_1d(t3_arr)[0])

    # Method 4: tempogram peaks (top-2 candidates)
    hop = 512
    tgram = librosa.feature.tempogram(onset_envelope=onset_env, sr=sr, hop_length=hop)
    # Sum across time → aggregate tempo strength
    tempo_weights = np.mean(tgram, axis=1)
    bpm_axis = librosa.tempo_frequencies(tgram.shape[0], sr=sr, hop_length=hop)
    # Valid range 60–220
    mask = (bpm_axis >= 60) & (bpm_axis <= 220)
    valid_weights = tempo_weights[mask]
    valid_bpm = bpm_axis[mask]
    # Top-2 candidates
    top2_idx = np.argsort(valid_weights)[-2:][::-1]
    t4_candidates = [float(valid_bpm[i]) for i in top2_idx]
    t4 = t4_candidates[0]

    all_methods = [t1, t2, t3, t4]
    median_bpm = float(np.median(all_methods))

    # Half/double-tempo check: if half of median_bpm is closer to a known value, flag it
    known = KNOWN_BPM.get(title, 0)
    half   = median_bpm / 2
    double = median_bpm * 2

    best = median_bpm
    note = ""
    if known:
        candidates = [
            (abs(median_bpm - known), median_bpm, "full"),
            (abs(half - known),        half,       "half-tempo of librosa"),
            (abs(double - known),      double,     "double-tempo of librosa"),
        ]
        candidates.sort(key=lambda x: x[0])
        if candidates[0][2] != "full":
            note = f" ← adjusted to {candidates[0][2]} to match known {known}"
            best = candidates[0][1]

    print(f"  Methods: {t1:.1f}, {t2:.1f}, {t3:.1f}, {t4:.1f}")
    print(f"  Median: {median_bpm:.1f}  →  Final: {round(best)}{note}")
    if known:
        print(f"  Known reference: {known} BPM  |  diff: {abs(best-known):.1f}")

    return {"title": title, "methods": all_methods, "median": median_bpm, "final": round(best)}


def main():
    results = []
    for title, filename in AUDIO_MAP.items():
        path = AUDIO_ROOT / filename
        if not path.exists():
            print(f"  MISSING: {path}")
            continue
        r = analyze(path, title)
        results.append(r)

    print("\n" + "="*55)
    print("FINAL BPM SUMMARY")
    print("="*55)
    for r in results:
        print(f"  {r['final']:3d}  {r['title']}")

    return results


if __name__ == "__main__":
    main()

