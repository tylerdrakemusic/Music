---
name: ❤music-tee-merch
description: 'Tee merch catalog and artwork directives for ❤Music. Use when Tyler asks to create or edit a tee concept, generate artwork candidates from an approved concept, or decide on a generated candidate.'
---

# ❤music-tee-merch

Use these directives for Tyler James Drake tee merchandise. Keep concept curation and image generation distinct: catalog requests do not authorize image generation, and image requests do not authorize concept edits or image approval.

## Catalog directives

- Treat `tee_prompt_catalogs` and `tee_prompts` in `src/data/heartmusic.db` as canonical. Use `src.merch.tee_prompt_catalog.TeePromptCatalog` from the Music repository root. Do not use SQL, a catalog CLI, or the retired JSON catalog.
- Read and inspect records with `read_catalog()` and `read_prompt(prompt_id)`. Never silently substitute a different ID.
- If the request does not identify `create` or `edit`, or an edit's target ID, ask one concise clarification question before changing the catalog.
- Review `Brand/tyler-james-drake-merch-brand-system.md`, relevant concepts in `Brand/t-design prompts.txt`, and existing catalog entries before proposing a new concept. Preserve existing IDs; when a create request omits an ID, choose the next available `TJD-TEE-NNN` ID.
- Before creating an entry or changing `concept` or its depicted subject, show Tyler the complete proposed entry or revised concept and wait for explicit approval. Persist only with `approved_by_tyler=True` on the same catalog instance. Never infer approval from silence.
- Do not persist declined or unapproved proposals, and do not create rejected-source entries.
- For edits that do not change the core concept, pass only the requested fields so the catalog helper preserves unrelated values; these edits do not require concept reapproval. Preserve ID, provenance, metadata, and every unrequested field.
- After concept edits, repeat the rights, duplication, brand, and print-readiness checks.
- Keep concepts original to Tyler's music world, rights-aware, brand-consistent, and print-conscious. Reject recognizable artists, athletes, teams, logos, protected characters, and religious or cultural figures unless Tyler documents a separate license. Do not copy third-party marks, readable labels, signatures, or named artist likenesses.
- Preserve provenance. New concepts use `source: operator-authored` and identify the request in `source_entry`.
- Every entry must retain `id`, `title`, `concept`, `intended_garment_use`, `palette`, `print_notes`, `provenance`, `concept_revision`, `concept_approval_revision`, `concept_approval_status`, and `exact_image_approval_status`. Valid concept states are `concept_pending` and `concept_approved`; valid exact-image states are `not_started`, `exact_image_pending`, and `exact_image_approved`.
- Let the catalog helper own revision and approval transitions. Any change to `title`, `concept`, `intended_garment_use`, `palette`, or `print_notes` advances the semantic patch version and resets current exact-image approval to `not_started`. Retain prior approved assets and records. Never set approval states or revisions manually.
- After a catalog change, read the entry back and verify its ID, required fields, provenance, and approval states. Show the complete resulting entry and report the operation, ID, catalog version, validation result, approval state, changed files, and any unresolved human decision. Do not leave a partial edit or repair a failed catalog operation with direct database writes.

## Image-generation directives

- Generate candidates only when Tyler explicitly requests tee artwork from a catalog concept. Require a `TJD-TEE-NNN` catalog ID. Candidate count must be 1 through 4; if omitted, state that the default is 2 and get Tyler's authorization before running generation. The authorized count permits that many independent cascade calls and may incur provider costs. A new batch requires a new request.
- Read the requested concept through `TeePromptCatalog` before generation. Require `concept_approval_status: concept_approved` and matching `concept_revision` and `concept_approval_revision`. If either check fails, stop and explain that the concept must return to curation and receive explicit approval. Do not edit the catalog to make preflight pass.
- Start the chat-mediated batch from the Music repository root with the requested ID and authorized count:

  ```powershell
  C:\G\python.exe -m src.merch.tee_image_approval --chat-start --catalog-id TJD-TEE-001 --count 2
  ```

  Substitute Tyler's values. Use the current Music feature worktree when one is checked out. The module delegates candidates to the Workspace-owned cascade. If it is unavailable, report the configured `WORKSPACE_SRC` requirement; do not call providers directly or fall back to direct provider clients.
- The command stages the first successful candidate in an OS-temp session and returns its ID and image path. Display that image in chat before asking Tyler for an exact-image decision. Do not use terminal-interactive generation for agent-managed approvals.
- A generation request authorizes candidate generation only. Approve an image only after Tyler's explicit decision for that displayed candidate. Never infer approval from silence, generation, or approval of another candidate.
- Resolve only the matching candidate with the chat-decision command:

  ```powershell
  C:\G\python.exe -m src.merch.tee_image_approval --chat-decide --session-id <session-id> --candidate-id <candidate-id> --decision y
  ```

  Substitute the session ID, candidate ID, and Tyler's explicit `y` or `n`. Approval is valid only while the concept is approved, concept revisions match the staged revision, the image-prompt revision matches, and the generator prompt revision is unchanged. A catalog-version change alone does not invalidate the candidate. If a required revision changed, return to curation and start a new batch.
- A rejected candidate is discarded before another candidate is generated. Provider failures are not approval decisions. If Tyler cancels the remaining batch, discard its pending image and session with `--chat-cancel --session-id <session-id>`.
- Keep approved files and sidecars under ignored `output/images/tee-merch/<catalog-id>/<run-id>/`. Report generated, approved, rejected, and failed candidate counts. Do not create mockups, transparent artwork, product listings, or commerce output, and do not claim production or commerce readiness.

## Shared boundaries

- Do not generate images, select providers, render transparent artwork, create product listings, or publish commerce output as part of catalog curation.
- Do not edit a rejected-source list to hide a rejected concept. Add a new curated entry only when it passes the brand and rights checks.
- Keep changes limited to the requested catalog entry unless a related schema correction is required and explicitly reported.