# QA Re-run 2 — BFX-20260630-chord-sheet-ollama-timeout (light tier)
Date: 2026-07-03 (post 3rd bugfix round)

## Result: **FAIL**

## Pre-flight
- `llama3.1:8b` confirmed available via `/api/tags` (also `qwen2:0.5b` present).
- All 5 pilot PDFs confirmed present in `F:\temp`: gimmeGimme.pdf, sweetCaroline.pdf,
  99redBalloons.pdf, monyMony.pdf, landDownUnder.pdf.
- **Stale process check**: `src/analysis/music_dashboard.py` mtime = 2026-07-03 09:58:32.
  Found THREE stale dashboard processes (PIDs 11968, 27836, 22836) all started before
  09:58:32 — killed all three. Started a fresh instance (PID 7420, created 09:59:54,
  postdates the source mtime). Confirmed via `/health` → 200 `{ready: true, status: ok}`.
  This QA run is confirmed against current code, not stale code.

## Execution
Drove the Chord Sheets tab (`A — New Song`) via Playwright at http://127.0.0.1:5057/
for gimmeGimme (full UI flow: paste text → Parse with AI → observed result), then
confirmed the identical failure pattern for the remaining 4 songs via direct
`POST /chord-sheet/parse` calls (same code path the UI button hits) to gather
diagnostic evidence efficiently once the systemic defect was reproduced.

| Song | HTTP Status | Failure Mode |
|---|---|---|
| gimmeGimme | 422 | `LLM parse failed` — response still wrapped in ` ```json ` fences AND hallucinated wrong song entirely ("Beyoncé - Lemonade" by "Beck"), with placeholder chord/lyric content (`"[Major Scale] Intro: Chord 1 - Chord 4"`, empty `lyrics: ""` throughout) |
| sweetCaroline | 422 | `LLM parse incomplete: missing or negligible song content` — only title/artist/key/bpm returned, zero sections |
| 99redBalloons | 422 | `LLM parse failed` (see `parse_resp_99redBalloons_error.json`) |
| monyMony | 422 | `LLM parse failed` — malformed JSON (unquoted `bpm` key, no `sections` at all), wrong "title" placeholder text ("Title of song") |
| landDownUnder | 422 | `LLM parse failed` (see `parse_resp_landDownUnder_error.json`) |

**0/5 PDFs succeeded.** Raw response bodies saved alongside this file
(`parse_resp_<song>_error.json` for all 5).

## Assessment against the three claimed fixes
1. **Markdown fence stripping** — NOT fixed. gimmeGimme response is still wrapped in
   ` ```json ... ``` `.
2. **Prompt-echo hallucination** — NOT fixed, and arguably worse: the model no longer
   reliably echoes the prior schema example (Fake Plastic Trees/Radiohead) — it now
   fabricates entirely different, unrelated songs/artists per request (Beyoncé/Beck,
   Billy Idol "Mony Mony (Live Version)" as both title and key, "Caroline Song"/Neil
   Diamond with no chord/lyric content). The model is still not performing verbatim
   transcription of the submitted `raw_text` in any of the 5 cases.
3. **422 validation for near-empty responses** — this part IS working correctly (it
   caught 4/5 incomplete responses), but it only proves the guard rail functions; it
   does not mean the underlying generation defect is resolved. Every request still
   fails end-to-end.

## Conclusion
The core defect (LLM not transcribing the submitted song verbatim, and/or not
respecting the JSON-only output format) persists after the 3rd fix round. No .docx
files were produced for any of the 5 pilot songs since parsing failed before the
Save & Generate DOCX step could run. **PASS criteria not met — reporting FAIL.**
Per instructions, the FR/BFX ledger has NOT been updated; this is a results-only report.

## Proof artifacts (this run)
- `parse_resp_gimme_error.json`
- `parse_resp_sweetCaroline_error.json`
- `parse_resp_99redBalloons_error.json`
- `parse_resp_monyMony_error.json`
- `parse_resp_landDownUnder_error.json`
- Screenshot of gimmeGimme UI failure (see `chord-sheet-parse-failure-gimmeGimme.png`
  from prior run, same error message reproduced this run)
