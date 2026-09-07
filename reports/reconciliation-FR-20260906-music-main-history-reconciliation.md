# Music Main History Reconciliation

Date: 2026-09-06
FR: FR-20260906-music-main-history-reconciliation

## Topology

The feature worktree was initially based on `origin/main` at `a6f9131` and
contained the policy commit `e835835`. It now contains a non-fast-forward
merge of local `main` at `abe8bae`, with reconciliation head
`bcd5204f9547db62b7d2dfb835a3cce222bd61ed`. The merge preserves all 467
local-main commits beyond `origin/main`; the reconciled branch is 469 commits
ahead of `origin/main` (467 local-main commits, the policy commit, and the
reconciliation merge commit). No history was rewritten and no historical path
was deleted. The eventual delivery is one pull request targeting `main`; no
force-push is part of this change.

The untracked
`bands/copperCreek/branding/2026-08-23-wide-open-saloon/videos/` directory is intentionally
ignored for this reconciliation and is not added to the repository. The rule
is path-scoped. The approved named file `HelixFiles/Rocky Mountain W.hlx` is
explicitly eligible for tracking; no exception is claimed for invented nested
paths under the ignored CopperCreek directory.

The original local `main` checkout also has three untracked asset paths:
`HelixFiles/Rocky Mountain W.hlx`,
`catalog/artwork/originals/Invisible-Cropped.jpg`, and
`catalog/artwork/originals/Invisible.jpg`. They were not part of the approved
467-commit history and were not copied, staged, or committed into the feature
worktree.

## File dispositions

| Area | Disposition | Evidence or follow-up |
| --- | --- | --- |
| `catalog/artwork/originals/Invisible*.jpg` | Present only as untracked files in the original local `main` checkout. | Not copied, staged, or deleted. Any future import or removal requires explicit path-level approval. |
| CopperCreek branding video directory, `bands/copperCreek/branding/2026-08-23-wide-open-saloon/videos/` | Ignore as untracked source material. | Not staged or committed. |
| `.hlx` files | Eligible for tracking. | No blanket `*.hlx` ignore rule was added. Preserve and classify `HelixFiles/Rocky Mountain W.hlx` if it is present in a later local-main path review. |
| `catalog/visualizers/you_already_know_visualized.webm` | Existing tracked oversized file, 61,169,583 bytes (about 58.3 MiB). | Below the 100 MiB blocking threshold, so retained without history rewrite. Requires explicit path-level approval before any future removal or migration. |
| Databases, generated output, temporary files, and media | Do not commit unless an existing repository rule explicitly permits the file. | Current `.gitignore` rules remain authoritative. |

## Size policy

The existing test workflow now checks tracked files after checkout by invoking
`.github/scripts/check_tracked_file_sizes.sh`:

- At or above 50 MiB: emit a GitHub Actions warning for review.
- At or above 100 MiB: emit an error and fail the job.

The check uses Git's tracked-file list, so untracked local assets cannot enter a
pull request accidentally through this policy step. It does not rewrite history
or remove an existing blob. The `.gitignore` file does not contain a blanket
`*.hlx` rule; its CopperCreek rule ignores only the requested branding-video
directory, while the approved root-level Helix path has an explicit named
exception.

## Validation

Commands run during reconciliation:

```text
git rev-list --count a6f9131..main
git diff --stat a6f9131..main
C:\G\python.exe -m pytest -q tests/test_history_reconciliation_policy.py
git diff --check
C:\G\python.exe -m pytest -q
```

The executable policy tests invoke `git check-ignore --no-index` to verify that
the approved root-level Helix path is eligible, that a CopperCreek branding
video is ignored, and that a nested CopperCreek `.hlx` path remains ignored
under the parent-directory rule. They also verify that an exactly 50 MiB
tracked file emits a warning without failing and that an exactly 100 MiB tracked
file emits an error and fails. The current-worktree scan found one tracked file
at or above 50 MiB,
`catalog/visualizers/you_already_know_visualized.webm`, at 61,169,583 bytes.
It found no file at or above 100 MiB and no
`catalog/artwork/originals/Invisible*.jpg` files. The focused contract test is
the executable guard for this report and workflow policy. The full Music suite
was also run after the history merge; its result is recorded in the FR ledger
and in the delivery summary.

## Residual risks

- The 467 local-main commits are preserved as reachable history in the feature
  branch. Any future selective migration, removal, or rewrite still requires
  Tyler's explicit path-level history approval.
- A worktree scan cannot establish provenance for files that are absent here.
- The CI size check covers tracked files at checkout time; it is not a complete
  historical Git object audit or a secret scanner.
- No path was deleted, so any accidentally committed local-main path remains
  available for a later, explicitly approved reconciliation pass.

## Tyler approval required

Tyler must approve any future path-level history action involving the 467
local-main commits or the existing tracked
`catalog/visualizers/you_already_know_visualized.webm` blob. This pass leaves
both intact.