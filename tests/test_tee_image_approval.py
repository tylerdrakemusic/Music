"""Tests for operator-approved tee artwork generation."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.merch.tee_prompt_catalog import TeePromptCatalog
from src.merch.tee_image_approval import TeeImageApprovalFlow, TeeImageCandidate
from src.utils import init_db


def _in_memory_catalog(
    database_path: str | Path = ":memory:",
) -> tuple[sqlite3.Connection, TeePromptCatalog]:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(init_db._SCHEMA_SQL)
    init_db.import_tee_catalog_bootstrap(connection)
    return connection, TeePromptCatalog(connection)


def _open_test_catalog(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


@pytest.fixture
def db_catalog() -> tuple[TeePromptCatalog, sqlite3.Connection]:
    connection, catalog = _in_memory_catalog()
    yield catalog, connection
    connection.close()


class FakeCascade:
    def __init__(self, failures: bool = False) -> None:
        self.calls: list[tuple[str, Path]] = []
        self.failures = failures

    def generate(self, prompt: str, *, output_dir: Path) -> SimpleNamespace:
        self.calls.append((prompt, output_dir))
        output_dir.mkdir(parents=True, exist_ok=True)
        candidate_path = output_dir / f"candidate-{len(self.calls)}.png"
        candidate_path.write_bytes(
            b"\x89PNG\r\n\x1a\n" + f"image-{len(self.calls)}".encode("ascii")
        )
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


def test_unapproved_concept_is_rejected_before_any_provider_call(
    tmp_path: Path, db_catalog: tuple[TeePromptCatalog, sqlite3.Connection]
) -> None:
    catalog, connection = db_catalog
    connection.execute(
        "UPDATE tee_prompts SET concept_approval_status = 'concept_pending' WHERE id = ?",
        ("TJD-TEE-001",),
    )
    connection.commit()
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(catalog, tmp_path / "output", cascade=cascade)

    with pytest.raises(ValueError, match="concept_approved"):
        flow.generate_batch("TJD-TEE-001")

    assert cascade.calls == []
    assert not (tmp_path / "output").exists()


def test_missing_concept_approval_revision_is_not_filled_by_generation(
    tmp_path: Path, db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    catalog, connection = db_catalog
    connection.execute(
        "UPDATE tee_prompts SET concept_approval_revision = NULL WHERE id = ?",
        ("TJD-TEE-001",),
    )
    connection.commit()
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(catalog, tmp_path / "output", cascade=cascade)

    with pytest.raises(ValueError, match="approval revision"):
        flow.generate_batch("TJD-TEE-001", decide=lambda candidate: False)

    assert cascade.calls == []
    assert catalog.read_prompt("TJD-TEE-001")["concept_approval_revision"] is None


def test_batch_persists_only_explicitly_approved_images_and_sidecars(
    tmp_path: Path, db_catalog: tuple[TeePromptCatalog, sqlite3.Connection]
) -> None:
    catalog, _ = db_catalog
    output_root = tmp_path / "output" / "images" / "tee-merch"
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=cascade)
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
    assert all("image prompt revision" in prompt.lower() for prompt, _ in cascade.calls)
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
    assert manifest["image_prompt_revision"] == 1
    assert manifest["catalog_version"] == "1.0.0"
    assert manifest["concept_revision"] == 1
    assert manifest["prompt_revision"] == "tee-artwork-prompt-v2"
    assert manifest["approval"] == "approved"
    assert manifest["content_sha256"] == hashlib.sha256(
        b"\x89PNG\r\n\x1a\nimage-1"
    ).hexdigest()
    assert "exact_prompt" in manifest
    assert manifest["exact_prompt"] == cascade.calls[0][0]
    assert not list(run_dir.glob("*rejected*"))

    assert catalog.read_prompt("TJD-TEE-001")["exact_image_approval_status"] == (
        "exact_image_approved"
    )


def test_batch_uses_distinct_art_directions_for_each_candidate(
    tmp_path: Path, db_catalog: tuple[TeePromptCatalog, sqlite3.Connection]
) -> None:
    catalog, _ = db_catalog
    expected_concept = catalog.read_prompt("TJD-TEE-001")["concept"]
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(catalog, tmp_path / "output", cascade=cascade)

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
    assert all(f"Concept: {expected_concept}" in prompt for prompt in prompts)
    assert all("Catalog ID: TJD-TEE-001" in prompt for prompt in prompts)
    assert all("t-shirt design" in preface for preface in prefaces)
    style_markers = {"screen-print", "abstract", "line-work", "woodcut"}
    assert {style for preface in prefaces for style in style_markers if style in preface} == style_markers


def test_chat_batch_stages_one_candidate_without_approving_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    output_root = tmp_path / "output"
    monkeypatch.setattr(
        tee_image_approval,
        "_PENDING_ROOT",
        tmp_path / "pending",
        raising=False,
    )
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=cascade)
    stage = flow.start_chat_batch("TJD-TEE-001", count=2)

    candidate_path = Path(stage["image_path"])
    assert stage["status"] == "candidate_pending"
    assert stage["candidate_number"] == 1
    assert candidate_path.is_file()
    assert len(cascade.calls) == 1
    assert not output_root.exists()
    assert catalog.read_prompt("TJD-TEE-001")["exact_image_approval_status"] == (
        "not_started"
    )


def test_chat_rejection_discards_candidate_before_staging_the_next_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    output_root = tmp_path / "output"
    monkeypatch.setattr(
        tee_image_approval, "_PENDING_ROOT", tmp_path / "pending", raising=False
    )
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=cascade)
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    output_root = tmp_path / "output"
    monkeypatch.setattr(
        tee_image_approval, "_PENDING_ROOT", tmp_path / "pending", raising=False
    )
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=cascade)
    stage = flow.start_chat_batch("TJD-TEE-001", count=1)
    pending_path = Path(stage["image_path"])
    session = json.loads((pending_path.parent / "session.json").read_text(encoding="utf-8"))
    assert session["pending_candidate"]["content_sha256"] == hashlib.sha256(
        b"\x89PNG\r\n\x1a\nimage-1"
    ).hexdigest()
    assert not output_root.exists()

    finished = flow.decide_chat_candidate(
        stage["session_id"], stage["candidate_id"], decision="y"
    )

    run_dir = output_root / "TJD-TEE-001" / stage["run_id"]
    image_path = run_dir / f"{stage['candidate_id']}.png"
    sidecar_path = run_dir / f"{stage['candidate_id']}.json"
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert finished["status"] == "completed"
    assert finished["generated"] == 1
    assert finished["approved"] == 1
    assert finished["rejected"] == 0
    assert image_path.read_bytes() == b"\x89PNG\r\n\x1a\nimage-1"
    assert not pending_path.exists()
    assert sidecar["approval"] == "approved"
    assert sidecar["exact_prompt"] == cascade.calls[0][0]
    assert sidecar["prompt_revision"] == "tee-artwork-prompt-v2"
    assert catalog.read_prompt("TJD-TEE-001")["exact_image_approval_status"] == (
        "exact_image_approved"
    )


def test_chat_approval_keeps_assets_when_post_commit_readback_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, connection = db_catalog
    output_root = tmp_path / "output"
    monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", tmp_path / "pending")
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=FakeCascade())
    stage = flow.start_chat_batch("TJD-TEE-001", count=1)
    original_read_prompt = catalog.read_prompt

    def fail_after_approval(prompt_id: str) -> dict[str, object]:
        prompt = original_read_prompt(prompt_id)
        if prompt["exact_image_approval_status"] == "exact_image_approved":
            raise RuntimeError("post-commit readback failed")
        return prompt

    monkeypatch.setattr(catalog, "read_prompt", fail_after_approval)

    result = flow.decide_chat_candidate(
        stage["session_id"], stage["candidate_id"], decision="y"
    )

    run_dir = output_root / "TJD-TEE-001" / stage["run_id"]
    image_path = run_dir / f"{stage['candidate_id']}.png"
    sidecar_path = run_dir / f"{stage['candidate_id']}.json"
    assert result["status"] == "completed"
    assert image_path.read_bytes() == b"\x89PNG\r\n\x1a\nimage-1"
    assert json.loads(sidecar_path.read_text(encoding="utf-8"))["approval"] == "approved"
    assert connection.execute(
        "SELECT exact_image_approval_status FROM tee_prompts WHERE id = ?",
        ("TJD-TEE-001",),
    ).fetchone()[0] == "exact_image_approved"


def test_current_approval_sidecar_reconciles_database_without_changing_assets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, connection = db_catalog
    output_root = tmp_path / "output"
    pending_root = tmp_path / "pending"
    monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", pending_root)
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=FakeCascade())
    run = flow.generate_batch("TJD-TEE-001", count=1, decide=lambda candidate: True)
    approved_image = run.approved[0].path
    sidecar_path = approved_image.with_suffix(".json")
    prior_image_bytes = approved_image.read_bytes()
    prior_sidecar_bytes = sidecar_path.read_bytes()
    connection.execute(
        "UPDATE tee_prompts SET exact_image_approval_status = 'not_started' WHERE id = ?",
        ("TJD-TEE-001",),
    )
    connection.commit()

    stage = flow.start_chat_batch("TJD-TEE-001", count=1)

    assert catalog.read_prompt("TJD-TEE-001")["exact_image_approval_status"] == (
        "exact_image_approved"
    )
    assert approved_image.read_bytes() == prior_image_bytes
    assert sidecar_path.read_bytes() == prior_sidecar_bytes
    flow.cancel_chat_batch(stage["session_id"])


def test_unrelated_test_sidecar_does_not_manufacture_current_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    output_root = tmp_path / "output"
    pending_root = tmp_path / "pending"
    test_run = output_root / "TJD-TEE-001" / "pytest-artifacts"
    test_run.mkdir(parents=True)
    sidecar_path = test_run / "test-candidate.json"
    sidecar_path.write_text(
        json.dumps({"catalog_id": "TJD-TEE-001", "approval": "approved"}),
        encoding="utf-8",
    )
    prior_sidecar_bytes = sidecar_path.read_bytes()
    monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", pending_root)
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=FakeCascade())

    stage = flow.start_chat_batch("TJD-TEE-001", count=1)

    assert catalog.read_prompt("TJD-TEE-001")["exact_image_approval_status"] == (
        "not_started"
    )
    assert sidecar_path.read_bytes() == prior_sidecar_bytes
    flow.cancel_chat_batch(stage["session_id"])


def test_stale_revision_sidecar_is_preserved_but_not_current_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, connection = db_catalog
    output_root = tmp_path / "output"
    pending_root = tmp_path / "pending"
    monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", pending_root)
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=FakeCascade())
    run = flow.generate_batch("TJD-TEE-001", count=1, decide=lambda candidate: True)
    old_image = run.approved[0].path
    old_sidecar = old_image.with_suffix(".json")
    prior_image_bytes = old_image.read_bytes()
    prior_sidecar_bytes = old_sidecar.read_bytes()
    catalog.edit_prompt("TJD-TEE-001", {"title": "Jukebox After Rain"})
    connection.execute(
        "UPDATE tee_prompts SET exact_image_approval_status = 'exact_image_approved' WHERE id = ?",
        ("TJD-TEE-001",),
    )
    connection.commit()

    stage = flow.start_chat_batch("TJD-TEE-001", count=1)

    assert catalog.read_prompt("TJD-TEE-001")["exact_image_approval_status"] == (
        "not_started"
    )
    assert old_image.read_bytes() == prior_image_bytes
    assert old_sidecar.read_bytes() == prior_sidecar_bytes
    flow.cancel_chat_batch(stage["session_id"])


def test_editing_another_concept_preserves_current_approved_sidecar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    output_root = tmp_path / "output"
    pending_root = tmp_path / "pending"
    monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", pending_root)
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=cascade)
    approved = flow.generate_batch("TJD-TEE-002", count=1, decide=lambda candidate: True)
    approved_image = approved.approved[0].path
    sidecar_path = approved_image.with_suffix(".json")
    approved_prompt = json.loads(sidecar_path.read_text(encoding="utf-8"))["exact_prompt"]
    image_bytes = approved_image.read_bytes()
    sidecar_bytes = sidecar_path.read_bytes()

    catalog.edit_prompt("TJD-TEE-001", {"title": "A different concept"})
    stage = flow.start_chat_batch("TJD-TEE-002", count=1)

    assert catalog.read_prompt("TJD-TEE-002")["exact_image_approval_status"] == (
        "exact_image_approved"
    )
    assert cascade.calls[-1][0] == approved_prompt
    assert approved_image.read_bytes() == image_bytes
    assert sidecar_path.read_bytes() == sidecar_bytes
    flow.cancel_chat_batch(stage["session_id"])


def test_legacy_approved_sidecar_survives_an_unrelated_prompt_edit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    output_root = tmp_path / "output"
    pending_root = tmp_path / "pending"
    monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", pending_root)
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=FakeCascade())
    approved = flow.generate_batch("TJD-TEE-002", count=1, decide=lambda candidate: True)
    sidecar_path = approved.approved[0].path.with_suffix(".json")
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar["catalog_revision"] = "1.0.0:1"
    sidecar["exact_prompt"] = sidecar["exact_prompt"].replace(
        "Image prompt revision: 1", "Catalog revision: 1.0.0:1"
    )
    sidecar.pop("image_prompt_revision")
    sidecar.pop("catalog_version")
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    sidecar_bytes = sidecar_path.read_bytes()

    catalog.edit_prompt("TJD-TEE-001", {"title": "A different concept"})
    stage = flow.start_chat_batch("TJD-TEE-002", count=1)

    assert catalog.read_prompt("TJD-TEE-002")["exact_image_approval_status"] == (
        "exact_image_approved"
    )
    assert sidecar_path.read_bytes() == sidecar_bytes
    flow.cancel_chat_batch(stage["session_id"])


def test_chat_approval_survives_another_concepts_prompt_edit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    output_root = tmp_path / "output"
    pending_root = tmp_path / "pending"
    monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", pending_root)
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=FakeCascade())
    stage = flow.start_chat_batch("TJD-TEE-002", count=1)

    catalog.edit_prompt("TJD-TEE-001", {"title": "A different concept"})
    result = flow.decide_chat_candidate(
        stage["session_id"], stage["candidate_id"], decision="y"
    )

    sidecar = json.loads(
        (output_root / "TJD-TEE-002" / stage["run_id"] / f"{stage['candidate_id']}.json")
        .read_text(encoding="utf-8")
    )
    assert result["status"] == "completed"
    assert sidecar["catalog_id"] == "TJD-TEE-002"
    assert catalog.read_prompt("TJD-TEE-002")["exact_image_approval_status"] == (
        "exact_image_approved"
    )


def test_chat_decision_validates_session_candidate_and_choice(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    monkeypatch.setattr(
        tee_image_approval, "_PENDING_ROOT", tmp_path / "pending", raising=False
    )
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(catalog, tmp_path / "output", cascade=cascade)
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    output_root = tmp_path / "output"
    monkeypatch.setattr(
        tee_image_approval, "_PENDING_ROOT", tmp_path / "pending", raising=False
    )
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=FakeCascade())
    stage = flow.start_chat_batch("TJD-TEE-001", count=1)
    pending_path = Path(stage["image_path"])
    catalog.edit_prompt(
        "TJD-TEE-001",
        {"concept": "A revised fictional guitarist leaves the jukebox at dawn."},
        approved_by_tyler=True,
    )

    with pytest.raises(ValueError, match="revision changed"):
        flow.decide_chat_candidate(stage["session_id"], stage["candidate_id"], decision="y")

    assert not pending_path.exists()
    assert not (
        pending_path.parent.parent
        / f".{stage['session_id']}.presentation.json"
    ).exists()
    assert not output_root.exists()


def test_chat_cancel_discards_pending_candidate_without_rejecting_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    output_root = tmp_path / "output"
    monkeypatch.setattr(
        tee_image_approval, "_PENDING_ROOT", tmp_path / "pending", raising=False
    )
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=FakeCascade())
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from src.merch import tee_image_approval

    database_path = tmp_path / "catalog.sqlite"
    connection, _ = _in_memory_catalog(database_path)
    connection.close()
    output_root = tmp_path / "output"
    pending_root = tmp_path / "pending"
    monkeypatch.setattr(
        tee_image_approval, "_live_connection", lambda: _open_test_catalog(database_path)
    )
    monkeypatch.setattr(tee_image_approval, "_OUTPUT_ROOT", output_root)
    monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", pending_root)
    monkeypatch.setattr(tee_image_approval, "_workspace_cascade", lambda workspace_src=None: FakeCascade())

    assert tee_image_approval.main(
        ["--chat-start", "--catalog-id", "TJD-TEE-001", "--count", "1"]
    ) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "candidate_pending"
    assert Path(result["image_path"]).is_file()
    connection = sqlite3.connect(database_path)
    flow = TeeImageApprovalFlow(
        TeePromptCatalog(connection), output_root, pending_root=pending_root
    )
    flow.cancel_chat_batch(result["session_id"])
    connection.close()


def test_chat_decide_cli_approves_exact_image_and_prints_next_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from src.merch import tee_image_approval

    database_path = tmp_path / "catalog.sqlite"
    connection, _ = _in_memory_catalog(database_path)
    connection.close()
    output_root = tmp_path / "output"
    pending_root = tmp_path / "pending"
    monkeypatch.setattr(
        tee_image_approval, "_live_connection", lambda: _open_test_catalog(database_path)
    )
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
    connection = sqlite3.connect(database_path)
    flow = TeeImageApprovalFlow(
        TeePromptCatalog(connection), output_root, pending_root=pending_root
    )
    flow.cancel_chat_batch(first["session_id"])
    connection.close()


def test_batch_count_is_limited_to_one_through_four(
    tmp_path: Path, db_catalog: tuple[TeePromptCatalog, sqlite3.Connection]
) -> None:
    catalog, _ = db_catalog
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(catalog, tmp_path / "output", cascade=cascade)

    with pytest.raises(ValueError, match="1 and 4"):
        flow.generate_batch("TJD-TEE-001", count=5)
    with pytest.raises(ValueError, match="1 and 4"):
        flow.generate_batch("TJD-TEE-001", count=2.5)

    assert cascade.calls == []


def test_provider_failures_are_preserved_without_persisting_candidates(
    tmp_path: Path, db_catalog: tuple[TeePromptCatalog, sqlite3.Connection]
) -> None:
    catalog, _ = db_catalog
    output_root = tmp_path / "output"
    flow = TeeImageApprovalFlow(
        catalog,
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
    assert catalog.read_prompt("TJD-TEE-001")["exact_image_approval_status"] == (
        "not_started"
    )


def test_batch_rejects_images_outside_generation_directory(
    tmp_path: Path, db_catalog: tuple[TeePromptCatalog, sqlite3.Connection]
) -> None:
    catalog, _ = db_catalog
    external_image = tmp_path / "external" / "candidate.png"
    external_image.parent.mkdir()
    external_image.write_bytes(b"external-image")

    class ExternalPathCascade:
        def generate(self, prompt: str, *, output_dir: Path) -> SimpleNamespace:
            return SimpleNamespace(
                path=external_image,
                provider="fake-provider",
                model="fake-model",
                diagnostics=(),
            )

    output_root = tmp_path / "output"
    decisions: list[object] = []
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=ExternalPathCascade())

    run = flow.generate_batch(
        "TJD-TEE-001",
        count=1,
        decide=lambda candidate: decisions.append(candidate) or True,
    )

    assert decisions == []
    assert run.approved == ()
    assert len(run.failures) == 1
    assert run.failures[0]["error"] == (
        "image cascade returned a missing, unsupported, or out-of-directory image file"
    )
    run_dir = output_root / "TJD-TEE-001" / run.run_id
    assert (run_dir / "provider-failures.json").is_file()
    assert not list(run_dir.glob("*.png"))
    assert not [
        sidecar
        for sidecar in run_dir.glob("*.json")
        if sidecar.name != "provider-failures.json"
    ]
    assert catalog.read_prompt("TJD-TEE-001")["exact_image_approval_status"] == (
        "not_started"
    )


def test_batch_rejects_candidate_replaced_during_approval(
    tmp_path: Path, db_catalog: tuple[TeePromptCatalog, sqlite3.Connection]
) -> None:
    catalog, _ = db_catalog
    external_image = tmp_path / "external.png"
    external_image.write_bytes(b"\x89PNG\r\n\x1a\nexternal-image")

    class ReplacedPathCascade:
        def generate(self, prompt: str, *, output_dir: Path) -> SimpleNamespace:
            candidate_path = output_dir / "candidate.png"
            candidate_path.write_bytes(b"\x89PNG\r\n\x1a\nvalidated-image")
            return SimpleNamespace(
                path=candidate_path,
                provider="fake-provider",
                model="fake-model",
                diagnostics=(),
            )

    output_root = tmp_path / "output"
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=ReplacedPathCascade())

    def replace_candidate(candidate: TeeImageCandidate) -> bool:
        candidate.path.unlink()
        external_image.replace(candidate.path)
        return True

    run = flow.generate_batch("TJD-TEE-001", count=1, decide=replace_candidate)

    assert run.approved == ()
    assert len(run.failures) == 1
    assert run.failures[0]["error"] == (
        "image candidate changed or escaped the generation directory during approval"
    )
    run_dir = output_root / "TJD-TEE-001" / run.run_id
    assert not list(run_dir.glob("*.png"))
    assert not [
        sidecar
        for sidecar in run_dir.glob("*.json")
        if sidecar.name != "provider-failures.json"
    ]
    assert catalog.read_prompt("TJD-TEE-001")["exact_image_approval_status"] == (
        "not_started"
    )


def test_batch_rejects_candidate_modified_in_place_during_approval(
    tmp_path: Path, db_catalog: tuple[TeePromptCatalog, sqlite3.Connection]
) -> None:
    catalog, _ = db_catalog
    output_root = tmp_path / "output"
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=FakeCascade())

    def modify_candidate(candidate: TeeImageCandidate) -> bool:
        candidate.path.write_bytes(b"\x89PNG\r\n\x1a\nmodified-after-display")
        return True

    run = flow.generate_batch("TJD-TEE-001", count=1, decide=modify_candidate)

    assert run.approved == ()
    assert len(run.failures) == 1
    assert run.failures[0]["error"] == (
        "image candidate content changed during approval"
    )
    run_dir = output_root / "TJD-TEE-001" / run.run_id
    assert not list(run_dir.glob("*.png"))
    assert not [
        sidecar
        for sidecar in run_dir.glob("*.json")
        if sidecar.name != "provider-failures.json"
    ]
    assert catalog.read_prompt("TJD-TEE-001")["exact_image_approval_status"] == (
        "not_started"
    )


def test_batch_rejects_non_image_content_before_approval(
    tmp_path: Path, db_catalog: tuple[TeePromptCatalog, sqlite3.Connection]
) -> None:
    catalog, _ = db_catalog

    class InvalidImageCascade:
        def generate(self, prompt: str, *, output_dir: Path) -> SimpleNamespace:
            candidate_path = output_dir / "candidate.png"
            candidate_path.write_bytes(b"not-an-image")
            return SimpleNamespace(
                path=candidate_path,
                provider="fake-provider",
                model="fake-model",
                diagnostics=(),
            )

    decisions: list[TeeImageCandidate] = []
    output_root = tmp_path / "output"
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=InvalidImageCascade())

    run = flow.generate_batch(
        "TJD-TEE-001",
        count=1,
        decide=lambda candidate: decisions.append(candidate) or True,
    )

    assert decisions == []
    assert run.approved == ()
    assert len(run.failures) == 1
    assert run.failures[0]["error"] == (
        "image file content does not match its extension"
    )
    run_dir = output_root / "TJD-TEE-001" / run.run_id
    assert (run_dir / "provider-failures.json").is_file()
    assert not list(run_dir.glob("*.png"))
    assert not [
        sidecar
        for sidecar in run_dir.glob("*.json")
        if sidecar.name != "provider-failures.json"
    ]
    assert catalog.read_prompt("TJD-TEE-001")["exact_image_approval_status"] == (
        "not_started"
    )


def test_batch_does_not_overwrite_existing_approved_candidate(
    tmp_path: Path,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog, _ = db_catalog
    run_id = "0123456789abcdef0123456789abcdef"
    monkeypatch.setattr(
        "src.merch.tee_image_approval.uuid.uuid4",
        lambda: SimpleNamespace(hex=run_id),
    )
    output_root = tmp_path / "output"
    run_dir = output_root / "TJD-TEE-001" / run_id
    run_dir.mkdir(parents=True)
    existing_image = run_dir / "01234567-01.png"
    existing_image.write_bytes(b"preexisting-output")
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=FakeCascade())

    run = flow.generate_batch("TJD-TEE-001", count=1, decide=lambda candidate: True)

    assert run.approved == ()
    assert len(run.failures) == 1
    assert existing_image.read_bytes() == b"preexisting-output"
    assert not [
        sidecar
        for sidecar in run_dir.glob("*.json")
        if sidecar.name != "provider-failures.json"
    ]
    assert catalog.read_prompt("TJD-TEE-001")["exact_image_approval_status"] == (
        "not_started"
    )


def test_catalog_revision_change_requires_concept_reapproval(
    tmp_path: Path, db_catalog: tuple[TeePromptCatalog, sqlite3.Connection]
) -> None:
    catalog, connection = db_catalog
    connection.execute(
        "UPDATE tee_prompts SET concept_revision = concept_revision + 1 WHERE id = ?",
        ("TJD-TEE-001",),
    )
    connection.commit()
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(catalog, tmp_path / "output", cascade=cascade)

    with pytest.raises(ValueError, match="revision"):
        flow.generate_batch("TJD-TEE-001")

    assert cascade.calls == []
    assert catalog.read_prompt("TJD-TEE-001")["concept_approval_status"] == (
        "concept_approved"
    )


def test_exact_image_approval_is_monotonic_across_batches(
    tmp_path: Path, db_catalog: tuple[TeePromptCatalog, sqlite3.Connection]
) -> None:
    catalog, _ = db_catalog
    output_root = tmp_path / "output"
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=FakeCascade())
    first = flow.generate_batch("TJD-TEE-001", count=1, decide=lambda candidate: True)

    flow.generate_batch("TJD-TEE-001", count=1, decide=lambda candidate: False)

    assert first.approved
    assert catalog.read_prompt("TJD-TEE-001")["exact_image_approval_status"] == (
        "exact_image_approved"
    )


def test_multiple_images_can_be_approved_for_one_concept(
    tmp_path: Path, db_catalog: tuple[TeePromptCatalog, sqlite3.Connection]
) -> None:
    catalog, _ = db_catalog
    flow = TeeImageApprovalFlow(catalog, tmp_path / "output", cascade=FakeCascade())

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


def test_default_workspace_source_prefers_canonical_root_over_stale_feature_worktree(
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

    assert tee_image_approval._resolve_workspace_src() == canonical_src


def test_explicit_workspace_source_override_is_retained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.merch import tee_image_approval

    workspace_root = tmp_path / "workspace"
    override_src = tmp_path / "configured-workspace" / "src"
    monkeypatch.setenv("WORKSPACE_SRC", str(override_src))
    monkeypatch.setattr(tee_image_approval, "_WORKSPACE_ROOT", workspace_root)

    assert tee_image_approval._resolve_workspace_src() == override_src


def test_approved_asset_keeps_provenance_from_selected_workspace_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    workspace_root = tmp_path / "workspace"
    canonical_src = workspace_root / "src"
    integration_dir = canonical_src / "integrations"
    integration_dir.mkdir(parents=True)
    (integration_dir / "image_cascade.py").write_text(
        "from pathlib import Path\n"
        "from types import SimpleNamespace\n"
        "\n"
        "class Cascade:\n"
        "    def generate(self, prompt, *, output_dir=None):\n"
        "        path = Path(output_dir) / 'candidate.png'\n"
        "        path.write_bytes(b'\\x89PNG\\r\\n\\x1a\\nworkspace-image')\n"
        "        return SimpleNamespace(path=path, provider='workspace-provider', "
        "model='workspace-selected-model', diagnostics=())\n"
        "\n"
        "def default_image_cascade():\n"
        "    return Cascade()\n",
        encoding="utf-8",
    )

    catalog, _ = db_catalog
    flow = TeeImageApprovalFlow(
        catalog, tmp_path / "output", cascade=tee_image_approval._workspace_cascade(canonical_src)
    )

    run = flow.generate_batch("TJD-TEE-001", count=1, decide=lambda candidate: True)

    sidecar = json.loads(run.approved[0].path.with_suffix(".json").read_text(encoding="utf-8"))
    assert sidecar["provider"] == "workspace-provider"
    assert sidecar["model"] == "workspace-selected-model"


def test_generation_uses_the_database_catalog(tmp_path: Path) -> None:
    connection, catalog = _in_memory_catalog()
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(catalog, tmp_path / "output", cascade=cascade)

    try:
        flow.generate_batch("TJD-TEE-001", count=1, decide=lambda candidate: False)

        assert len(cascade.calls) == 1
        assert "Walk Away From the Jukebox" in cascade.calls[0][0]
        assert "Image prompt revision: 1" in cascade.calls[0][0]
    finally:
        connection.close()


def test_exact_image_approval_persists_revision_through_catalog_boundary(
    tmp_path: Path,
) -> None:
    connection, catalog = _in_memory_catalog()
    output_root = tmp_path / "output"
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=FakeCascade())

    try:
        run = flow.generate_batch("TJD-TEE-001", count=1, decide=lambda candidate: True)

        assert len(run.approved) == 1
        sidecar_path = run.approved[0].path.with_suffix(".json")
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        assert sidecar["image_prompt_revision"] == 1
        assert sidecar["catalog_version"] == "1.0.0"
        assert sidecar["concept_revision"] == 1
        assert sidecar["prompt_revision"] == "tee-artwork-prompt-v2"
        assert catalog.read_prompt("TJD-TEE-001")["exact_image_approval_status"] == (
            "exact_image_approved"
        )
    finally:
        connection.close()


def test_batch_rejects_candidate_swapped_and_restored_during_decision(
    tmp_path: Path, db_catalog: tuple[TeePromptCatalog, sqlite3.Connection]
) -> None:
    catalog, _ = db_catalog
    flow = TeeImageApprovalFlow(catalog, tmp_path / "output", cascade=FakeCascade())
    original_bytes = b"\x89PNG\r\n\x1a\nimage-1"
    replacement_bytes = b"\x89PNG\r\n\x1a\nreplacement"
    presented_bytes: list[bytes] = []

    def swap_and_restore(candidate: TeeImageCandidate) -> bool:
        presented_bytes.append(candidate.path.read_bytes())
        original_path = candidate.path.with_suffix(".original")
        candidate.path.replace(original_path)
        candidate.path.write_bytes(replacement_bytes)
        candidate.path.unlink()
        original_path.replace(candidate.path)
        return True

    run = flow.generate_batch("TJD-TEE-001", count=1, decide=swap_and_restore)

    assert presented_bytes == [original_bytes]
    assert run.approved == ()
    assert len(run.failures) == 1
    assert not list((tmp_path / "output").rglob("*.png"))


def test_chat_rejects_staged_image_changed_after_display(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", tmp_path / "pending")
    output_root = tmp_path / "output"
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=FakeCascade())
    stage = flow.start_chat_batch("TJD-TEE-001", count=1)
    pending_path = Path(stage["image_path"])
    pending_path.write_bytes(b"\x89PNG\r\n\x1a\nchanged-after-display")

    with pytest.raises(ValueError, match="candidate changed"):
        flow.decide_chat_candidate(
            stage["session_id"], stage["candidate_id"], decision="y"
        )

    assert not output_root.exists()
    assert catalog.read_prompt("TJD-TEE-001")["exact_image_approval_status"] == (
        "not_started"
    )


def test_chat_rejects_candidate_swapped_and_restored_before_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", tmp_path / "pending")
    output_root = tmp_path / "output"
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=FakeCascade())
    stage = flow.start_chat_batch("TJD-TEE-001", count=1)
    pending_path = Path(stage["image_path"])
    original_path = pending_path.with_suffix(".original")
    original_bytes = pending_path.read_bytes()
    pending_path.replace(original_path)
    pending_path.write_bytes(b"\x89PNG\r\n\x1a\ntransient-replacement")
    pending_path.unlink()
    original_path.replace(pending_path)
    from src.merch import tee_image_approval

    presentation_record = json.loads(
        (
            pending_path.parent.parent
            / f".{stage['session_id']}.presentation.json"
        ).read_text(encoding="utf-8")
    )
    current_directory_stat = pending_path.parent.stat()
    os.utime(
        pending_path.parent,
        ns=(
            current_directory_stat.st_atime_ns,
            presentation_record["directory_fingerprint"][3] + 100_000_000,
        ),
    )
    assert presentation_record["directory_fingerprint"] != list(
        tee_image_approval._stat_fingerprint(pending_path.parent.stat())
    )

    with pytest.raises(ValueError, match="candidate changed"):
        flow.decide_chat_candidate(
            stage["session_id"], stage["candidate_id"], decision="y"
        )

    assert pending_path.read_bytes() == original_bytes
    assert not output_root.exists()


@pytest.mark.parametrize("entry_path", ("batch", "chat"))
@pytest.mark.parametrize("symlink_location", ("root", "parent"))
def test_generation_rejects_symlinked_output_root_ancestors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
    entry_path: str,
    symlink_location: str,
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    outside_root = tmp_path / "outside"
    outside_root.mkdir()
    if symlink_location == "root":
        output_root = tmp_path / "output"
        link = output_root
    else:
        linked_parent = tmp_path / "linked-parent"
        link = linked_parent
        output_root = linked_parent / "output"
    if os.name == "nt":
        reparse_path = output_root if symlink_location == "root" else output_root.parent
        monkeypatch.setattr(
            tee_image_approval,
            "_is_reparse_point",
            lambda path: Path(path) == reparse_path,
            raising=False,
        )
    else:
        link.symlink_to(outside_root, target_is_directory=True)

    monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", tmp_path / "pending")
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=cascade)

    with pytest.raises(ValueError, match="symlink|output path"):
        if entry_path == "batch":
            flow.generate_batch("TJD-TEE-001", count=1, decide=lambda candidate: True)
        else:
            flow.start_chat_batch("TJD-TEE-001", count=1)

    assert cascade.calls == []
    assert list(outside_root.iterdir()) == []


@pytest.mark.parametrize("entry_path", ("batch", "chat"))
@pytest.mark.parametrize("collision_type", ("image", "sidecar"))
def test_generation_preserves_existing_approved_output_collisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
    entry_path: str,
    collision_type: str,
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    run_id = "0123456789abcdef0123456789abcdef"
    monkeypatch.setattr(
        tee_image_approval.uuid, "uuid4", lambda: SimpleNamespace(hex=run_id)
    )
    monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", tmp_path / "pending")
    output_root = tmp_path / "output"
    run_dir = output_root / "TJD-TEE-001" / run_id
    run_dir.mkdir(parents=True)
    suffix = ".png" if collision_type == "image" else ".json"
    collision_path = run_dir / f"01234567-01{suffix}"
    collision_bytes = b"approved bytes that must survive"
    collision_path.write_bytes(collision_bytes)
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=FakeCascade())

    if entry_path == "batch":
        result = flow.generate_batch(
            "TJD-TEE-001", count=1, decide=lambda candidate: True
        )
        assert result.approved == ()
        assert result.failures
    else:
        stage = flow.start_chat_batch("TJD-TEE-001", count=1)
        with pytest.raises(FileExistsError):
            flow.decide_chat_candidate(
                stage["session_id"], stage["candidate_id"], decision="y"
            )

    assert collision_path.read_bytes() == collision_bytes


def test_batch_revalidates_output_root_after_decision_callback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    output_root = tmp_path / "output"
    became_reparse_point = False
    monkeypatch.setattr(
        tee_image_approval,
        "_is_reparse_point",
        lambda path: became_reparse_point and Path(path) == output_root,
    )
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=FakeCascade())

    def replace_output_root(candidate: TeeImageCandidate) -> bool:
        nonlocal became_reparse_point
        became_reparse_point = True
        return True

    with pytest.raises(ValueError, match="output path"):
        flow.generate_batch("TJD-TEE-001", count=1, decide=replace_output_root)

    assert not output_root.exists()
