# TODO 518 Finding Validation

FR: `FR-20260903-open-security-findings-all-repositories`
Project: `❤Music`
Child: `518`
Validation date: `2026-09-10` (amended recycled-light review)

## Inventory

The baseline inventory was read from the workspace `vulnerabilities` table with
`status = 'open'` and file paths under `f:\❤Music\`. Nine records were found.
No vulnerability record was changed during this validation.

| Finding | Severity | Location | Disposition | Evidence |
|---|---:|---|---|---|
| `02588e79880cbd29` | high | `tools/reconcile_heartmusic_db.py:96` | remediated | Dynamic table identifier is now validated and quoted before `SELECT *`. |
| `333266d641881717` | high | `tools/reconcile_heartmusic_db.py:77` | remediated | Dynamic table identifier is now validated and quoted before PRAGMA metadata lookup. |
| `9e83cf72df39d24c` | high | `tools/reconcile_heartmusic_db.py:82` | remediated | Dynamic table and column identifiers are now validated and quoted in row lookup. |
| `e24d83d5bec284e6` | high | `tools/reconcile_heartmusic_db.py:87` | remediated | Dynamic table and key-column identifiers are now validated and quoted in ID-map lookup. |
| `7b373142b6b79cad` | high | `src/utils/init_db.py:482` | false positive/tooling limitation | The flagged PRAGMA key is built from a runtime key, with apostrophes doubled before interpolation. SQLite PRAGMA key does not accept DB-API parameters. |
| `b3897a3f98aac7d1` | medium | `src/utils/init_db.py:482` | duplicate false positive/tooling limitation | Same source expression and same safe escaping as `7b373142b6b79cad`; this is the B608 companion finding. |
| `2eee90a0df5500d7` | low | `src/band_mgmt/generate_band_mgmt_panel.py:1324` | false positive/tooling limitation | The server binds a caller-selected local host and port; the URL is a local status message and API documentation string. |
| `b7b92c8a1a57c741` | low | `src/training/musician_training_ui.py:2160` | false positive/tooling limitation | The application defaults to `127.0.0.1`; the URL is a local startup message, not an outbound request. |
| `d51513208547e4a1` | low | `tests/test_band_mgmt_http_file_serve.py:239` | false positive/tooling limitation | The HTTP URL is an adversarial negative test input asserting that non-audio URLs do not match. |

## Remediation validation

The new regression tests in
`tests/test_security_reconciliation_identifiers.py` exercise hostile table
identifiers containing statement separators and SQL syntax. Before the fix,
the direct red probe reached SQLite and produced `ProgrammingError` or
`OperationalError`. After the fix, both inputs raise `ValueError`, and the
SQLite table remains intact.

The implementation validates identifiers against
`^[A-Za-z_][A-Za-z0-9_]*$` and emits quoted identifiers. Row values remain
DB-API parameters.

## Validation command notes

The prescribed project virtualenv does not include pytest or pip-audit. A
rerun from the remediation worktree confirmed that the focused security test
cannot start in the repository-scoped environment:
`F:\❤Music\.venv\Scripts\python.exe -m pytest
tests/test_security_reconciliation_identifiers.py -q` failed with
`No module named pytest`. The same environment reported
`No module named pip_audit`. No passing result is claimed for this rerun.

The tracked `.env` file was empty after the remediation change and has now
been removed from the child branch; its prior credential-bearing contents
were not restored, printed, or committed. Credential rotation or revocation
has not been performed by this workflow and remains an operator action
required outside the repository. The existing `.gitignore` already ignores
`.env` and `.env.local`.

## Reconciliation guard

This artifact is evidence only. It intentionally does not update central
vulnerability statuses, override notes, or remediation timestamps. Those
mutations must occur only after the child validation gate accepts this evidence.

## Amendment: post-snapshot findings

The three amended scanner IDs were inspected against the current branch source,
not just the reported line text:

| Finding | Current location | Disposition | Evidence |
|---|---|---|---|
| `0963a0e669d23f97` | `src/training/musician_training_ui.py:2187` | false positive/tooling limitation | The reported process launch is the `/launch` route. It accepts only an integer exercise ID, reads the exercise row by parameterized SQLite lookup, writes a fixed-name JSON file under `TRAINING_DIR`, and invokes a fixed `focused_musician_training.py` path with `shell=False` argument-list execution. The user-controlled values are serialized data, not PowerShell command text. |
| `9ea958a768d07907` | `tests/test_band_mgmt_http_file_serve.py:249` | false positive/tooling limitation | The reported line is the `TestPauseButtonUsesResolvedUrl` test class declaration. The nearby HTTP strings are adversarial test inputs and assertions; they are not requests made by production code. The test module also exercises encoded-path and traversal rejection for both file-serving endpoints. |
| `5bf9a4ee29cf49c4` | `src/band_mgmt/generate_band_mgmt_panel.py:1340` | false positive/tooling limitation | The reported line is the `argparse` declaration for an explicit CLI port value, with a `8765` default. The server default host is `127.0.0.1`; no external request is made by this declaration. File endpoints validate decoded paths against their configured roots before opening files. |

## Amendment validation

Focused executable checks from the isolated `fix/FR-20260903-open-security-findings`
worktree:

```text
pytest tests/test_band_mgmt_http_file_serve.py -q -k "resolve or JsUrlRewriting or AudioUrlRegex or PauseButton"
21 passed, 9 deselected

pytest tests/test_guitar_trainer_new_card_timestamps.py tests/test_guitar_trainer_exercise_audio.py tests/test_guitar_trainer_metronome.py -q
32 passed
```

The complete `test_band_mgmt_http_file_serve.py` module was also attempted. Its
first three tests passed, then the existing live-server fixture hung during
teardown and pytest ended with `KeyboardInterrupt`; this is recorded as a
validation blocker rather than a passing result. The deterministic subset
above completed successfully.

No production files were changed, no vulnerability record was mutated, and no
new finding status is claimed by this artifact.