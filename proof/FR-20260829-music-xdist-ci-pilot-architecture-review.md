# Architecture Impact Report: FR-20260829-music-xdist-ci-pilot

**Decision:** PASS_WITH_UPDATES

## Scope

The complete worktree diff is limited to the ❤Music repository. It changes
the Music CI workflow, pytest marker declarations, parallel test policy,
test runner, and focused tests. There are no cross-project imports, new
integrations, database changes, new dependencies, or agent changes.

## Impact Review

| File in diff | Impact type | Affected diagram |
| --- | --- | --- |
| `.github/workflows/test.yml` | CI lane and JUnit artifact contract | `diagrams/music-tech-stack.mmd` |
| `pytest.ini` | New `serial_only` marker contract | `diagrams/music-tech-stack.mmd` |
| `tools/parallel_test_policy.json` | Enables bounded parallel CI and declares serial paths | `diagrams/music-tech-stack.mmd` |
| `tools/run_tests.py` | Adds two-lane runner, worker bound, marker routing, and reports | `diagrams/music-tech-stack.mmd` |
| `tests/test_ci_exclusion_policy.py` | Workflow contract coverage | `diagrams/music-tech-stack.mmd` |
| `tests/test_guitar_trainer_exercise_audio.py` | Marks audio tests serial-only | `diagrams/music-tech-stack.mmd` |
| `tests/test_parallel_runner_contract.py` | Runner and lane contract coverage | `diagrams/music-tech-stack.mmd` |

## Diagram Status

| Diagram | Status | Notes |
| --- | --- | --- |
| `diagrams/music-tech-stack.mmd` | CURRENT | The diagram describes the bounded two-worker CI lane, the serial lane, the `serial_only` policy, split JUnit artifacts, and rollback behavior. It is present as an intended untracked handoff file and must be included by CI. |
| `diagrams/music-architecture.mmd` | No update required | No test-runner or CI architecture element is represented there. It is already over the overview node budget (`88 > 40`), but that is pre-existing and unrelated to this FR. |

The affected technology-stack source measures 3,156 UTF-8 characters, 3,174
UTF-8 bytes, 23 nodes, and 23 edges. All are within the technology-stack
budgets of 8,000 characters, 12,000 bytes, 30 nodes, and 40 edges, so no split
is required. Its recorded renderer evidence is `mermaid.ink HTTP 200`; no
`mmdc` backend is installed, so local renderer evidence is `NOT RUN`.

The mandatory workspace-agent topology check is a workspace-wide invariant and
reported missing agent nodes outside the Music-only change surface. That
finding is unrelated to this FR, so no workspace topology rewrite is included;
scope containment is preserved. The Music technology-stack diagram is current
for this FR.

## Behavioral Risk Notes

- Focused validation passed: 13 tests passed. The runner also passed three
  paired pilots with 735 parallel tests, five serial audio tests, two workers,
  and both JUnit outputs present.
- `pytest-xdist>=3.6,<4.0` is already present in `requirements.txt`, so the
  CI install path supplies the parallel plugin.
- The legacy `tools/run_tests.py --junitxml PATH` interface is accepted but
  ignored when the new default two-lane mode is used. This is a compatibility
  risk for callers that still expect one report at the requested path.
- The `parallel_ci` policy field is declarative only; the runner does not read
  it to decide whether to execute the parallel lane. Turning that field off
  alone is therefore not a rollback mechanism.
- Lane ordering is fail-visible: the serial lane runs after a parallel
  failure, and the first non-zero exit code is returned. The workflow uploads
  both lane paths with `if: always()`, but a runner startup failure before
  either pytest process creates a report can leave an upload path absent.
- The serial path and JUnit paths are relative to the process working
  directory. CI invokes the runner from the repository root, which is covered
  by the pilot evidence; callers from another directory would need an
  explicit working-directory contract.

## Remediation

The Music diagram update is complete. CI must include the intended implementation
files and this reviewable proof in the handoff, then rerun the architecture
check against the implementation commit. The unrelated workspace topology
finding remains out of scope for this Music-only FR.