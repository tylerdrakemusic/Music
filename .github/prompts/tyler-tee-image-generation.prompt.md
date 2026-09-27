---
name: "Tyler Tee Image Generation"
description: "Generate and review exact tee-art candidates from an approved catalog concept. Use when asked to generate tee artwork or tee image candidates."
argument-hint: "Catalog ID and candidate count (1-4, default 2)"
agent: "agent"
---

# Tyler Tee Image Generation

Use this prompt only for generating candidate images from the existing approved tee prompt catalog. Keep concept authoring and editing in `tyler-merch-prompt-catalog.prompt.md`.

## Request and Authorization

Extract the stable catalog ID and candidate count from Tyler's request.

- Require a catalog ID in `TJD-TEE-NNN` form. If missing, ask which concept to use.
- Candidate count must be an integer from 1 through 4. If omitted, explain that the default is 2 and ask Tyler to authorize two candidates before running the script.
- The authorized count permits that many independent image-cascade calls and may incur provider costs. Do not run an additional batch without a new request.
- A generation request authorizes candidate generation only. It does not authorize approving any image.

## Preflight

From the Music repository root, inspect `Brand/tyler-james-drake-tee-prompt-catalog.json` and verify the requested entry exists, has `concept_approval_status: concept_approved`, and has matching `concept_revision` and `concept_approval_revision`. If any check fails, do not run the script; explain that the concept must return to curation and receive explicit approval.

Do not edit the catalog to make preflight pass. Do not call an image provider directly, copy provider order into this prompt, or use the Vera portrait generator.

## Run

Run the Music module from the Music repository root with the authorized ID and count:

```powershell
C:\G\python.exe -m src.merch.tee_image_approval --catalog-id TJD-TEE-001 --count 2
```

Substitute Tyler's requested values. Use the current Music feature worktree when it is the checked-out workspace. The module delegates every candidate independently to the Workspace-owned cascade. If that cascade is unavailable, report the configured `WORKSPACE_SRC` requirement; do not fall back to direct provider clients.

## Exact-Image Decisions

The script presents each successful candidate separately and asks `Approve this exact image? [y/n]`. Show/open that candidate for Tyler and obtain a decision for that specific image. Enter only Tyler's explicit `y` or `n`; never infer approval from silence, generation, or approval of another candidate. Multiple candidates may be approved. Rejected candidate files and rejection records are discarded by the script.

Provider failures are not approval decisions. Let the script preserve their diagnostics, then report the number of generated, approved, rejected, and failed candidates. Approved files and sidecars are retained only under ignored `output/images/tee-merch/<catalog-id>/<run-id>/`.

Do not create mockups, transparent artwork, listings, or commerce output. Do not claim production or commerce readiness from an image approval.