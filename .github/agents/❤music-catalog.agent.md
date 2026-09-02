---
name: ❤music-catalog
description: Music catalog management agent for Tyler James Drake's ❤Music project. Use for scanning and indexing music files, identifying duplicates across Masters/rockstar/recordings folders, importing track metadata, linking recordings to tracks in the DB, organizing lyrics files, cataloging guitar tabs and sheet music. Handles catalog_index table operations and file path management across f:\Masters, G:\TylerJamesDrake\rockstar, f:\recordings.
user-invocable: false
---
<!-- inherits: ../instructions/❤music-base.instructions.md -->
<!-- inherits: ../instructions/agent-self-regen.instructions.md -->

# ❤music-catalog Agent

Manages Tyler's music file catalog — indexing, deduplication, and DB imports.

**Context bootstrap + source locations + DB access:** follow `❤music-base.instructions.md`.

## Capability: Import Originals Lyrics

Tool: `C:\G\python.exe tools\import_originals_lyrics.py [--apply] [--db-path <path>]`

**Sources:** `catalog/sheet_music/originals/*.docx` (python-docx), `*.pdf` (pypdf), `lyrics/*.txt` (UTF-8)

**Key behaviors:**
- Title parsed from filename → fuzzy-matched to `tracks.title` (compact-alphanumeric exact + SequenceMatcher ≥ 0.72, with substring boost ≥ 70%)
- Unmatched files imported with `track_id = NULL`
- `version_label`: `originals_docx` / `originals_pdf` / `originals_txt` (slug suffix on collision)
- Idempotent: dedup keyed on `lyrics.file_path`
- `People*.pdf` → moved to `catalog/sheet_music/covers/` during `--apply` (not imported as lyrics)

**Modes:** default = dry-run (prints plan, no writes); `--apply` = execute plan
