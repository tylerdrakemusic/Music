---
mode: ❤music-orchestrator
---
# Tyler James Drake Tee Prompt Catalog

Use this prompt to create or edit one stable-ID entry in the canonical tee prompt catalog.

## Canonical files

- Catalog: `Brand/tyler-james-drake-tee-prompt-catalog.json`
- Brand rules: `Brand/tyler-james-drake-merch-brand-system.md`
- Source prompts: `Brand/t-design prompts.txt`

## Required request

Ask Tyler for:

- `operation`: `create` or `edit`
- `id`: required for `edit`; optional for `create`
- the concept, title, garment use, palette, print notes, and any requested field changes

Do not infer a destructive edit from an ambiguous request. If the request does not identify an operation or target ID, ask one concise clarification question before changing files.

## Create workflow

1. Read the catalog and brand system before proposing content.
2. If no ID is supplied, assign the next available numeric ID using `TJD-TEE-NNN`, preserving existing IDs.
3. Draft the complete entry before writing it.
4. Check that the concept is original music-world merchandise, rights-aware, print-conscious, and consistent with the brand system.
5. Set new entries to `concept_pending` and `exact_image_approval_status: not_started`.
6. Preserve provenance. If the concept is new, use `source: operator-authored` and identify the request in `source_entry`.
7. Show the proposed entry and wait for Tyler's concept approval before treating it as approved.

## Edit workflow

1. Locate the exact requested ID. Never silently substitute another entry.
2. Preserve the ID, catalog structure, provenance, and unrelated fields.
3. Re-run the rights, duplication, brand, and print-readiness checks after editing.
4. If the concept or artwork direction changes materially, reset `concept_approval_status` to `concept_pending` and `exact_image_approval_status` to `not_started`.
5. Do not mark either approval state as approved without explicit Tyler approval.
6. Show a concise before/after summary and the complete resulting entry.

## Required entry fields

Every retained prompt must contain:

- `id`
- `title`
- `concept`
- `intended_garment_use`
- `palette`
- `print_notes`
- `provenance`
- `concept_approval_status`
- `exact_image_approval_status`

Allowed concept states are `concept_pending` and `concept_approved`. Allowed exact-image states are `not_started`, `exact_image_pending`, and `exact_image_approved`.

## Hard boundaries

- Use original music-world concepts only.
- Reject recognizable artists, athletes, teams, logos, protected characters, and religious or cultural figures unless Tyler documents a separate license.
- Do not copy third-party marks, readable labels, signatures, or named artist likenesses.
- Do not generate images, select providers, render transparent artwork, create product listings, or publish commerce output from this prompt.
- Do not edit the rejected-source list to hide a rejected concept; add a new curated entry only when it passes the brand and rights checks.
- Keep edits limited to the requested catalog entry unless a related schema correction is required and explicitly reported.

## Validation and response

After an edit, parse the JSON and verify unique IDs, required fields, valid approval states, provenance, and valid JSON formatting. Report:

- operation and ID
- whether the entry was created or changed
- validation result
- approval state
- files changed
- any unresolved human decision

If validation fails, do not leave a partial catalog edit. Never claim exact-image approval or commerce readiness from this workflow.
