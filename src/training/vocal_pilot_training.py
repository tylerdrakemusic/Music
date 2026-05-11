from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import wave
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from mutagen import File as MutagenFile


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "output" / "vocal_pilots"
DEFAULT_SAMPLE_RATE = 44_100
DEFAULT_SINGLE_KEYS = ["C", "D", "E", "F", "G", "A", "B"]
DEFAULT_COMMUTE_KEYS = ["C", "D", "E", "F", "G"]

SCALE_INTERVALS: dict[str, tuple[int, ...]] = {
    "major": (0, 2, 4, 5, 7, 9, 11, 12),
    "natural_minor": (0, 2, 3, 5, 7, 8, 10, 12),
    "harmonic_minor": (0, 2, 3, 5, 7, 8, 11, 12),
}

NOTE_TO_SEMITONE: dict[str, int] = {
    "C": 0,
    "C#": 1,
    "DB": 1,
    "D": 2,
    "D#": 3,
    "EB": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "GB": 6,
    "G": 7,
    "G#": 8,
    "AB": 8,
    "A": 9,
    "A#": 10,
    "BB": 10,
    "B": 11,
}
SEMITONE_TO_NAME = {
    0: "C",
    1: "C#",
    2: "D",
    3: "Eb",
    4: "E",
    5: "F",
    6: "F#",
    7: "G",
    8: "Ab",
    9: "A",
    10: "Bb",
    11: "B",
}


@dataclass(frozen=True)
class VocalRange:
    """Inclusive MIDI range used when selecting drill register."""

    low_midi: int = 48
    high_midi: int = 69


@dataclass(frozen=True)
class ExerciseTemplate:
    """Scale exercise template for one drill family."""

    name: str
    scale_type: str
    bpm: int = 92
    beats_per_note: float = 1.0
    cycles: int = 2


@dataclass(frozen=True)
class TrackRequest:
    """Render request payload passed to the audio renderer seam."""

    kind: str
    template_name: str
    scale_type: str
    key_signature: str
    bpm: int
    beats_per_note: float
    note_midis: tuple[int, ...]
    sample_rate: int


@dataclass(frozen=True)
class RenderResult:
    """Audio metadata emitted by a renderer."""

    duration_seconds: float
    sample_rate: int
    channels: int


@dataclass(frozen=True)
class ManifestEntry:
    """Persisted index row for a generated vocal pilot track."""

    kind: str
    template_name: str
    scale_type: str
    key_signature: str
    relative_path: str
    sha256: str
    duration_seconds: float
    sample_rate: int
    channels: int


class VocalPilotRenderer(Protocol):
    """Renderer seam that can be backed by local synthesis or external services."""

    def render(self, request: TrackRequest, output_path: Path) -> RenderResult:
        """Render one track request to output_path."""


class SineWaveRenderer:
    """Deterministic local renderer that writes PCM WAV drills."""

    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE) -> None:
        self._sample_rate = sample_rate

    def render(self, request: TrackRequest, output_path: Path) -> RenderResult:
        seconds_per_note = (60.0 / request.bpm) * request.beats_per_note
        pcm = bytearray()
        silence_between_notes = int(self._sample_rate * 0.04)

        for midi_note in request.note_midis:
            if midi_note < 0:
                pcm.extend(_silence_frames(int(seconds_per_note * self._sample_rate)))
                continue
            tone = _synthesize_sine_note(
                midi_to_frequency(midi_note),
                duration_seconds=seconds_per_note,
                sample_rate=self._sample_rate,
            )
            pcm.extend(tone)
            pcm.extend(_silence_frames(silence_between_notes))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(self._sample_rate)
            handle.writeframes(bytes(pcm))

        duration_seconds = len(pcm) / (self._sample_rate * 2)
        return RenderResult(
            duration_seconds=round(duration_seconds, 3),
            sample_rate=self._sample_rate,
            channels=1,
        )


