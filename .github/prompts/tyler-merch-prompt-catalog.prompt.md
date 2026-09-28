---
mode: ❤music-orchestrator
---
# Tyler James Drake Tee Prompt Catalog

Use this prompt to read, create, or edit one stable-ID entry in the database-backed tee prompt catalog.

## Canonical files

- Catalog data: `tee_prompt_catalogs` and `tee_prompts` in `src/data/heartmusic.db`
- Internal catalog helper: `src.merch.tee_prompt_catalog`
- Brand rules: `Brand/tyler-james-drake-merch-brand-system.md`
- Source prompts: `Brand/t-design prompts.txt`

The helper is the sole operator read/write path for this prompt. Run its
`list`, `read`, `create`, and `edit` operations from the Music repository root;
do not use SQL or edit the retired JSON catalog directly. `create` and `edit`
read one JSON object from standard input. For example:

```powershell
C:\G\python.exe -m src.merch.tee_prompt_catalog list
C:\G\python.exe -m src.merch.tee_prompt_catalog read TJD-TEE-001
@'
{"title":"A revised title"}
'@ | C:\G\python.exe -m src.merch.tee_prompt_catalog edit TJD-TEE-001
```

Only add `--approved-by-tyler` to a `create` or `edit` invocation after Tyler
has explicitly approved the complete proposed concept in the current prompt
conversation. The helper rejects unapproved creation and core-concept edits.

## Required request

Ask Tyler for:

- `operation`: `create` or `edit`
- `id`: required for `edit`; optional for `create`
- the concept, title, garment use, palette, print notes, and any requested field changes

Do not infer a destructive edit from an ambiguous request. If the request does not identify an operation or target ID, ask one concise clarification question before changing files.

## Create workflow

1. Read the catalog with the helper and review the brand system before proposing content.
2. If no ID is supplied, assign the next available numeric ID using `TJD-TEE-NNN`, preserving existing IDs.
3. Draft the complete entry without writing it.
4. Check that the concept is original music-world merchandise, rights-aware, print-conscious, and consistent with the brand system.
5. Preserve provenance. If the concept is new, use `source: operator-authored` and identify the request in `source_entry`.
6. Show the complete proposed entry and wait for Tyler's explicit approval. A new concept is not persisted before that approval.
7. After approval, pipe the complete JSON entry to `python -m src.merch.tee_prompt_catalog create --approved-by-tyler`. The helper initializes both concept revisions to `1`, marks the concept approved, and starts exact-image approval at `not_started`.
8. A declined or unapproved proposal is not written anywhere in the catalog; do not create rejected-source entries.

## Edit workflow

1. Read the exact requested ID with the helper. Never silently substitute another entry.
2. Preserve the ID, provenance, catalog metadata, and every field not explicitly changed.
3. Re-run the rights, duplication, brand, and print-readiness checks after editing.
4. A change to `concept` or its depicted subject requires showing the full revised concept and receiving Tyler's explicit approval before persistence. Then invoke `edit <ID> --approved-by-tyler`; the helper increments `concept_revision` and sets `concept_approval_revision` to that revision.
5. Edits to other fields can be saved without concept reapproval. Send only the requested changes to the helper; it merges partial provenance edits and preserves unrelated values.
6. Every changed image-generation input (`title`, `concept`, `intended_garment_use`, `palette`, or `print_notes`) advances the catalog's semantic patch version and resets the current `exact_image_approval_status` to `not_started`. Prior approved assets and records are retained; do not delete or rewrite them.
7. Do not set approval states or revisions manually. The helper owns these transitions.
8. Show a concise before/after summary, the catalog version, and the complete resulting entry.

## Required entry fields

Every retained prompt must contain:

- `id`
- `title`
- `concept`
- `intended_garment_use`
- `palette`
- `print_notes`
- `provenance`
- `concept_revision`
- `concept_approval_revision`
- `concept_approval_status`
- `exact_image_approval_status`

Allowed concept states are `concept_pending` and `concept_approved`. Allowed exact-image states are `not_started`, `exact_image_pending`, and `exact_image_approved`.
Generation requires `concept_approval_revision` to match `concept_revision`; a mismatch returns the entry to concept curation.

## Hard boundaries

- Use original music-world concepts only.
- Reject recognizable artists, athletes, teams, logos, protected characters, and religious or cultural figures unless Tyler documents a separate license.
- Do not copy third-party marks, readable labels, signatures, or named artist likenesses.
- Do not generate images, select providers, render transparent artwork, create product listings, or publish commerce output from this prompt.
- For an explicit image-generation request, use the separate `tyler-tee-image-generation.prompt.md` workflow; do not generate from this curation prompt.
- Do not edit the rejected-source list to hide a rejected concept; add a new curated entry only when it passes the brand and rights checks.
- Keep edits limited to the requested catalog entry unless a related schema correction is required and explicitly reported.

## Validation and response

After a change, read the result back through the helper and verify stable unique IDs, required fields, valid approval states, and provenance. Report:

- operation and ID
- whether the entry was created or changed and its catalog version
- validation result
- approval state
- files changed
- any unresolved human decision

If validation fails, do not leave a partial catalog edit or retry by changing the database directly. Never claim exact-image approval or commerce readiness from this workflow. For an explicit image-generation request, direct Tyler to the separate `tyler-tee-image-generation.prompt.md` workflow.
