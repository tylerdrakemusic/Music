"""Tests for operator-approved tee artwork generation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.merch.tee_image_approval import TeeImageApprovalFlow


def _catalog(path: Path, concept_status: str = "concept_approved") -> None:
    path.write_text(
        json.dumps(
            {
                "version": "1.2.0",
                "prompts": [
                    {
                        "id": "TJD-TEE-001",
                        "title": "Porchlight Blues",
                        "concept": "A fictional guitarist under a porchlight.",
                        "intended_garment_use": "Standalone tee artwork.",
                        "palette": ["black", "aged cream"],
                        "print_notes": "Opaque print, two spot colors.",
                        "concept_revision": 1,
                        "concept_approval_revision": 1,
                        "concept_approval_status": concept_status,
                        "exact_image_approval_status": "not_started",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


class FakeCascade:
    def __init__(self, failures: bool = False) -> None:
        self.calls: list[tuple[str, Path]] = []
        self.failures = failures

    def generate(self, prompt: str, *, output_dir: Path) -> SimpleNamespace:
        self.calls.append((prompt, output_dir))
        output_dir.mkdir(parents=True, exist_ok=True)
        candidate_path = output_dir / f"candidate-{len(self.calls)}.png"
        candidate_path.write_bytes(f"image-{len(self.calls)}".encode("ascii"))
        if self.failures:
            raise FakeGenerationError(
                "all fake providers failed",
                diagnostics=(
                    SimpleNamespace(provider="fake-one", model="fake-model", error="offline"),
                ),
            )
        return SimpleNamespace(
            path=candidate_path,
            provider="fake-provider",
            model="fake-model",
            diagnostics=(),
        )


class FakeGenerationError(Exception):
    def __init__(self, message: str, *, diagnostics: tuple[object, ...]) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics


def test_unapproved_concept_is_rejected_before_any_provider_call(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    _catalog(catalog_path, concept_status="concept_pending")
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(catalog_path, tmp_path / "output", cascade=cascade)

    with pytest.raises(ValueError, match="concept_approved"):
        flow.generate_batch("TJD-TEE-001")

    assert cascade.calls == []
    assert not (tmp_path / "output").exists()


def test_missing_concept_approval_revision_is_not_filled_by_generation(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog.json"
    _catalog(catalog_path)
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    del catalog["prompts"][0]["concept_approval_revision"]
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(catalog_path, tmp_path / "output", cascade=cascade)

    with pytest.raises(ValueError, match="approval revision"):
        flow.generate_batch("TJD-TEE-001", decide=lambda candidate: False)

    assert cascade.calls == []
    unchanged_catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert "concept_approval_revision" not in unchanged_catalog["prompts"][0]


def test_batch_persists_only_explicitly_approved_images_and_sidecars(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    output_root = tmp_path / "output" / "images" / "tee-merch"
    _catalog(catalog_path)
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(catalog_path, output_root, cascade=cascade)
    decisions = iter((True, False))

    run = flow.generate_batch(
        "TJD-TEE-001",
        decide=lambda candidate: next(decisions),
    )

    assert len(cascade.calls) == 2
    assert len(run.approved) == 1
    assert run.rejected_count == 1
    assert not hasattr(run, "rejected")
    assert cascade.calls[0][0] != "Porchlight Blues"
    assert all("TJD-TEE-001" in prompt for prompt, _ in cascade.calls)
    assert all("catalog revision" in prompt.lower() for prompt, _ in cascade.calls)
    assert cascade.calls[0][1] != cascade.calls[1][1]

    run_dir = output_root / "TJD-TEE-001" / run.run_id
    image_files = list(run_dir.glob("*.png"))
    sidecars = list(run_dir.glob("*.json"))
    assert len(image_files) == 1
    assert len(sidecars) == 1
    manifest = json.loads(sidecars[0].read_text(encoding="utf-8"))
    assert manifest["candidate_id"] == run.approved[0].candidate_id
    assert manifest["provider"] == "fake-provider"
    assert manifest["model"] == "fake-model"
    assert manifest["catalog_id"] == "TJD-TEE-001"
    assert manifest["catalog_revision"] == "1.2.0:1"
    assert manifest["prompt_revision"] == "tee-artwork-prompt-v2"
    assert manifest["approval"] == "approved"
    assert manifest["content_sha256"] == hashlib.sha256(b"image-1").hexdigest()
    assert "exact_prompt" in manifest
    assert manifest["exact_prompt"] == cascade.calls[0][0]
    assert not list(run_dir.glob("*rejected*"))

    updated_catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert updated_catalog["prompts"][0]["exact_image_approval_status"] == "exact_image_approved"


def test_batch_uses_distinct_art_directions_for_each_candidate(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    _catalog(catalog_path)
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(catalog_path, tmp_path / "output", cascade=cascade)

    flow.generate_batch(
        "TJD-TEE-001",
        count=4,
        decide=lambda candidate: False,
    )

    prompts = [prompt for prompt, _ in cascade.calls]
    directions = [prompt.splitlines()[0] for prompt in prompts]
    prefaces = [prompt.splitlines()[0].lower() for prompt in prompts]
    assert len(prompts) == 4
    assert len(set(directions)) == 4
    assert all("A fictional guitarist under a porchlight." in prompt for prompt in prompts)
    assert all("Catalog ID: TJD-TEE-001" in prompt for prompt in prompts)
    assert all("t-shirt design" in preface for preface in prefaces)
    style_markers = {"screen-print", "abstract", "line-work", "woodcut"}
    assert {style for preface in prefaces for style in style_markers if style in preface} == style_markers


def test_chat_batch_stages_one_candidate_without_approving_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.merch import tee_image_approval

    catalog_path = tmp_path / "catalog.json"
    output_root = tmp_path / "output"
    _catalog(catalog_path)
    monkeypatch.setattr(
        tee_image_approval,
        "_PENDING_ROOT",
        tmp_path / "pending",
        raising=False,
    )
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(catalog_path, output_root, cascade=cascade)

    stage = flow.start_chat_batch("TJD-TEE-001", count=2)

    candidate_path = Path(stage["image_path"])
    assert stage["status"] == "candidate_pending"
    assert stage["candidate_number"] == 1
    assert candidate_path.is_file()
    assert len(cascade.calls) == 1
    assert not output_root.exists()
    updated_catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert updated_catalog["prompts"][0]["exact_image_approval_status"] == "exact_image_pending"


def test_chat_rejection_discards_candidate_before_staging_the_next_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.merch import tee_image_approval

    catalog_path = tmp_path / "catalog.json"
    output_root = tmp_path / "output"
    _catalog(catalog_path)
    monkeypatch.setattr(
        tee_image_approval, "_PENDING_ROOT", tmp_path / "pending", raising=False
    )
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(catalog_path, output_root, cascade=cascade)
    first = flow.start_chat_batch("TJD-TEE-001", count=2)
    first_path = Path(first["image_path"])

    second = flow.decide_chat_candidate(
        first["session_id"], first["candidate_id"], decision="n"
    )

    assert second["status"] == "candidate_pending"
    assert second["candidate_number"] == 2
    assert not first_path.exists()
    assert Path(second["image_path"]).is_file()
    assert len(cascade.calls) == 2
    assert not output_root.exists()

    finished = flow.decide_chat_candidate(
        second["session_id"], second["candidate_id"], decision="n"
    )

    assert finished["status"] == "completed"
    assert finished["generated"] == 2
    assert finished["approved"] == 0
    assert finished["rejected"] == 2
    assert not Path(second["image_path"]).parent.exists()


def test_chat_approval_persists_only_after_explicit_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.merch import tee_image_approval

    catalog_path = tmp_path / "catalog.json"
    output_root = tmp_path / "output"
    _catalog(catalog_path)
    monkeypatch.setattr(
        tee_image_approval, "_PENDING_ROOT", tmp_path / "pending", raising=False
    )
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(catalog_path, output_root, cascade=cascade)
    stage = flow.start_chat_batch("TJD-TEE-001", count=1)
    pending_path = Path(stage["image_path"])
    assert not output_root.exists()

    finished = flow.decide_chat_candidate(
        stage["session_id"], stage["candidate_id"], decision="y"
    )

    run_dir = output_root / "TJD-TEE-001" / stage["run_id"]
    image_path = run_dir / f"{stage['candidate_id']}.png"
    sidecar_path = run_dir / f"{stage['candidate_id']}.json"
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    updated_catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert finished["status"] == "completed"
    assert finished["generated"] == 1
    assert finished["approved"] == 1
    assert finished["rejected"] == 0
    assert image_path.read_bytes() == b"image-1"
    assert not pending_path.exists()
    assert sidecar["approval"] == "approved"
    assert sidecar["exact_prompt"] == cascade.calls[0][0]
    assert sidecar["prompt_revision"] == "tee-artwork-prompt-v2"
    assert updated_catalog["prompts"][0]["exact_image_approval_status"] == "exact_image_approved"


def test_chat_decision_validates_session_candidate_and_choice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.merch import tee_image_approval

    catalog_path = tmp_path / "catalog.json"
    _catalog(catalog_path)
    monkeypatch.setattr(
        tee_image_approval, "_PENDING_ROOT", tmp_path / "pending", raising=False
    )
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(catalog_path, tmp_path / "output", cascade=cascade)
    stage = flow.start_chat_batch("TJD-TEE-001", count=1)
    pending_path = Path(stage["image_path"])

    with pytest.raises(ValueError, match="decision"):
        flow.decide_chat_candidate(stage["session_id"], stage["candidate_id"], decision="yes")
    with pytest.raises(ValueError, match="session ID"):
        flow.decide_chat_candidate("../outside", stage["candidate_id"], decision="n")
    with pytest.raises(ValueError, match="candidate"):
        flow.decide_chat_candidate(stage["session_id"], "other-candidate", decision="n")

    assert pending_path.is_file()
    assert not (tmp_path / "output").exists()
    flow.decide_chat_candidate(stage["session_id"], stage["candidate_id"], decision="n")


def test_chat_approval_is_blocked_if_concept_changes_while_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.merch import tee_image_approval

    catalog_path = tmp_path / "catalog.json"
    output_root = tmp_path / "output"
    _catalog(catalog_path)
    monkeypatch.setattr(
        tee_image_approval, "_PENDING_ROOT", tmp_path / "pending", raising=False
    )
    flow = TeeImageApprovalFlow(catalog_path, output_root, cascade=FakeCascade())
    stage = flow.start_chat_batch("TJD-TEE-001", count=1)
    pending_path = Path(stage["image_path"])
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["prompts"][0]["concept_revision"] = 2
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    with pytest.raises(ValueError, match="concept changed"):
        flow.decide_chat_candidate(stage["session_id"], stage["candidate_id"], decision="y")

    assert not pending_path.exists()
    assert not output_root.exists()


def test_chat_cancel_discards_pending_candidate_without_rejecting_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.merch import tee_image_approval

    catalog_path = tmp_path / "catalog.json"
    output_root = tmp_path / "output"
    _catalog(catalog_path)
    monkeypatch.setattr(
        tee_image_approval, "_PENDING_ROOT", tmp_path / "pending", raising=False
    )
    flow = TeeImageApprovalFlow(catalog_path, output_root, cascade=FakeCascade())
    stage = flow.start_chat_batch("TJD-TEE-001", count=2)
    pending_path = Path(stage["image_path"])

    result = flow.cancel_chat_batch(stage["session_id"])

    assert result["status"] == "cancelled"
    assert result["generated"] == 1
    assert result["approved"] == 0
    assert result["rejected"] == 0
    assert not pending_path.parent.exists()
    assert not output_root.exists()


def test_chat_start_cli_prints_candidate_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from src.merch import tee_image_approval

    catalog_path = tmp_path / "catalog.json"
    output_root = tmp_path / "output"
    pending_root = tmp_path / "pending"
    _catalog(catalog_path)
    monkeypatch.setattr(tee_image_approval, "_CATALOG_PATH", catalog_path)
    monkeypatch.setattr(tee_image_approval, "_OUTPUT_ROOT", output_root)
    monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", pending_root)
    monkeypatch.setattr(tee_image_approval, "_workspace_cascade", lambda workspace_src=None: FakeCascade())

    assert tee_image_approval.main(
        ["--chat-start", "--catalog-id", "TJD-TEE-001", "--count", "1"]
    ) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "candidate_pending"
    assert Path(result["image_path"]).is_file()
    flow = TeeImageApprovalFlow(catalog_path, output_root, pending_root=pending_root)
    flow.cancel_chat_batch(result["session_id"])


def test_chat_decide_cli_approves_exact_image_and_prints_next_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from src.merch import tee_image_approval

    catalog_path = tmp_path / "catalog.json"
    output_root = tmp_path / "output"
    pending_root = tmp_path / "pending"
    _catalog(catalog_path)
    monkeypatch.setattr(tee_image_approval, "_CATALOG_PATH", catalog_path)
    monkeypatch.setattr(tee_image_approval, "_OUTPUT_ROOT", output_root)
    monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", pending_root)
    monkeypatch.setattr(
        tee_image_approval,
        "_workspace_cascade",
        lambda workspace_src=None: FakeCascade(),
    )

    tee_image_approval.main(
        ["--chat-start", "--catalog-id", "TJD-TEE-001", "--count", "2"]
    )
    first = json.loads(capsys.readouterr().out)

    assert tee_image_approval.main(
        [
            "--chat-decide",
            "--session-id",
            first["session_id"],
            "--candidate-id",
            first["candidate_id"],
            "--decision",
            "y",
        ]
    ) == 0
    next_candidate = json.loads(capsys.readouterr().out)

    assert next_candidate["status"] == "candidate_pending"
    assert next_candidate["candidate_id"] != first["candidate_id"]
    approved_path = (
        output_root
        / "TJD-TEE-001"
        / first["run_id"]
        / f"{first['candidate_id']}{Path(first['image_path']).suffix}"
    )
    assert approved_path.is_file()
    flow = TeeImageApprovalFlow(catalog_path, output_root, pending_root=pending_root)
    flow.cancel_chat_batch(first["session_id"])


def test_batch_count_is_limited_to_one_through_four(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    _catalog(catalog_path)
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(catalog_path, tmp_path / "output", cascade=cascade)

    with pytest.raises(ValueError, match="1 and 4"):
        flow.generate_batch("TJD-TEE-001", count=5)
    with pytest.raises(ValueError, match="1 and 4"):
        flow.generate_batch("TJD-TEE-001", count=2.5)

    assert cascade.calls == []


def test_provider_failures_are_preserved_without_persisting_candidates(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    output_root = tmp_path / "output"
    _catalog(catalog_path)
    flow = TeeImageApprovalFlow(
        catalog_path,
        output_root,
        cascade=FakeCascade(failures=True),
    )

    run = flow.generate_batch("TJD-TEE-001", count=1)

    assert run.approved == ()
    assert len(run.failures) == 1
    run_dir = output_root / "TJD-TEE-001" / run.run_id
    diagnostics = json.loads((run_dir / "provider-failures.json").read_text(encoding="utf-8"))
    assert diagnostics[0]["diagnostics"][0]["provider"] == "fake-one"
    assert diagnostics[0]["diagnostics"][0]["error"] == "offline"
    assert not list(run_dir.glob("*.png"))
    updated_catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert updated_catalog["prompts"][0]["exact_image_approval_status"] == "exact_image_pending"


def test_catalog_revision_change_requires_concept_reapproval(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    _catalog(catalog_path)
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["prompts"][0]["concept_approval_revision"] = 1
    catalog["prompts"][0]["concept_revision"] = 2
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(catalog_path, tmp_path / "output", cascade=cascade)

    with pytest.raises(ValueError, match="reapproval"):
        flow.generate_batch("TJD-TEE-001")

    assert cascade.calls == []
    updated_catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert updated_catalog["prompts"][0]["concept_approval_status"] == "concept_pending"


def test_exact_image_approval_is_monotonic_across_batches(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    output_root = tmp_path / "output"
    _catalog(catalog_path)
    flow = TeeImageApprovalFlow(catalog_path, output_root, cascade=FakeCascade())
    first = flow.generate_batch("TJD-TEE-001", count=1, decide=lambda candidate: True)
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["prompts"][0]["exact_image_approval_status"] = "not_started"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    flow.generate_batch("TJD-TEE-001", count=1, decide=lambda candidate: False)

    updated_catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert first.approved
    assert updated_catalog["prompts"][0]["exact_image_approval_status"] == "exact_image_approved"


def test_multiple_images_can_be_approved_for_one_concept(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.json"
    _catalog(catalog_path)
    flow = TeeImageApprovalFlow(catalog_path, tmp_path / "output", cascade=FakeCascade())

    run = flow.generate_batch(
        "TJD-TEE-001",
        count=2,
        decide=lambda candidate: True,
    )

    assert len(run.approved) == 2
    assert len(list((tmp_path / "output" / "TJD-TEE-001" / run.run_id).glob("*.png"))) == 2


def test_default_workspace_cascade_loads_from_configured_src_without_generation(
    tmp_path: Path,
) -> None:
    from src.merch.tee_image_approval import _workspace_cascade

    workspace_src = tmp_path / "workspace" / "src"
    integration_dir = workspace_src / "integrations"
    integration_dir.mkdir(parents=True)
    (integration_dir / "image_cascade.py").write_text(
        "class Cascade:\n"
        "    def generate(self, prompt, *, output_dir=None):\n"
        "        raise AssertionError('generation must not run in this test')\n"
        "\n"
        "def default_image_cascade():\n"
        "    return Cascade()\n",
        encoding="utf-8",
    )

    cascade = _workspace_cascade(workspace_src)

    assert callable(cascade.generate)


def test_default_workspace_source_resolves_feature_worktree_before_canonical_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.merch import tee_image_approval

    workspace_root = tmp_path / "workspace"
    feature_src = (
        workspace_root
        / ".worktrees"
        / "FR-20260927-tee-image-generation-approval"
        / "workspace"
        / "src"
    )
    canonical_src = workspace_root / "src"
    for source in (feature_src, canonical_src):
        integration_dir = source / "integrations"
        integration_dir.mkdir(parents=True)
        (integration_dir / "image_cascade.py").touch()

    monkeypatch.delenv("WORKSPACE_SRC", raising=False)
    monkeypatch.setattr(tee_image_approval, "_WORKSPACE_ROOT", workspace_root)
    monkeypatch.setattr(tee_image_approval, "_FEATURE_WORKSPACE_SRC", feature_src)

    assert tee_image_approval._resolve_workspace_src() == feature_src
