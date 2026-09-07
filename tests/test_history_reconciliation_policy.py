"""Contracts for the Music history reconciliation report and size policy."""

import os
import shutil
import stat
import subprocess
from uuid import uuid4
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "reconciliation-FR-20260906-music-main-history-reconciliation.md"
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"
SIZE_POLICY = ROOT / ".github" / "scripts" / "check_tracked_file_sizes.sh"
BRANDING_VIDEO_PATH = "bands/copperCreek/branding/2026-08-23-wide-open-saloon/videos/"
APPROVED_HELIX_PATH = "HelixFiles/Rocky Mountain W.hlx"
IGNORED_BRANDING_VIDEO_PATH = f"{BRANDING_VIDEO_PATH}teaser.mp4"
IGNORED_BRANDING_HELIX_PATH = f"{BRANDING_VIDEO_PATH}nested/Rocky Mountain W.hlx"


def run_size_policy(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            ".github/scripts/check_tracked_file_sizes.sh",
            str(repo.relative_to(ROOT)).replace("\\", "/"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def remove_test_repo(repo: Path) -> None:
    def make_writable(function, path, _error):
        os.chmod(path, stat.S_IWRITE)
        function(path)

    shutil.rmtree(repo, onerror=make_writable)


def test_reconciliation_report_records_required_dispositions_and_policy():
    report = REPORT.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    for marker in (
        "467 local-main commits",
        "CopperCreek branding video",
        "Invisible*.jpg",
        "HelixFiles/Rocky Mountain W.hlx",
        "you_already_know_visualized.webm",
        "50 MiB",
        "100 MiB",
        "Residual risks",
    ):
        assert marker in report

    assert str(SIZE_POLICY.relative_to(ROOT)).replace("\\", "/") in workflow
    assert f"{BRANDING_VIDEO_PATH}*" in gitignore
    assert f"!{APPROVED_HELIX_PATH}" in gitignore
    assert "\n*.hlx\n" not in gitignore


def test_gitignore_allows_the_approved_root_helix_file_only():
    approved = subprocess.run(
        ["git", "check-ignore", "--no-index", "--", APPROVED_HELIX_PATH],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    branding_video = subprocess.run(
        ["git", "check-ignore", "--no-index", "--", IGNORED_BRANDING_VIDEO_PATH],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    nested_branding_helix = subprocess.run(
        ["git", "check-ignore", "--no-index", "--", IGNORED_BRANDING_HELIX_PATH],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert approved.returncode == 1, approved.stdout + approved.stderr
    assert branding_video.returncode == 0, branding_video.stdout + branding_video.stderr
    assert nested_branding_helix.returncode == 0, (
        nested_branding_helix.stdout + nested_branding_helix.stderr
    )


def test_size_policy_warns_at_50_mib(tmp_path):
    repo = ROOT / "tmp" / f"size-policy-{tmp_path.name}-{uuid4().hex}"
    repo.mkdir(parents=True)
    try:
        (repo / "warning.bin").write_bytes(b"0" * (50 * 1024 * 1024))
        subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "warning.bin"], check=True)

        result = run_size_policy(repo)
    finally:
        remove_test_repo(repo)

    assert result.returncode == 0
    assert "::warning" in result.stdout
    assert "warning.bin" in result.stdout


def test_size_policy_blocks_at_100_mib(tmp_path):
    repo = ROOT / "tmp" / f"size-policy-{tmp_path.name}-{uuid4().hex}"
    repo.mkdir(parents=True)
    try:
        (repo / "blocking.bin").write_bytes(b"0" * (100 * 1024 * 1024))
        subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "blocking.bin"], check=True)

        result = run_size_policy(repo)
    finally:
        remove_test_repo(repo)

    assert result.returncode != 0
    assert "::error" in result.stdout
    assert "blocking.bin" in result.stdout
