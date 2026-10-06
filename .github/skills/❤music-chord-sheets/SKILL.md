---
name: ❤music-chord-sheets
description: 'Agentic chord-sheet generation for ❤Music. Use when Tyler hands Copilot one or more input files/links in chat (PDF, raw text, URL, image, or any parseable song structure) and asks to turn them into chord sheets. Covers parsing unconstrained input into the song_template.json schema, routing output to covers/ vs originals/ (Tyler James Drake = original, all other artists = cover), generating the .docx via tools/make_chord_sheet.py, Playwright-based accuracy validation against the source, batch review, and git commit on Tyler''s approval. Triggers: "make a chord sheet", "chord sheet for <song>", "process these songs into chord sheets", "generate sheet music from this PDF/text/link". Replaces the disabled Ollama-based Chord Sheets dashboard tab (BFX-20260630).'
---

# ❤music-chord-sheets

Turns raw song input Tyler pastes or attaches in chat into reviewed,
catalog-ready chord sheet `.docx` files, entirely in-session without dashboard
automation or local LLMs.

## When to Use

- Tyler supplies one or more chord charts, lead sheets, lyric-and-chord PDFs,
  URLs, images, or other song-structure documents and asks for a chord sheet,
  sheet music, or to process a song.
- Batch requests: process each input sequentially in the same session and
  present the complete batch for review only after all inputs are processed.

## Procedure

For each input file, in order:

### 1. Extract song structure

Read the input (PDF text, raw paste, fetched URL, or described image) and parse
it into the `song_template.json` schema used by
[`tools/make_chord_sheet.py`](../../../tools/make_chord_sheet.py):

```json
{
  "title": "...", "artist": "...", "key": "...", "bpm": "...",
  "sections": [
    { "name": "Verse 1", "lines": [ { "chords": "Dm F Am Dm", "lyrics": "..." } ] }
  ]
}
```

- Preserve chord/lyric line pairing exactly as it appears in the source.
- Use `[Section]` markers in raw text as section boundaries.
- Best-effort `key`/`bpm` if not explicit in the source; mark `"?"` if
  unknown. Never fabricate metadata.
- Call [`resolve_bpm`](../../../src/utils/chord_sheet_output.py) with the
  parsed `title`/`artist` and any manually noted BPM from the source as
  `manual_bpm`. This attempts an automated lookup via
  [`lookup_bpm`](../../../src/utils/bpm_lookup.py) first, using the
  `GETSONGBPM_API_KEY` environment variable. If there is no API key, an HTTP
  error, timeout, or no title/artist match, `resolve_bpm` falls back to
  `manual_bpm` when available, otherwise `"?"`. Never invent a BPM value.
- If input is genuinely unparseable, stop and tell Tyler rather than guessing.

### 2. Resolve output paths

Call [`resolve_chord_sheet_paths`](../../../src/utils/chord_sheet_output.py)
with the parsed `title`/`artist` and the Music repo root. It returns:

- `sheet_music_path`: `catalog/sheet_music/originals/` if the artist is Tyler
  James Drake, otherwise `catalog/sheet_music/covers/`, named
  `{Artist} - {Title}.docx`.
- `template_path`: `studio_master/song_templates/{Artist} - {Title}.json`.
- `log_path`: `catalog/sheet_music/_process_logs/chord_sheets_runs.jsonl`,
  one JSONL record per processed input.

### 3. Save JSON template

Write the parsed song JSON to `template_path`, creating parent directories as
needed.

### 4. Generate the .docx

Import `build_docx` and `load_song` from `tools/make_chord_sheet.py` and call
`build_docx(song, sheet_music_path)`.

### 5. Validate with Playwright

Extract text from the generated `.docx` (paragraph text via `python-docx`) and
call [`render_validation_html`](../../../src/utils/chord_sheet_output.py)
with the original source lines and generated lines. Open the resulting HTML
report with a Playwright browser tool and inspect the mismatch count and rows
before presenting results. Report mismatches; do not silently accept them.

### 6. Log the run

Call `log_chord_sheet_run(log_path, {...})` with `title`, `artist`,
`sheet_music_path`, `template_path`, `is_original`, and the mismatch count from
validation.

### 7. Batch review and commit

After every input in the batch is processed, present all generated file paths
and validation summaries to Tyler for review. Commit only the `.docx`, `.json`,
and process-log artifacts Tyler explicitly approves. Never commit
automatically, and do not push.

## Constraints

- Keep the disabled Chord Sheets tab disabled; do not alter
  `music_dashboard.py`'s `ENABLE_CHORD_SHEETS = False` code.
- Do not fabricate lyrics, chords, or metadata absent from the source.
- Do not use Ollama or another local LLM for this in-chat workflow.