"""Contract tests for paired Music and Workspace revisions in CI."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TEST_WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"
STUDIO_WORKFLOW = ROOT / ".github" / "workflows" / "deploy-hyperthreat-studio.yml"
FLYCTL_ACTION = "superfly/flyctl-actions/setup-flyctl@ed8efb33836e8b2096c7fd3ba1c8afe303ebbff1"


def _bash_executable() -> str | None:
    if os.name == "nt":
        candidates = (
            Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git" / "bin" / "bash.exe",
            Path("C:/Program Files/Git/bin/bash.exe"),
        )
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
    return shutil.which("bash")


def _shell_path(path: Path, bash: str) -> str:
    if os.name != "nt":
        return str(path)
    converted = subprocess.run(
        [bash, "-lc", 'cygpath -u "$1"', "bash", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return converted.stdout.strip()


def _step_script(workflow: str, step_name: str) -> str:
    step_start = workflow.index(f"      - name: {step_name}\n")
    run_start = workflow.index("        run: |\n", step_start) + len("        run: |\n")
    next_step = workflow.find("\n      - ", run_start)
    if next_step == -1:
        next_step = len(workflow)
    return "\n".join(line[10:] for line in workflow[run_start:next_step].splitlines())


def _run_resolution_step(
    tmp_path: Path,
    lookup_mode: str,
    event_name: str = "pull_request",
    pr_head_ref: str = "feature/paired-revision",
) -> tuple[subprocess.CompletedProcess[str], Path, Path, Path]:
    bash = _bash_executable()
    if bash is None:
        pytest.skip("Bash is required to exercise the workflow resolution step")

    workflow = TEST_WORKFLOW.read_text(encoding="utf-8")
    resolution_script = (
        "set -euo pipefail\n"
        "git() {\n"
        '  local ref count count_file\n'
        '  ref="${@: -1}"\n'
        '  case "$ref" in\n'
        '    refs/heads/feature/paired-revision)\n'
        '      count_file="$PR_LOOKUP_COUNT_FILE"\n'
        '      count=0\n'
        '      [[ ! -f "$count_file" ]] || count=$(<"$count_file")\n'
        '      count=$((count + 1))\n'
        '      printf "%s" "$count" > "$count_file"\n'
        '      if [[ "$LOOKUP_MODE" == "no_match" ]]; then return 2; fi\n'
        '      if [[ "$LOOKUP_MODE" == "exhaust" || ( "$LOOKUP_MODE" == "transient" && "$count" -lt 3 ) ]]; then return 1; fi\n'
        '      printf "%s\\t%s\\n" "$PR_SHA" "$ref" ;;\n'
        '    refs/heads/main)\n'
        '      count_file="$DEFAULT_LOOKUP_COUNT_FILE"\n'
        '      count=0\n'
        '      [[ ! -f "$count_file" ]] || count=$(<"$count_file")\n'
        '      count=$((count + 1))\n'
        '      printf "%s" "$count" > "$count_file"\n'
        '      printf "%s\\t%s\\n" "$DEFAULT_SHA" "$ref" ;;\n'
        '    *) return 64 ;;\n'
        '  esac\n'
        "}\n"
        + _step_script(workflow, "Resolve Workspace peer revision")
    ).replace("sleep 1", ":")
    output = tmp_path / "github-output"
    pr_count = tmp_path / "pr-lookup-count"
    default_count = tmp_path / "default-lookup-count"
    env = os.environ.copy()
    env.update(
        {
            "DEFAULT_LOOKUP_COUNT_FILE": _shell_path(default_count, bash),
            "DEFAULT_SHA": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "EVENT_NAME": event_name,
            "GITHUB_OUTPUT": _shell_path(output, bash),
            "LOOKUP_MODE": lookup_mode,
            "PR_HEAD_REF": pr_head_ref,
            "PR_LOOKUP_COUNT_FILE": _shell_path(pr_count, bash),
            "PR_SHA": "0123456789abcdef0123456789abcdef01234567",
        }
    )
    result = subprocess.run(
        [bash, "--noprofile", "--norc", "-e", "-u", "-o", "pipefail", "-c", resolution_script],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    return result, output, pr_count, default_count


def _workflow_outputs(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines())


def test_ci_resolves_and_checks_out_workspace_commit_before_running_tests():
    workflow = TEST_WORKFLOW.read_text(encoding="utf-8")

    resolve_step = workflow.index("name: Resolve Workspace peer revision")
    checkout_step = workflow.index("name: Check out Workspace peer revision")
    tests_step = workflow.index("name: Run bounded parallel and serial pytest lanes")

    assert resolve_step < checkout_step < tests_step
    assert "repository=tylerdrakemusic/-Workspace" in workflow
    assert "EVENT_NAME: ${{ github.event_name }}" in workflow
    assert "PR_HEAD_REF: ${{ github.head_ref }}" in workflow
    assert "git ls-remote --exit-code --heads" in workflow
    assert workflow.count("for attempt in 1 2 3; do") == 2
    assert "sleep 1" in workflow
    assert 'if [ "$lookup_status" -ne 2 ]; then' in workflow
    assert 'fallback="main (PR ref $PR_HEAD_REF not found)"' in workflow
    assert 'fetch --no-tags --depth=1 origin "$REVISION_SHA"' in workflow
    assert 'checkout --detach "$REVISION_SHA"' in workflow
    assert 'rev-parse HEAD' in workflow
    assert "$GITHUB_STEP_SUMMARY" in workflow
    assert "Peer repository:" in workflow
    assert "Selected ref:" in workflow
    assert "Checked-out SHA:" in workflow


def test_both_deploy_workflows_pin_the_approved_flyctl_action_revision():
    for workflow_path in (TEST_WORKFLOW, STUDIO_WORKFLOW):
        workflow = workflow_path.read_text(encoding="utf-8")

        assert f"uses: {FLYCTL_ACTION}" in workflow
        assert f"uses: {FLYCTL_ACTION}\n        with:\n          version: 0.4.111" in workflow
        assert "superfly/flyctl-actions/setup-flyctl@master" not in workflow


@pytest.mark.parametrize("workflow_path", (TEST_WORKFLOW, STUDIO_WORKFLOW))
def test_checkout_actions_have_read_only_permissions_and_do_not_persist_credentials(
    workflow_path: Path,
):
    workflow = workflow_path.read_text(encoding="utf-8")
    checkout_steps = re.findall(
        r"(?ms)^      - uses: actions/checkout@[^\n]*\n(.*?)(?=^      - |\Z)",
        workflow,
    )

    assert re.search(r"(?m)^permissions:\n  contents: read$", workflow)
    assert checkout_steps
    assert all(
        re.search(r"(?m)^          persist-credentials: false$", step)
        for step in checkout_steps
    )


def test_pr_resolution_retries_and_selects_the_exact_matching_peer_sha(tmp_path: Path):
    result, output, pr_count, default_count = _run_resolution_step(tmp_path, "transient")

    assert result.returncode == 0, result.stderr
    assert pr_count.read_text(encoding="utf-8") == "3"
    assert not default_count.exists()
    assert _workflow_outputs(output) == {
        "repository": "tylerdrakemusic/-Workspace",
        "selected_ref": "feature/paired-revision",
        "fallback": "none",
        "revision_sha": "0123456789abcdef0123456789abcdef01234567",
    }


def test_pr_resolution_uses_default_only_after_confirmed_peer_ref_absence(tmp_path: Path):
    result, output, pr_count, default_count = _run_resolution_step(tmp_path, "no_match")

    assert result.returncode == 0, result.stderr
    assert pr_count.read_text(encoding="utf-8") == "1"
    assert default_count.read_text(encoding="utf-8") == "1"
    assert _workflow_outputs(output)["selected_ref"] == "main"
    assert _workflow_outputs(output)["fallback"] == "main (PR ref feature/paired-revision not found)"
    assert _workflow_outputs(output)["revision_sha"] == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def test_non_pr_resolution_uses_peer_default_without_fallback(tmp_path: Path):
    result, output, pr_count, default_count = _run_resolution_step(
        tmp_path,
        "default",
        event_name="push",
        pr_head_ref="",
    )

    assert result.returncode == 0, result.stderr
    assert not pr_count.exists()
    assert default_count.read_text(encoding="utf-8") == "1"
    assert _workflow_outputs(output)["selected_ref"] == "main"
    assert _workflow_outputs(output)["fallback"] == "none"
    assert _workflow_outputs(output)["revision_sha"] == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def test_transient_pr_lookup_exhaustion_does_not_fall_back_to_default(tmp_path: Path):
    result, output, pr_count, default_count = _run_resolution_step(tmp_path, "exhaust")

    assert result.returncode != 0
    assert "lookup exhausted retries" in result.stderr
    assert pr_count.read_text(encoding="utf-8") == "3"
    assert not default_count.exists()
    assert not output.exists()


@pytest.mark.parametrize(
    ("checkout_always_fails", "selected_ref", "fallback"),
    (
        (False, "feature/paired-revision", "none"),
        (False, "main", "main (PR ref feature/paired-revision not found)"),
        (True, "feature/paired-revision", "none"),
    ),
)
def test_peer_checkout_retries_transient_git_checkout_errors_and_reports_exact_sha(
    tmp_path: Path,
    checkout_always_fails: bool,
    selected_ref: str,
    fallback: str,
):
    bash = _bash_executable()
    if bash is None:
        pytest.skip("Bash is required to exercise the workflow checkout step")

    workflow = TEST_WORKFLOW.read_text(encoding="utf-8")
    checkout_script = (
        "git() {\n"
        '  if [[ "$1" == "-C" ]]; then shift 2; fi\n'
        '  case "$1" in\n'
        '    init|remote|fetch) return 0 ;;\n'
        '    checkout)\n'
        '      count=0\n'
        '      [[ ! -f "$CHECKOUT_COUNT_FILE" ]] || count=$(<"$CHECKOUT_COUNT_FILE")\n'
        '      count=$((count + 1))\n'
        '      printf "%s" "$count" > "$CHECKOUT_COUNT_FILE"\n'
        '      if [[ "$CHECKOUT_ALWAYS_FAILS" == true || "$count" -lt 3 ]]; then return 17; fi\n'
        '      return 0 ;;\n'
        '    rev-parse) printf "%s\\n" "$REVISION_SHA" ;;\n'
        '    *) return 64 ;;\n'
        '  esac\n'
        "}\n"
        + _step_script(workflow, "Check out Workspace peer revision")
    ).replace("sleep 1", ":")
    checkout_count = tmp_path / "checkout-count"
    summary = tmp_path / "summary.md"
    summary.touch()

    env = os.environ.copy()
    env.update(
        {
            "CHECKOUT_COUNT_FILE": _shell_path(checkout_count, bash),
            "CHECKOUT_ALWAYS_FAILS": str(checkout_always_fails).lower(),
            "FALLBACK": fallback,
            "GITHUB_STEP_SUMMARY": _shell_path(summary, bash),
            "GITHUB_WORKSPACE": _shell_path(tmp_path, bash),
            "REVISION_SHA": "0123456789abcdef0123456789abcdef01234567",
            "SELECTED_REF": selected_ref,
            "WORKSPACE_REPOSITORY": "tylerdrakemusic/-Workspace",
        }
    )
    result = subprocess.run(
        [bash, "--noprofile", "--norc", "-e", "-u", "-o", "pipefail", "-c", checkout_script],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )

    assert checkout_count.read_text(encoding="utf-8") == "3"
    if checkout_always_fails:
        assert result.returncode != 0
        assert "Workspace peer checkout exhausted retries." in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        summary_text = summary.read_text(encoding="utf-8")
        assert "- Peer repository: tylerdrakemusic/-Workspace" in summary_text
        assert f"- Selected ref: {selected_ref}" in summary_text
        assert f"- Fallback: {fallback}" in summary_text
        assert "- Checked-out SHA: 0123456789abcdef0123456789abcdef01234567" in summary_text


def test_existing_test_and_studio_deploy_gates_remain_intact():
    test_workflow = TEST_WORKFLOW.read_text(encoding="utf-8")
    studio_workflow = STUDIO_WORKFLOW.read_text(encoding="utf-8")

    assert "branches: [main]" in test_workflow
    assert "if: github.ref == 'refs/heads/main'" in test_workflow
    assert "flyctl deploy --remote-only --app guitartrainer" in test_workflow
    assert "FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}" in test_workflow
    assert "github.ref == 'refs/heads/main'" in studio_workflow
    assert "inputs.approval == 'approved'" in studio_workflow
    assert "flyctl deploy --app \"$APP_NAME\" --config fly.hyperthreat-studio.toml --remote-only" in studio_workflow
    assert "FLY_API_TOKEN: ${{ secrets.HT_FLY_TOKEN }}" in studio_workflow