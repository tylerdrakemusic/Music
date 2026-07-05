"""Tests for src/guitar_tech/todo_writer.py (FR-20260705-guitar-tech-persona-agent).

Verifies new .hlx filenames are appended to HelixFiles/TODO.md's two existing
checklist sections in the exact established format, without disturbing
existing entries.
"""
from __future__ import annotations

from guitar_tech.todo_writer import append_todo_entries

_SAMPLE_TODO = """# Helix Preset TODOs

## Expression Pedal Assignment
- [ ] Add expression pedal (Mission EP1-L6) controller assignment to ALL presets
  - Wah presets: EXP → Wah Position (min 0%, max 100%)
  - Non-wah presets: EXP → Volume (min 0%, max 100%)
  - Configure per-preset in HX Edit under Controller Assign

### Presets needing EXP assignment:
- [ ] VoodooChild.hlx — EXP → Wah
- [ ] Rhiannon_Fleetwood_Mac.hlx — EXP → Volume

---

## Snapshots (3 per preset)
- [ ] Add 3 named/custom snapshots to ALL presets
  - Snapshot 1: Full tone (all blocks enabled)
  - Snapshot 2: Stripped back (drive/mod off, clean rhythm)
  - Snapshot 3: Lead boost (all blocks on, solo-friendly settings)
  - Customize snapshot names per song where appropriate

### Presets needing snapshots:
- [x] VoodooChild.hlx — Done (Voodoo Crunch / Raw Plexi / Lead Wail)
- [ ] Rhiannon_Fleetwood_Mac.hlx
"""


def test_append_adds_exp_lines_before_separator(tmp_path):
    todo_path = tmp_path / "TODO.md"
    todo_path.write_text(_SAMPLE_TODO, encoding="utf-8")

    append_todo_entries(todo_path, ["NewSong.hlx"])

    content = todo_path.read_text(encoding="utf-8")
    assert "- [ ] NewSong.hlx — EXP → Volume" in content
    exp_section, _, snapshot_section = content.partition("---")
    assert "NewSong.hlx" in exp_section
    assert "NewSong.hlx" in snapshot_section


def test_append_adds_plain_line_to_snapshot_section(tmp_path):
    todo_path = tmp_path / "TODO.md"
    todo_path.write_text(_SAMPLE_TODO, encoding="utf-8")

    append_todo_entries(todo_path, ["NewSong.hlx"])

    content = todo_path.read_text(encoding="utf-8")
    assert content.rstrip("\n").endswith("- [ ] NewSong.hlx")


def test_append_preserves_existing_entries(tmp_path):
    todo_path = tmp_path / "TODO.md"
    todo_path.write_text(_SAMPLE_TODO, encoding="utf-8")

    append_todo_entries(todo_path, ["NewSong.hlx"])

    content = todo_path.read_text(encoding="utf-8")
    assert "- [ ] VoodooChild.hlx — EXP → Wah" in content
    assert "- [x] VoodooChild.hlx — Done (Voodoo Crunch / Raw Plexi / Lead Wail)" in content
    assert "- [ ] Rhiannon_Fleetwood_Mac.hlx — EXP → Volume" in content


def test_append_multiple_filenames_in_order(tmp_path):
    todo_path = tmp_path / "TODO.md"
    todo_path.write_text(_SAMPLE_TODO, encoding="utf-8")

    append_todo_entries(todo_path, ["SongA.hlx", "SongB.hlx"])

    content = todo_path.read_text(encoding="utf-8")
    exp_section, _, snapshot_section = content.partition("---")
    assert exp_section.index("SongA.hlx") < exp_section.index("SongB.hlx")
    assert "- [ ] SongA.hlx" in snapshot_section
    assert "- [ ] SongB.hlx" in snapshot_section


def test_append_keeps_exactly_one_blank_line_before_separator(tmp_path):
    todo_path = tmp_path / "TODO.md"
    todo_path.write_text(_SAMPLE_TODO, encoding="utf-8")

    append_todo_entries(todo_path, ["NewSong.hlx"])

    content = todo_path.read_text(encoding="utf-8")
    assert "- [ ] NewSong.hlx — EXP → Volume\n\n---\n" in content

