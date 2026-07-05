"""Orchestrates persona assignment + .hlx generation + validation for a
batch of gap songs (FR-20260705-guitar-tech-persona-agent).

Pure/testable — takes song rows + existing filenames, returns one
PilotResult per genuine gap song. No DB or file I/O here; that lives in
tools/generate_guitar_tech_pilot.py, which wires this against the real
encrypted DB connection and the real HelixFiles/ directory.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from guitar_tech.hlx_generator import generate_preset
from guitar_tech.hlx_validator import ValidationResult, validate_preset_dict
from guitar_tech.persona_rubric import PersonaMatch, score_persona
from guitar_tech.pilot_selector import find_gap_songs


def safe_filename_stub(title: str) -> str:
    """Collapse a song title into a filesystem-safe filename stub.

    Non-alphanumeric characters become underscores; consecutive
    underscores are collapsed to one; leading/trailing underscores are
    stripped. E.g. "I Can't Go for That" -> "I_Can_t_Go_for_That".
    """
    stub = "".join(c if c.isalnum() else "_" for c in title).strip("_")
    while "__" in stub:
        stub = stub.replace("__", "_")
    return stub


@dataclass(frozen=True)
class PilotResult:
    """One song's full pilot-batch outcome: persona, generated preset,
    validation result, and target filename."""

    song: Mapping[str, Any]
    persona_match: PersonaMatch
    preset: dict
    validation: ValidationResult
    filename: str


def build_pilot_results(
    rows: list[Mapping], existing_filenames: list[str]
) -> list[PilotResult]:
    """Assign a persona, generate a preset, and validate it for each genuine
    gap song in `rows`. Songs with an existing dedicated preset (per
    `find_gap_songs`) are skipped. Output preserves `rows` order."""
    gaps = find_gap_songs(rows, existing_filenames)
    gap_ids = {g.id for g in gaps}

    results = []
    for row in rows:
        if row["id"] not in gap_ids:
            continue
        match = score_persona(artist=row["artist"], key_sig=row["key_sig"], bpm=row["bpm"])
        preset = generate_preset(
            title=row["title"], artist=row["artist"], bpm=row["bpm"], persona_match=match
        )
        validation = validate_preset_dict(preset, source=row["title"])
        filename = f"{safe_filename_stub(row['title'])}.hlx"
        results.append(PilotResult(row, match, preset, validation, filename))
    return results