class VocalPilotGenerator:
    """Builds single-key and commute vocal drill assets and manifest entries."""

    def __init__(
        self,
        templates: dict[str, ExerciseTemplate],
        renderer: VocalPilotRenderer,
        output_root: Path = DEFAULT_OUTPUT_ROOT,
    ) -> None:
        self.templates = templates
        self.renderer = renderer
        self.output_root = output_root
        self.single_root = self.output_root / "single_key"
        self.commute_root = self.output_root / "commute"
        self.manifest_path = self.output_root / "manifests" / "index.json"

    def generate_single_key_tracks(self, keys: list[str], template_names: list[str]) -> list[ManifestEntry]:
        """Generate one track per key and template."""
        entries: list[ManifestEntry] = []
        for template_name in template_names:
            template = self.templates[template_name]
            for key in keys:
                normalized_key = normalize_key_signature(key)
                note_midis = _build_scale_drill_notes(normalized_key, template)
                file_name = f"{template.scale_type}__{slug_key(normalized_key)}.wav"
                output_path = self.single_root / template.scale_type / file_name
                request = TrackRequest(
                    kind="single_key",
                    template_name=template.name,
                    scale_type=template.scale_type,
                    key_signature=normalized_key,
                    bpm=template.bpm,
                    beats_per_note=template.beats_per_note,
                    note_midis=note_midis,
                    sample_rate=DEFAULT_SAMPLE_RATE,
                )
                result = self.renderer.render(request, output_path)
                entries.append(
                    ManifestEntry(
                        kind="single_key",
                        template_name=template.name,
                        scale_type=template.scale_type,
                        key_signature=normalized_key,
                        relative_path=output_path.relative_to(self.output_root).as_posix(),
                        sha256=file_sha256(output_path),
                        duration_seconds=result.duration_seconds,
                        sample_rate=result.sample_rate,
                        channels=result.channels,
                    )
                )
        return entries

    def generate_commute_tracks(
        self,
        commute_keys: list[str],
        template_names: list[str],
        workout_name: str,
    ) -> list[ManifestEntry]:
        """Generate one commute workout track per template across multiple keys."""
        entries: list[ManifestEntry] = []
        normalized_keys = [normalize_key_signature(k) for k in commute_keys]
        for template_name in template_names:
            template = self.templates[template_name]
            note_midis: list[int] = []
            for key in normalized_keys:
                note_midis.extend(_build_scale_drill_notes(key, template))
                note_midis.extend([-1, -1, -1])
            note_midis_tuple = tuple(note_midis)
            key_label = "-".join(slug_key(k) for k in normalized_keys)
            file_name = f"{workout_name}__{template.scale_type}__{key_label}.wav"
            output_path = self.commute_root / template.scale_type / file_name
            request = TrackRequest(
                kind="commute",
                template_name=template.name,
                scale_type=template.scale_type,
                key_signature=",".join(normalized_keys),
                bpm=template.bpm,
                beats_per_note=template.beats_per_note,
                note_midis=note_midis_tuple,
                sample_rate=DEFAULT_SAMPLE_RATE,
            )
            result = self.renderer.render(request, output_path)
            entries.append(
                ManifestEntry(
                    kind="commute",
                    template_name=template.name,
                    scale_type=template.scale_type,
                    key_signature=",".join(normalized_keys),
                    relative_path=output_path.relative_to(self.output_root).as_posix(),
                    sha256=file_sha256(output_path),
                    duration_seconds=result.duration_seconds,
                    sample_rate=result.sample_rate,
                    channels=result.channels,
                )
            )
        return entries

    def write_manifest(self, entries: list[ManifestEntry]) -> Path:
        """Persist deterministic index for generated tracks."""
        payload = {
            "manifest_version": 1,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "output_root": self.output_root.as_posix(),
            "tracks": [asdict(entry) for entry in sorted(entries, key=lambda e: e.relative_path)],
        }
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return self.manifest_path


@dataclass(frozen=True)
class SmokeCheckResult:
    """Smoke-check summary for generated assets in one manifest."""

    checked: int
    passed: int
    failed: int
    failures: tuple[str, ...]


def build_default_templates() -> dict[str, ExerciseTemplate]:
    """Return canonical vocal drill templates for this FR."""
    templates = {
        "major": ExerciseTemplate(name="major", scale_type="major"),
        "natural_minor": ExerciseTemplate(name="natural_minor", scale_type="natural_minor"),
        "harmonic_minor": ExerciseTemplate(name="harmonic_minor", scale_type="harmonic_minor"),
    }
    return templates


def generate_vocal_pilot_bundle(
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    single_keys: list[str] | None = None,
    commute_keys: list[str] | None = None,
    template_names: list[str] | None = None,
    workout_name: str = "tenor_commute",
) -> Path:
    """Generate single-key and commute tracks, then persist a manifest index."""
    selected_single_keys = single_keys if single_keys is not None else DEFAULT_SINGLE_KEYS
    selected_commute_keys = commute_keys if commute_keys is not None else DEFAULT_COMMUTE_KEYS
    templates = build_default_templates()
    selected_templates = template_names if template_names is not None else sorted(templates.keys())

    generator = VocalPilotGenerator(
        templates=templates,
        renderer=SineWaveRenderer(sample_rate=DEFAULT_SAMPLE_RATE),
        output_root=output_root,
    )
    entries: list[ManifestEntry] = []
    entries.extend(generator.generate_single_key_tracks(selected_single_keys, selected_templates))
    entries.extend(generator.generate_commute_tracks(selected_commute_keys, selected_templates, workout_name))
    return generator.write_manifest(entries)


def smoke_check_manifest(manifest_path: Path) -> SmokeCheckResult:
    """Validate that all manifest tracks exist and expose readable metadata."""
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    tracks = payload.get("tracks", [])
    output_root = Path(payload["output_root"])

    failures: list[str] = []
    for track in tracks:
        rel_path = track["relative_path"]
        file_path = output_root / rel_path
        if not file_path.exists():
            failures.append(f"missing:{rel_path}")
            continue

        audio = MutagenFile(file_path)
        info = getattr(audio, "info", None)
        length = float(getattr(info, "length", 0.0) or 0.0)
        sample_rate = int(getattr(info, "sample_rate", 0) or 0)
        channels = int(getattr(info, "channels", 0) or 0)
        if length <= 0.0 or sample_rate <= 0 or channels <= 0:
            failures.append(f"unreadable:{rel_path}")

    checked = len(tracks)
    failed = len(failures)
    return SmokeCheckResult(
        checked=checked,
        passed=checked - failed,
        failed=failed,
        failures=tuple(failures),
    )


