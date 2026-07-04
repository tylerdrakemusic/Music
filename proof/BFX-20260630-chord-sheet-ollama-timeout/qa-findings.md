# QA — BFX-20260630-chord-sheet-ollama-timeout (light tier)

**Date:** 2026-07-03
**QA agent:** ⊕workspace-qa-light (GPT-5.4 mini)

## Environment verified
- Ollama server running (PID 14532 `ollama`, PID 20016 `ollama app`), `/api/tags` confirms
  `llama3.1:8b` (digest `46e0c10c...`, 4.92 GB, parameter_size 8.0B) is installed and available.
- 5 pilot PDFs confirmed present in `F:\temp`: gimmeGimme.pdf, sweetCaroline.pdf,
  99redBalloons.pdf, monyMony.pdf, landDownUnder.pdf.
- Music Dashboard confirmed running at `http://localhost:5050/` (health check 200 OK),
  Chord Sheets tab reachable and renders Workflow A (paste raw text → Parse with AI →
  Save & Generate DOCX).
- No evidence of a prior completed pipeline run: `f:\❤Music\proof\BFX-20260630-chord-sheet-ollama-timeout\`
  was empty at session start, no `.docx` files found anywhere under `F:\temp` or
  `❤Music\catalog\sheet_music\covers`. Restarted validation from scratch per task instructions.

## Test executed
- Extracted raw chord-chart text from `gimmeGimme.pdf` via `pdfplumber` (2713 chars extracted
  successfully — PDF text extraction itself works fine).
- Pasted a representative excerpt of the Gimme Gimme Gimme (ABBA) chord chart into the
  Chord Sheets → Workflow A raw-text box via Playwright.
- Clicked "Parse with AI" **twice** (2 independent trials).

## Result: FAIL — reproducible bug, 2/2 trials

Both calls returned `POST /chord-sheet/parse => 422 UNPROCESSABLE ENTITY` with
`{"error": "LLM parse failed", "raw": "```json\n{...}\n```"}`.

Two distinct defects found, root-caused from the raw response body (saved above):

1. **Original timeout defect appears FIXED.** Neither call timed out or raised
   "Cannot reach Ollama" — both got a full generation response from `llama3.1:8b`
   within ~30s. The `_generate_with_ollama_fallback` retry/fallback logic in
   `music_dashboard.py` (chord_sheet_parse route) did not need to engage a fallback
   model; the primary model responded directly.

2. **NEW/pre-existing blocking bug uncovered:** `chord_sheet_parse()` calls
   `json.loads(llm_response)` directly with no markdown-fence stripping
   (`music_dashboard.py` ~line 2999). `llama3.1:8b` wrapped its JSON in
   ` ```json ... ``` ` fences on both trials, despite the prompt explicitly
   instructing "Return ONLY the JSON object, no explanation, no code block markers."
   This causes `json.JSONDecodeError` → 422 every time, independent of the
   original timeout bug.

3. **Content correctness issue:** on both trials the model's returned JSON was
   for **"Fake Plastic Trees" by Radiohead** — a completely different song from
   the ABBA "Gimme Gimme Gimme" text that was actually submitted as `raw_text`.
   The model appears to be echoing the schema *example* song (drawn from an
   existing template file used to build the prompt) rather than parsing the
   user's actual input. This is model-following-instructions behavior with the
   smaller 8B model, not a code bug per se, but it means the endpoint currently
   produces **wrong output even when JSON parsing succeeds**.

Given (2) causes a hard 422 on every attempt observed, the pipeline cannot proceed
to `/chord-sheet/generate` for any of the 5 pilot PDFs. Testing was stopped after
2 reproducible failures on song 1 (gimmeGimme) rather than running all 5, since the
blocking defect is in shared code (`chord_sheet_parse`) that all 5 songs would hit
identically.

## Proof artifacts
- `f:\❤Music\proof\BFX-20260630-chord-sheet-ollama-timeout\chord-sheet-parse-failure-gimmeGimme.png`
  — full-page screenshot showing the "Error: LLM parse failed" UI state.
- Raw Ollama response bodies (both trials) captured above in this file — both show
  ` ```json ` fenced output for the wrong song (Fake Plastic Trees, not Gimme Gimme Gimme).

## Verdict: **FAIL**

The specific timed-out-connection defect named in the bug title appears resolved
(model responds without timing out). However, functional QA of the actual user-facing
outcome — "chord sheet parse succeeds and produces a DOCX" — fails 2/2 on the first
pilot song due to an unhandled markdown-fence-wrapped JSON response, compounded by
the model ignoring the submitted raw_text. Acceptance criteria (5 pilot PDFs producing
usable .docx chord sheets) is not met. Recommend routing back to implementation to:
(a) strip ` ```json ` fences before `json.loads`, and (b) investigate why the prompt's
schema example content is dominating the model's output over the actual `raw_text`
(likely needs restructuring the prompt so raw_text is unambiguously the last/primary
instruction, or truncating/removing the full schema example body).
