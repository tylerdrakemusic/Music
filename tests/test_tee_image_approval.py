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
    assert manifest["approval"] == "approved"
    assert manifest["content_sha256"] == hashlib.sha256(b"image-1").hexdigest()
    assert "exact_prompt" in manifest
    assert not list(run_dir.glob("*rejected*"))

    updated_catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert updated_catalog["prompts"][0]["exact_image_approval_status"] == "exact_image_approved"


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
