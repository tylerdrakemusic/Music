# TODO 518 Finding Validation

FR: `FR-20260903-open-security-findings-all-repositories`
Project: `❤Music`
Child: `518`
Validation date: `2026-09-04`

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