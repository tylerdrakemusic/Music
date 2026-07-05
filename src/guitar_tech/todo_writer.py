"""Appends new .hlx filenames to HelixFiles/TODO.md's two checklist sections
(FR-20260705-guitar-tech-persona-agent).

Matches the established TODO.md convention exactly:
  - "### Presets needing EXP assignment:" section -> one
    "- [ ] <Filename>.hlx — EXP → Volume" line per new preset, inserted
    right before the "---" separator that ends the section.
  - "### Presets needing snapshots:" section -> one "- [ ] <Filename>.hlx"
    line per new preset, appended at the end of the file (this is the last
    section in the document).
"""
from __future__ import annotations

from pathlib import Path

_SEPARATOR = "---\n"


def append_todo_entries(todo_path: Path | str, filenames: list[str]) -> None:
    """Append one EXP-assignment line and one snapshot line per filename."""
    todo_path = Path(todo_path)
    content = todo_path.read_text(encoding="utf-8")

    before, sep, after = content.partition(_SEPARATOR)
    exp_block = "\n".join(f"- [ ] {name} — EXP → Volume" for name in filenames)
    content = before.rstrip("\n") + "\n" + exp_block + "\n\n" + sep + after

    plain_block = "\n".join(f"- [ ] {name}" for name in filenames)
    content = content.rstrip("\n") + "\n" + plain_block + "\n"

    todo_path.write_text(content, encoding="utf-8")
