# QA Re-run — BFX-20260630-chord-sheet-ollama-timeout (light tier)

**Date:** 2026-07-03
**QA agent:** ⊕workspace-qa-light (GPT-5.4 mini)
**Trigger:** post-bugfix re-verification (`_strip_markdown_json_fences()` + reworked prompt, 3 new regression tests in `test_chord_sheet_tab.py`)

## Environment verified
- `llama3.1:8b` confirmed available via `/api/tags` (digest `46e0c10c...`, 4.92 GB, parameter_size 8.0B).
- All 5 pilot PDFs confirmed present in `F:\temp`: gimmeGimme.pdf, sweetCaroline.pdf,
  99redBalloons.pdf, monyMony.pdf, landDownUnder.pdf.
- **Server staleness caught and corrected:** the Music Dashboard process already listening
  on port 5050 (PID 37072) had a start time of 9:18 AM, but `music_dashboard.py` was last
  modified 9:41 AM — the running process predated the bugfix. Killed the stale process and
  started a fresh one; it bound to port **5051** (5050 was released moments earlier but the
  Flask dev server picked the next free port). All testing below was run against the
  freshly-started process on `http://127.0.0.1:5051/` to guarantee the fix under test was
  actually loaded.

## Regression confirmed fixed
- **422 / markdown-fence defect: FIXED.** `POST /chord-sheet/parse` returned `200 OK` on
  every trial (2/2). No more `json.JSONDecodeError` from ` ```json ` fences.
- **Song-echo/hallucination defect: FIXED.** Both trials returned the correct submitted
  song's title/artist (`"Gimme Gimme Gimme"` / `"Abba"`, `"Sweet Caroline"` / `"Neil Diamond"`),
  not the previous run's hallucinated "Fake Plastic Trees" (Radiohead) schema-example echo.

## NEW blocking defect found: parsed JSON omits song content (lyrics/chords)

Trial 1 — gimmeGimme.pdf, raw response body from `/chord-sheet/parse`:
```json
{"title": "Gimme Gimme Gimme", "artist": "Abba", "key": "Bb", "bpm": "120"}
```
No `sections`, no lyrics, no chord/lyric lines at all — despite ~2700 chars of verse/chorus/
chord content in the submitted `raw_text`. Clicking through to **Save & Generate DOCX**
returns 200 and produces `Gimme Gimme Gimme_Abba_Key_B_Flat.docx`, but inspecting the file
with `python-docx` shows it contains **only a single title-line paragraph**
(`"Gimme Gimme Gimme — Abba · BPM 120 · Key Bb"`) — no lyrics, no chords, no song body at all.

Trial 2 — sweetCaroline.pdf, raw response body:
```json
{
  "title": "Sweet Caroline",
  "artist": "Neil Diamond",
  "key": "E E D# G#",
  "bpm": "120",
  "sections": [
    {"name": "Chorus 1", "lines": ["B E (E D# G#) E F", "F# F# F# F#"]},
    {"name": "Chorus 2", "lines": ["B E (E D# G#) E F", "F# F# F# F#"]}
  ]
}
```
Title/artist correct, but this time `sections` exists — however it contains **only chord
tokens, zero lyric text** (no "Sweet Caroline, good times never seemed so good", etc.), only
2 of the 3 submitted sections (Verse 1, Chorus 1 collapsed to "Chorus 1"/"Chorus 2" with
duplicated/garbled chord lines, Intro/Outro dropped), and an invalid `key` field
(`"E E D# G#"` is not a key signature — looks like a chord-annotation string leaked into the
key field).

**Root cause (inferred):** the reworked prompt appears to have over-corrected — in removing
the embedded schema-example song (which fixed the echo bug), it also stripped or
de-emphasized the instruction/schema requirement to include full lyric+chord line-by-line
content in `sections[].lines`. The model is now returning a technically-valid, non-hallucinated,
but functionally empty/near-empty shell of the song.

**Impact:** the actual user-facing deliverable (a usable chord sheet) is not produced —
0/2 trials produced any lyrics, and 1/2 trials produced zero song sections whatsoever. This
is a hard block on the BFX acceptance criteria ("5 pilot PDFs producing usable .docx chord
sheets"). Testing stopped after 2/5 songs since the defect is in the shared `chord_sheet_parse`
prompt/parsing path that all 5 songs route through identically (same failure mode as the
original FAIL run's rationale for stopping early).

## Proof artifacts
- `f:\❤Music\proof\BFX-20260630-chord-sheet-ollama-timeout\sweetCaroline-parse-incomplete.png`
  — full-page screenshot of trial 2, "Parsed. Review and edit..." success banner with the
  incomplete JSON visible in the Review/Edit panel.
- Raw request/response bodies for both trials captured above in this file.
- Generated file confirmed on disk: `F:\catalog\sheet_music\covers\Gimme Gimme Gimme_Abba_Key_B_Flat.docx`
  (title-only, no lyrics/chords — inspected via `python-docx`).

## Verdict: **FAIL**

Both previously-identified defects (422/markdown-fence, song hallucination/echo) are
confirmed fixed. However, functional QA of the end-to-end outcome — "chord sheet parse
produces a usable DOCX with the song's actual lyrics and chords" — still fails 2/2 on the
first two pilot songs tested, due to a newly-surfaced defect: the parsed JSON is missing or
nearly missing all lyric/chord section content. Acceptance criteria (5 pilot PDFs producing
usable chord sheets matching the submitted song) is not met. Recommend routing back to
implementation to strengthen the prompt so it reliably instructs the model to transcribe
**all** submitted sections/lines verbatim into `sections[].lines`, and add a server-side
validation/regression test asserting `sections` is non-empty and line count is proportional
to input length before treating a parse as successful.