def normalize_key_signature(key_signature: str) -> str:
    """Normalize key signature text to stable display notation."""
    cleaned = key_signature.strip().replace(" ", "")
    if not cleaned:
        raise ValueError("key signature cannot be empty")
    token = cleaned.upper()
    semitone = NOTE_TO_SEMITONE.get(token)
    if semitone is None:
        raise ValueError(f"unsupported key signature: {key_signature}")
    return SEMITONE_TO_NAME[semitone]


def slug_key(key_signature: str) -> str:
    """Convert key signatures to deterministic filesystem tokens."""
    return key_signature.replace("#", "sharp").replace("b", "flat")


def midi_to_frequency(midi_note: int) -> float:
    """Convert MIDI note number to frequency in Hz."""
    return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))


def file_sha256(path: Path) -> str:
    """Return stable SHA256 hash for a generated file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_scale_drill_notes(key_signature: str, template: ExerciseTemplate) -> tuple[int, ...]:
    scale = SCALE_INTERVALS[template.scale_type]
    root_midi = _select_root_midi(key_signature, VocalRange())

    phrase = [root_midi + interval for interval in scale]
    descending = phrase[-2::-1]
    one_cycle = phrase + descending

    output: list[int] = []
    for _ in range(template.cycles):
        output.extend(one_cycle)
    return tuple(output)


def _select_root_midi(key_signature: str, vocal_range: VocalRange) -> int:
    semitone = NOTE_TO_SEMITONE[key_signature.upper()]
    top = vocal_range.high_midi - 12
    candidates = [
        midi
        for midi in range(vocal_range.low_midi, top + 1)
        if midi % 12 == semitone
    ]
    if not candidates:
        raise ValueError(f"no root note available for key {key_signature} in configured range")
    target = (vocal_range.low_midi + top) // 2
    return min(candidates, key=lambda c: abs(c - target))


def _synthesize_sine_note(frequency_hz: float, duration_seconds: float, sample_rate: int) -> bytes:
    total_samples = max(1, int(duration_seconds * sample_rate))
    attack_samples = max(1, int(sample_rate * 0.01))
    release_samples = max(1, int(sample_rate * 0.015))
    max_amp = 32767
    gain = 0.2

    frames = bytearray()
    for sample_index in range(total_samples):
        env = 1.0
        if sample_index < attack_samples:
            env = sample_index / attack_samples
        elif sample_index > total_samples - release_samples:
            env = max(0.0, (total_samples - sample_index) / release_samples)
        sample = math.sin((2.0 * math.pi * frequency_hz * sample_index) / sample_rate)
        value = int(max_amp * gain * env * sample)
        frames.extend(struct.pack("<h", value))
    return bytes(frames)


def _silence_frames(sample_count: int) -> bytes:
    return b"\x00\x00" * max(sample_count, 0)


def _parse_csv_list(raw: str) -> list[str]:
    return [token.strip() for token in raw.split(",") if token.strip()]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate and validate vocal pilot drill tracks.")
    sub = parser.add_subparsers(dest="command", required=True)

    generate_cmd = sub.add_parser("generate", help="Generate single-key and commute vocal pilot tracks")
    generate_cmd.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    generate_cmd.add_argument("--single-keys", default=",".join(DEFAULT_SINGLE_KEYS))
    generate_cmd.add_argument("--commute-keys", default=",".join(DEFAULT_COMMUTE_KEYS))
    generate_cmd.add_argument(
        "--templates",
        default="major,natural_minor,harmonic_minor",
        help="Comma-separated subset from: major,natural_minor,harmonic_minor",
    )
    generate_cmd.add_argument("--commute-name", default="tenor_commute")

    smoke_cmd = sub.add_parser("smoke-check", help="Validate existing manifest entries")
    smoke_cmd.add_argument("--manifest", type=Path, default=DEFAULT_OUTPUT_ROOT / "manifests" / "index.json")

    return parser


def main() -> int:
    """CLI entry point for generation and smoke-check operations."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "generate":
        manifest_path = generate_vocal_pilot_bundle(
            output_root=args.output_root,
            single_keys=_parse_csv_list(args.single_keys),
            commute_keys=_parse_csv_list(args.commute_keys),
            template_names=_parse_csv_list(args.templates),
            workout_name=args.commute_name,
        )
        result = smoke_check_manifest(manifest_path)
        print(f"manifest={manifest_path}")
        print(f"checked={result.checked} passed={result.passed} failed={result.failed}")
        return 0 if result.failed == 0 else 1

    if args.command == "smoke-check":
        result = smoke_check_manifest(args.manifest)
        print(f"manifest={args.manifest}")
        print(f"checked={result.checked} passed={result.passed} failed={result.failed}")
        if result.failures:
            for failure in result.failures:
                print(f"failure={failure}")
        return 0 if result.failed == 0 else 1

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
