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

From the Music repository root, read the requested concept through the catalog API:

```python
from contextlib import closing
from src.utils.init_db import get_connection
from src.merch.tee_prompt_catalog import TeePromptCatalog

with closing(get_connection()) as connection:
    prompt = TeePromptCatalog(connection).read_prompt(catalog_id)
```

Set `catalog_id` to Tyler's requested stable ID. Verify the returned record has
`concept_approval_status: concept_approved` and matching `concept_revision` and
`concept_approval_revision`. The generation command repeats this preflight
against the database before any provider call. If any check fails, do not run
generation; explain that the concept must return to curation and receive
explicit approval.

Do not edit the catalog to make preflight pass. Do not call an image provider directly, copy provider order into this prompt, or use the Vera portrait generator.

## Run

Start the chat-mediated batch from the Music repository root with the authorized ID and count:

```powershell
C:\G\python.exe -m src.merch.tee_image_approval --chat-start --catalog-id TJD-TEE-001 --count 2
```

Substitute Tyler's requested values. Use the current Music feature worktree when it is the checked-out workspace. The module delegates every candidate independently to the Workspace-owned cascade. If that cascade is unavailable, report the configured `WORKSPACE_SRC` requirement; do not fall back to direct provider clients.

The command stages only the first successful candidate in a random OS-temp session and prints JSON with its ID and image path. Its session records the catalog version, concept revision, and prompt revision used for generation. Use the image-view tool to display that path in chat before asking for an exact-image decision. Do not use terminal-interactive generation for agent-managed approvals.

## Exact-Image Decisions

After Tyler replies `y` or `n` for the displayed candidate, resolve only that image. An approval is accepted only if the concept, catalog version, and prompt revision still match the staged candidate. If any revision changed, return to curation and start a new batch; approval of a prior revision does not approve the changed prompt.

```powershell
C:\G\python.exe -m src.merch.tee_image_approval --chat-decide --session-id <session-id> --candidate-id <candidate-id> --decision y
```

Substitute only Tyler's explicit decision. Never infer approval from silence, generation, or approval of another candidate. Multiple candidates may be approved. An approval is persisted only after the matching chat decision; a rejection is discarded before another candidate is generated. The decision command returns the next candidate or a completion summary. If Tyler cancels the remaining batch, discard its pending image and session:

```powershell
C:\G\python.exe -m src.merch.tee_image_approval --chat-cancel --session-id <session-id>
```

Provider failures are not approval decisions. Let the script preserve their diagnostics, then report the number of generated, approved, rejected, and failed candidates. Approved files and sidecars are retained only under ignored `output/images/tee-merch/<catalog-id>/<run-id>/`.

Do not create mockups, transparent artwork, listings, or commerce output. Do not claim production or commerce readiness from an image approval.