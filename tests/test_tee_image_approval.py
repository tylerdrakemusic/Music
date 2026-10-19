"""Tests for operator-approved tee artwork generation."""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import sqlite3
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

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


def _patch_tee_lock(
    monkeypatch: pytest.MonkeyPatch, lock_path: Path, timeout_seconds: float = 10
) -> None:
    from src.merch import tee_image_lock

    monkeypatch.setattr(tee_image_lock, "TEE_IMAGE_APPROVAL_LOCK_PATH", lock_path)
    monkeypatch.setattr(
        tee_image_lock, "TEE_IMAGE_APPROVAL_LOCK_TIMEOUT_SECONDS", timeout_seconds
    )


@pytest.fixture
def db_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TeePromptCatalog, sqlite3.Connection]:
    monkeypatch.setenv(
        "HEARTMUSIC_DB_KEY",
        "test-only-music-approval-integrity-key-not-a-secret",
    )
    connection, catalog = _in_memory_catalog()
    yield catalog, connection
    connection.close()


@pytest.fixture(autouse=True)
def _test_tee_integrity_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "HEARTMUSIC_DB_KEY", "test-only-integrity-key-for-unit-tests-0123456789abcdef"
    )


class FakeCascade:
    def __init__(
        self,
        failures: bool = False,
        *,
        provider: str = "fal-ai",
        model: str = "black-forest-labs/FLUX.1-Krea-dev",
        route: str = "fal-ai/flux/krea",
    ) -> None:
        self.calls: list[tuple[str, Path]] = []
        self.failures = failures
        self.provider = provider
        self.model = model
        self.route = route

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
            provider=self.provider,
            model=self.model,
            route=self.route,
            diagnostics=(),
        )


def _lock_available_to_another_thread(
    tee_image_approval: object, lock_path: Path
) -> bool:
    acquired: list[bool] = []

    def try_lock() -> None:
        try:
            with tee_image_approval._tee_approval_lock(
                lock_path=lock_path, timeout_seconds=0.05
            ):
                acquired.append(True)
        except TimeoutError:
            acquired.append(False)

    thread = threading.Thread(target=try_lock)
    thread.start()
    thread.join(1)
    return not thread.is_alive() and acquired == [True]


class FakeGenerationError(Exception):
    def __init__(self, message: str, *, diagnostics: tuple[object, ...]) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics


def _hold_tee_approval_lock(
    lock_path: str, acquired: Any, release: Any
) -> None:
    from src.merch import tee_image_approval

    with tee_image_approval._tee_approval_lock(lock_path=Path(lock_path)):
        acquired.set()
        release.wait(5)


@pytest.mark.parametrize("entry_path", ("batch", "chat"))
@pytest.mark.parametrize(
    "provider,model,route",
    (
        ("pollinations", "black-forest-labs/FLUX.1-Krea-dev", "fal-ai/flux/krea"),
        ("fal-ai", "unapproved-model", "fal-ai/flux/krea"),
        ("fal-ai", "black-forest-labs/FLUX.1-Krea-dev", "unapproved/route"),
    ),
)
def test_unapproved_provider_tuple_never_becomes_pending_or_approved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
    entry_path: str,
    provider: str,
    model: str,
    route: str,
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    pending_root = tmp_path / "pending"
    output_root = tmp_path / "output"
    monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", pending_root)
    flow = TeeImageApprovalFlow(
        catalog,
        output_root,
        cascade=FakeCascade(provider=provider, model=model, route=route),
    )

    if entry_path == "chat":
        stage = flow.start_chat_batch("TJD-TEE-001", count=1)
        assert stage["status"] != "candidate_pending"
        assert list(pending_root.rglob("*.png")) == []
        assert list(pending_root.glob(".*.presentation.json")) == []
    else:
        result = flow.generate_batch("TJD-TEE-001", count=1, decide=lambda _: True)
        assert result.approved == ()
        assert list(output_root.rglob("*.png")) == []
        assert [
            path
            for path in output_root.rglob("*.json")
            if path.name != "provider-failures.json"
        ] == []


@pytest.mark.parametrize("configured_key", (None, "short"))
def test_chat_requires_valid_integrity_key_before_generation_or_persistence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
    configured_key: str | None,
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    pending_root = tmp_path / "pending"
    monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", pending_root)
    if configured_key is None:
        monkeypatch.delenv("HEARTMUSIC_DB_KEY", raising=False)
    else:
        monkeypatch.setenv("HEARTMUSIC_DB_KEY", configured_key)
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(catalog, tmp_path / "output", cascade=cascade)

    with pytest.raises(RuntimeError, match="HEARTMUSIC_DB_KEY"):
        flow.start_chat_batch("TJD-TEE-001", count=1)

    assert cascade.calls == []
    assert not pending_root.exists()


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


def test_interactive_approval_displays_provider_and_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from src.merch import tee_image_approval

    monkeypatch.setattr(tee_image_approval.os, "startfile", lambda _path: None, raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    candidate = TeeImageCandidate(
        candidate_id="01234567-01",
        path=tmp_path / "candidate.png",
        provider="fal-ai",
        model="black-forest-labs/FLUX.1-Krea-dev",
        exact_prompt="approved test prompt",
        provider_route="fal-ai/flux/krea",
    )

    approved = tee_image_approval._interactive_decision(candidate)

    output = capsys.readouterr().out
    assert not approved
    assert "Provider: fal-ai" in output
    assert "Model: black-forest-labs/FLUX.1-Krea-dev" in output
    assert "Route: fal-ai/flux/krea" in output


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
    assert len(sidecars) == 3
    candidate_id = run.approved[0].candidate_id
    manifest = json.loads((run_dir / f"{candidate_id}.json").read_text(encoding="utf-8"))
    assert manifest["candidate_id"] == run.approved[0].candidate_id
    assert manifest["provider"] == "fal-ai"
    assert manifest["model"] == "black-forest-labs/FLUX.1-Krea-dev"
    assert manifest["provider_route"] == "fal-ai/flux/krea"
    assert manifest["catalog_id"] == "TJD-TEE-001"
    assert manifest["image_prompt_revision"] == 1
    assert manifest["catalog_version"] == "1.0.0"
    assert manifest["concept_revision"] == 1
    assert manifest["prompt_revision"] == "tee-artwork-prompt-v3"
    assert manifest["approval"] == "approved"
    assert manifest["content_sha256"] == hashlib.sha256(
        b"\x89PNG\r\n\x1a\nimage-1"
    ).hexdigest()
    assert "exact_prompt" in manifest
    assert manifest["exact_prompt"] == cascade.calls[0][0]
    assert not list(run_dir.glob("*rejected*"))
    transformation = json.loads(
        (run_dir / f"{candidate_id}_transparency.json").read_text(encoding="utf-8")
    )
    assert transformation["status"] == "failed"
    assert transformation["source_sha256"] == manifest["content_sha256"]
    assert transformation["output_sha256"] is None
    assert run.failures[0]["candidate_id"] == candidate_id
    assert (run_dir / "transparency-failures.json").is_file()

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
    assert all("t-shirt design" not in prompt.lower() for prompt in prompts)
    assert all("selected concept itself" in prompt.lower() for prompt in prompts)
    assert all("standalone 2d design artwork" in prompt.lower() for prompt in prompts)
    assert all("do not depict clothing or apparel" in prompt.lower() for prompt in prompts)
    assert all("wearers" in prompt.lower() for prompt in prompts)
    assert all("product mockups" in prompt.lower() for prompt in prompts)
    assert all("clothing or apparel as the background" in prompt.lower() for prompt in prompts)
    assert all(
        "opaque artwork" in prompt.lower() and "do not use transparent rendering" in prompt.lower()
        for prompt in prompts
    )
    style_markers = {"screen-print", "abstract", "line-work", "woodcut"}
    assert {style for preface in prefaces for style in style_markers if style in preface} == style_markers
    composition_markers = (
        ("center the main subject", "balanced, emblematic composition", "sparse background"),
        ("wide environmental composition", "main subject off-center", "setting more space"),
        ("intimate close crop", "concept's key subjects", "secondary setting details"),
        ("dynamic diagonal composition", "main subject crossing the frame", "background shapes"),
    )
    assert all(
        all(marker in prompt.lower() for marker in markers)
        for prompt, markers in zip(prompts, composition_markers, strict=True)
    )


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
    assert sidecar["prompt_revision"] == "tee-artwork-prompt-v3"
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


def test_tampered_approved_sidecar_cannot_reconcile_provider_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    monkeypatch.setenv(
        "HEARTMUSIC_DB_KEY",
        "test-only-music-sidecar-integrity-key-not-a-secret",
    )
    catalog, connection = db_catalog
    output_root = tmp_path / "output"
    monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", tmp_path / "pending")
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=FakeCascade())
    run = flow.generate_batch("TJD-TEE-001", count=1, decide=lambda candidate: True)
    approved_image = run.approved[0].path
    sidecar_path = approved_image.with_suffix(".json")
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar["provider"] = "pollinations"
    sidecar["model"] = "default"
    sidecar["provider_route"] = "pollinations/text-to-image"
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    connection.execute(
        "UPDATE tee_prompts SET exact_image_approval_status = 'not_started' WHERE id = ?",
        ("TJD-TEE-001",),
    )
    connection.commit()

    pending = flow.start_chat_batch("TJD-TEE-001", count=1)

    assert catalog.read_prompt("TJD-TEE-001")["exact_image_approval_status"] == (
        "not_started"
    )
    assert sidecar["integrity_hmac_sha256"]
    flow.cancel_chat_batch(pending["session_id"])


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


def test_legacy_unsigned_sidecar_does_not_reconcile_approval(
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
        "not_started"
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


def test_chat_does_not_request_next_candidate_after_rejection_with_stale_concept(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    pending_root = tmp_path / "pending"
    monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", pending_root)
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(
        catalog,
        tmp_path / "output",
        cascade=cascade,
        pending_root=pending_root,
    )
    stage = flow.start_chat_batch("TJD-TEE-001", count=2)
    catalog.edit_prompt(
        "TJD-TEE-001",
        {"title": "Edited while operator reviewed candidate"},
        approved_by_tyler=True,
    )

    result = flow.decide_chat_candidate(
        stage["session_id"], stage["candidate_id"], decision="n"
    )

    assert result["status"] == "stale_concept"
    assert len(cascade.calls) == 1
    assert result["generated"] == 1
    assert result["rejected"] == 1
    assert list(pending_root.rglob("*.png")) == []
    assert list(pending_root.glob(".*.presentation.json")) == []
    assert list(pending_root.iterdir()) == []


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


def test_chat_session_write_failure_keeps_pending_candidate_recoverable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    pending_root = tmp_path / "pending"
    output_root = tmp_path / "output"
    monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", pending_root)
    flow = TeeImageApprovalFlow(
        catalog,
        output_root,
        cascade=FakeCascade(),
        pending_root=pending_root,
    )
    stage = flow.start_chat_batch("TJD-TEE-001", count=1)
    pending_path = Path(stage["image_path"])
    presentation_path = pending_root / f".{stage['session_id']}.presentation.json"
    original_write = flow._write_chat_session

    def fail_final_session_write(
        session_dir: Path, state: dict[str, object]
    ) -> None:
        if state.get("pending_candidate") is None:
            raise OSError("approved session state write failed")
        original_write(session_dir, state)

    monkeypatch.setattr(flow, "_write_chat_session", fail_final_session_write)

    with pytest.raises(OSError, match="approved session state write failed"):
        flow.decide_chat_candidate(
            str(stage["session_id"]), str(stage["candidate_id"]), decision="y"
        )

    assert pending_path.is_file()
    assert presentation_path.is_file()
    assert catalog.read_prompt("TJD-TEE-001")["exact_image_approval_status"] == (
        "exact_image_approved"
    )
    result = flow.cancel_chat_batch(str(stage["session_id"]))

    assert result["status"] == "cancelled"
    assert not pending_path.exists()
    assert not presentation_path.exists()


def test_chat_presentation_write_failure_does_not_leave_a_pending_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    pending_root = tmp_path / "pending"
    output_root = tmp_path / "output"
    monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", pending_root)
    original_write = tee_image_approval._write_json_exclusive

    def fail_presentation_write(path: Path, data: object) -> None:
        if path.name.endswith(".presentation.json"):
            raise OSError("presentation record write failed")
        original_write(path, data)

    monkeypatch.setattr(
        tee_image_approval, "_write_json_exclusive", fail_presentation_write
    )
    flow = TeeImageApprovalFlow(
        catalog,
        output_root,
        cascade=FakeCascade(),
        pending_root=pending_root,
    )

    result = flow.start_chat_batch("TJD-TEE-001", count=1)

    assert result["status"] == "completed"
    assert result["generated"] == 0
    assert result["failed"] == 1
    assert "presentation record write failed" in result["failures"][0]["error"]
    assert list(pending_root.rglob("*.png")) == []
    assert list(pending_root.glob(".*.presentation.json")) == []
    assert not list(pending_root.glob("*/session.json"))


def test_chat_staged_image_readback_failure_removes_orphan_before_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    pending_root = tmp_path / "pending"
    monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", pending_root)
    original_read = tee_image_approval._read_file_without_reparse_components
    staged_reads = 0

    def fail_first_staged_read(path: Path, **kwargs: object) -> bytes:
        nonlocal staged_reads
        if path.is_relative_to(pending_root):
            staged_reads += 1
            if staged_reads == 1:
                raise OSError("staged image readback failed")
        return original_read(path, **kwargs)

    monkeypatch.setattr(
        tee_image_approval,
        "_read_file_without_reparse_components",
        fail_first_staged_read,
    )
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(
        catalog,
        tmp_path / "output",
        cascade=cascade,
        pending_root=pending_root,
    )

    result = flow.start_chat_batch("TJD-TEE-001", count=2)

    assert result["status"] == "candidate_pending"
    assert result["candidate_id"].endswith("-02")
    assert result["candidate_number"] == 2
    assert len(cascade.calls) == 2
    _, session = flow._load_chat_session(str(result["session_id"]))
    assert "staged image readback failed" in session["failures"][0]["error"]
    assert [path.name for path in pending_root.rglob("*.png")] == [
        result["candidate_id"] + ".png"
    ]
    flow.cancel_chat_batch(str(result["session_id"]))


def test_chat_non_json_provider_metadata_does_not_leave_a_staged_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    pending_root = tmp_path / "pending"
    monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", pending_root)

    class NonJsonMetadataCascade(FakeCascade):
        def generate(self, prompt: str, *, output_dir: Path) -> SimpleNamespace:
            result = super().generate(prompt, output_dir=output_dir)
            result.provider_metadata = {"settings": object()}
            return result

    flow = TeeImageApprovalFlow(
        catalog,
        tmp_path / "output",
        cascade=NonJsonMetadataCascade(),
        pending_root=pending_root,
    )

    result = flow.start_chat_batch("TJD-TEE-001", count=1)

    assert result["status"] == "completed"
    assert result["generated"] == 0
    assert result["failed"] == 1
    assert "not JSON serializable" in result["failures"][0]["error"]
    assert list(pending_root.rglob("*.png")) == []
    assert list(pending_root.glob(".*.presentation.json")) == []
    assert not list(pending_root.glob("*/session.json"))


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



def test_batch_cli_reports_transparency_failures_with_details(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from src.merch import tee_image_approval

    connection, _ = _in_memory_catalog()
    failure = {
        "candidate_id": "abc12345-01",
        "error": "perimeter key color did not meet the confidence rule",
    }

    class FailedBatchFlow:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def generate_batch(
            self, catalog_id: str, *, count: int = 2
        ) -> SimpleNamespace:
            return SimpleNamespace(
                run_id="abc12345",
                approved=(),
                rejected_count=0,
                failures=(failure,),
            )

    monkeypatch.setattr(tee_image_approval, "_live_connection", lambda: connection)
    monkeypatch.setattr(tee_image_approval, "TeeImageApprovalFlow", FailedBatchFlow)

    assert tee_image_approval.main(["--catalog-id", "TJD-TEE-001"]) == 0

    output = capsys.readouterr().out
    assert "1 candidate failure" in output
    assert (
        "abc12345-01: perimeter key color did not meet the confidence rule"
        in output
    )


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
                provider="fal-ai",
                model="black-forest-labs/FLUX.1-Krea-dev",
                route="fal-ai/flux/krea",
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
                provider="fal-ai",
                model="black-forest-labs/FLUX.1-Krea-dev",
                route="fal-ai/flux/krea",
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
                provider="fal-ai",
                model="black-forest-labs/FLUX.1-Krea-dev",
                route="fal-ai/flux/krea",
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


def _write_workspace_cascade_fixture(
    workspace_src: Path,
    *,
    image_cascade_source: str,
    huggingface_client_source: str = (
        "class HuggingFaceImageClient:\n    value = 'fixture'\n"
    ),
    dalle3_init_source: str = "from .client import DallE3Client\n",
    huggingface_init_source: str = "from .client import HuggingFaceImageClient\n",
) -> dict[str, str]:
    sources = {
        "image_cascade.py": image_cascade_source,
        "dalle3/__init__.py": dalle3_init_source,
        "dalle3/client.py": "class DallE3Client: pass\n",
        "huggingface/__init__.py": huggingface_init_source,
        "huggingface/client.py": huggingface_client_source,
        "pollinations/__init__.py": "",
        "pollinations/client.py": "class PollinationsClient: pass\n",
    }
    integration_dir = workspace_src / "integrations"
    for relative_path, source in sources.items():
        path = integration_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    return {
        relative_path: hashlib.sha256(
            (integration_dir / relative_path).read_bytes()
        ).hexdigest()
        for relative_path in sources
    }


@pytest.mark.skipif(os.name != "nt", reason="Windows secure source reader")
def test_workspace_secure_reader_supports_the_canonical_source_volume() -> None:
    from src.merch import tee_image_approval

    source_path = (
        tee_image_approval._resolve_workspace_src()
        / "integrations"
        / "image_cascade.py"
    )
    if not source_path.is_file():
        pytest.skip("Canonical Workspace image cascade source is unavailable")

    expected_bytes = source_path.read_bytes()

    assert (
        tee_image_approval._read_file_without_reparse_components(source_path)
        == expected_bytes
    )


def test_secure_writer_creates_nested_file_exclusively(tmp_path: Path) -> None:
    from src.merch import tee_image_approval

    output_path = tmp_path / "nested" / "approved.png"
    tee_image_approval._write_file_exclusive_without_reparse_components(
        output_path, b"approved image bytes"
    )

    assert output_path.read_bytes() == b"approved image bytes"
    with pytest.raises(FileExistsError):
        tee_image_approval._write_file_exclusive_without_reparse_components(
            output_path, b"replacement bytes"
        )
    assert output_path.read_bytes() == b"approved image bytes"


def test_secure_writer_removes_partial_file_when_flush_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.merch import tee_image_approval

    output_path = tmp_path / "nested" / "approved.png"

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("synthetic disk flush failure")

    monkeypatch.setattr(tee_image_approval.os, "fsync", fail_fsync)

    with pytest.raises(OSError, match="synthetic disk flush failure"):
        tee_image_approval._write_file_exclusive_without_reparse_components(
            output_path, b"partial approved image"
        )

    assert not output_path.exists()


def test_tee_approval_lock_excludes_a_second_process(tmp_path: Path) -> None:
    from src.merch import tee_image_approval

    context = multiprocessing.get_context("spawn")
    acquired = context.Event()
    release = context.Event()
    lock_path = tmp_path / "tee-image-approval.lock"
    process = context.Process(
        target=_hold_tee_approval_lock,
        args=(str(lock_path), acquired, release),
    )
    process.start()
    try:
        assert acquired.wait(5), "child process did not acquire the tee lock"
        with pytest.raises(TimeoutError, match="tee approval is busy"):
            with tee_image_approval._tee_approval_lock(
                lock_path=lock_path, timeout_seconds=0.05
            ):
                pass
    finally:
        release.set()
        process.join(5)
        if process.is_alive():
            process.terminate()
            process.join(5)

    assert process.exitcode == 0


def test_catalog_edits_wait_for_tee_approval_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    lock_path = tmp_path / "tee-image-approval.lock"
    _patch_tee_lock(monkeypatch, lock_path, 0.05)
    original_title = catalog.read_prompt("TJD-TEE-001")["title"]
    errors: list[Exception] = []

    with tee_image_approval._tee_approval_lock():
        def edit_from_second_thread() -> None:
            try:
                catalog.edit_prompt(
                    "TJD-TEE-001",
                    {"title": "Concurrent uncoordinated edit"},
                    approved_by_tyler=True,
                )
            except Exception as exc:
                errors.append(exc)

        edit_thread = threading.Thread(target=edit_from_second_thread)
        edit_thread.start()
        edit_thread.join(1)
        assert not edit_thread.is_alive()

    assert len(errors) == 1
    assert isinstance(errors[0], TimeoutError)
    assert "tee approval is busy" in str(errors[0])
    assert catalog.read_prompt("TJD-TEE-001")["title"] == original_title


def test_approved_image_history_scan_runs_without_tee_approval_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    lock_path = tmp_path / "tee-image-approval.lock"
    _patch_tee_lock(monkeypatch, lock_path, 0.05)
    scan_lock_availability: list[bool] = []
    original_scan = tee_image_approval._has_approved_images

    def check_lock_during_scan(*args: object, **kwargs: object) -> bool:
        scan_lock_availability.append(
            _lock_available_to_another_thread(tee_image_approval, lock_path)
        )
        return original_scan(*args, **kwargs)

    monkeypatch.setattr(
        tee_image_approval, "_has_approved_images", check_lock_during_scan
    )
    flow = TeeImageApprovalFlow(
        catalog,
        tmp_path / "output",
        cascade=FakeCascade(),
        pending_root=tmp_path / "pending",
    )

    stage = flow.start_chat_batch("TJD-TEE-001", count=1)

    assert scan_lock_availability == [True]
    flow.cancel_chat_batch(str(stage["session_id"]))


def test_generation_rejects_catalog_edit_during_approved_image_history_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    cascade = FakeCascade()

    def edit_during_scan(*args: object, **kwargs: object) -> bool:
        catalog.edit_prompt(
            "TJD-TEE-001",
            {"title": "Edited while prior approvals were scanned"},
            approved_by_tyler=True,
        )
        return False

    monkeypatch.setattr(
        tee_image_approval, "_has_approved_images", edit_during_scan
    )
    flow = TeeImageApprovalFlow(
        catalog,
        tmp_path / "output",
        cascade=cascade,
        pending_root=tmp_path / "pending",
    )

    with pytest.raises(ValueError, match="changed while approved-image history was scanned"):
        flow.start_chat_batch("TJD-TEE-001", count=1)

    assert cascade.calls == []
    assert not (tmp_path / "pending").exists()


def test_catalog_write_rejects_external_open_transaction(
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection]
) -> None:
    catalog, connection = db_catalog
    original_title = catalog.read_prompt("TJD-TEE-001")["title"]
    connection.execute("BEGIN IMMEDIATE")

    with pytest.raises(RuntimeError, match="outer transaction"):
        catalog.edit_prompt(
            "TJD-TEE-001",
            {"title": "Uncommitted outer transaction edit"},
            approved_by_tyler=True,
        )

    connection.rollback()
    assert catalog.read_prompt("TJD-TEE-001")["title"] == original_title


def test_chat_start_fails_before_generation_when_lock_is_busy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    lock_path = tmp_path / "tee-image-approval.lock"
    _patch_tee_lock(monkeypatch, lock_path, 0.05)
    context = multiprocessing.get_context("spawn")
    acquired = context.Event()
    release = context.Event()
    process = context.Process(
        target=_hold_tee_approval_lock,
        args=(str(lock_path), acquired, release),
    )
    process.start()
    try:
        assert acquired.wait(5), "child process did not acquire the tee lock"
        catalog, _ = db_catalog
        cascade = FakeCascade()
        flow = TeeImageApprovalFlow(
            catalog,
            tmp_path / "output",
            cascade=cascade,
            pending_root=tmp_path / "pending",
        )

        with pytest.raises(TimeoutError, match="tee approval is busy"):
            flow.start_chat_batch("TJD-TEE-001", count=1)

        assert cascade.calls == []
        assert not (tmp_path / "pending").exists()
    finally:
        release.set()
        process.join(5)
        if process.is_alive():
            process.terminate()
            process.join(5)

    assert process.exitcode == 0


def test_chat_provider_call_runs_without_approval_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    lock_path = tmp_path / "tee-image-approval.lock"
    _patch_tee_lock(monkeypatch, lock_path, 0.05)

    class LockCheckingCascade(FakeCascade):
        lock_available_during_generate = False

        def generate(self, prompt: str, *, output_dir: Path) -> SimpleNamespace:
            self.lock_available_during_generate = _lock_available_to_another_thread(
                tee_image_approval, lock_path
            )
            return super().generate(prompt, output_dir=output_dir)

    cascade = LockCheckingCascade()
    flow = TeeImageApprovalFlow(
        catalog,
        tmp_path / "output",
        cascade=cascade,
        pending_root=tmp_path / "pending",
    )
    stage = flow.start_chat_batch("TJD-TEE-001", count=1)

    assert cascade.lock_available_during_generate
    flow.cancel_chat_batch(str(stage["session_id"]))


def test_chat_cancellation_during_provider_call_discards_late_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    lock_path = tmp_path / "tee-image-approval.lock"
    pending_root = tmp_path / "pending"
    _patch_tee_lock(monkeypatch, lock_path, 0.05)
    monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", pending_root)
    cancellation_results: list[dict[str, object]] = []

    class CancellingCascade(FakeCascade):
        flow: TeeImageApprovalFlow

        def generate(self, prompt: str, *, output_dir: Path) -> SimpleNamespace:
            session_dir = next(pending_root.iterdir())
            cancellation = threading.Thread(
                target=lambda: cancellation_results.append(
                    self.flow.cancel_chat_batch(session_dir.name)
                )
            )
            cancellation.start()
            cancellation.join(2)
            assert not cancellation.is_alive()
            return super().generate(prompt, output_dir=output_dir)

    cascade = CancellingCascade()
    flow = TeeImageApprovalFlow(
        catalog,
        tmp_path / "output",
        cascade=cascade,
        pending_root=pending_root,
    )
    cascade.flow = flow

    result = flow.start_chat_batch("TJD-TEE-001", count=1)

    assert cancellation_results[0]["status"] == "cancelled"
    assert result["status"] == "cancelled"
    assert list(pending_root.iterdir()) == []
    assert list((tmp_path / "output").rglob("*.png")) == []


def test_chat_does_not_stage_image_for_concept_edited_during_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_lock

    catalog, _ = db_catalog
    pending_root = tmp_path / "pending"
    monkeypatch.setattr(
        tee_image_lock,
        "TEE_IMAGE_APPROVAL_LOCK_PATH",
        tmp_path / "tee-image-approval.lock",
    )

    class EditingCascade(FakeCascade):
        def generate(self, prompt: str, *, output_dir: Path) -> SimpleNamespace:
            catalog.edit_prompt(
                "TJD-TEE-001",
                {"title": "Edited during provider call"},
                approved_by_tyler=True,
            )
            return super().generate(prompt, output_dir=output_dir)

    flow = TeeImageApprovalFlow(
        catalog,
        tmp_path / "output",
        cascade=EditingCascade(),
        pending_root=pending_root,
    )

    result = flow.start_chat_batch("TJD-TEE-001", count=1)

    assert result["status"] == "stale_concept"
    assert "changed while the provider was generating" in str(result["error"])
    assert list(pending_root.rglob("*.png")) == []
    assert list(pending_root.glob(".*.presentation.json")) == []
    assert catalog.read_prompt("TJD-TEE-001")["title"] == "Edited during provider call"


def test_chat_does_not_retry_stale_prompt_after_provider_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_lock

    catalog, _ = db_catalog
    pending_root = tmp_path / "pending"
    monkeypatch.setattr(
        tee_image_lock,
        "TEE_IMAGE_APPROVAL_LOCK_PATH",
        tmp_path / "tee-image-approval.lock",
    )

    class EditingFailingCascade(FakeCascade):
        def generate(self, prompt: str, *, output_dir: Path) -> SimpleNamespace:
            catalog.edit_prompt(
                "TJD-TEE-001",
                {"title": "Edited during failed provider call"},
                approved_by_tyler=True,
            )
            self.calls.append((prompt, output_dir))
            raise FakeGenerationError("provider unavailable", diagnostics=())

    cascade = EditingFailingCascade()
    flow = TeeImageApprovalFlow(
        catalog,
        tmp_path / "output",
        cascade=cascade,
        pending_root=pending_root,
    )

    result = flow.start_chat_batch("TJD-TEE-001", count=2)

    assert result["status"] == "stale_concept"
    assert "changed while the provider was generating" in str(result["error"])
    assert len(cascade.calls) == 1
    assert list(pending_root.rglob("*.png")) == []
    assert list(pending_root.glob(".*.presentation.json")) == []
    assert list(pending_root.iterdir()) == []


def test_batch_does_not_present_candidate_for_concept_edited_during_generation(
    tmp_path: Path,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    catalog, _ = db_catalog
    decision_calls: list[TeeImageCandidate] = []

    class EditingCascade(FakeCascade):
        def generate(self, prompt: str, *, output_dir: Path) -> SimpleNamespace:
            catalog.edit_prompt(
                "TJD-TEE-001",
                {"title": "Edited during provider call"},
                approved_by_tyler=True,
            )
            return super().generate(prompt, output_dir=output_dir)

    def decide(candidate: TeeImageCandidate) -> bool:
        decision_calls.append(candidate)
        return True

    flow = TeeImageApprovalFlow(
        catalog, tmp_path / "output", cascade=EditingCascade()
    )

    result = flow.generate_batch("TJD-TEE-001", count=1, decide=decide)

    assert decision_calls == []
    assert result.approved == ()
    assert result.failures[0]["error"] == (
        "concept or image prompt changed while the provider was generating"
    )
    assert not (tmp_path / "output").exists() or not list(
        (tmp_path / "output").rglob("*.png")
    )


def test_batch_does_not_request_next_candidate_after_rejection_with_stale_concept(
    tmp_path: Path,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    catalog, _ = db_catalog
    cascade = FakeCascade()

    def reject_after_edit(candidate: TeeImageCandidate) -> bool:
        catalog.edit_prompt(
            "TJD-TEE-001",
            {"title": "Edited during operator review"},
            approved_by_tyler=True,
        )
        return False

    flow = TeeImageApprovalFlow(
        catalog, tmp_path / "output", cascade=cascade
    )

    result = flow.generate_batch(
        "TJD-TEE-001", count=2, decide=reject_after_edit
    )

    assert len(cascade.calls) == 1
    assert result.rejected_count == 1
    assert result.approved == ()
    assert result.failures[-1]["error"] == (
        "concept or image prompt changed before the next provider attempt"
    )


def test_batch_does_not_retry_stale_prompt_after_provider_failure(
    tmp_path: Path,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    catalog, _ = db_catalog

    class EditingFailingCascade(FakeCascade):
        def generate(self, prompt: str, *, output_dir: Path) -> SimpleNamespace:
            catalog.edit_prompt(
                "TJD-TEE-001",
                {"title": "Edited during failed provider call"},
                approved_by_tyler=True,
            )
            self.calls.append((prompt, output_dir))
            raise FakeGenerationError("provider unavailable", diagnostics=())

    cascade = EditingFailingCascade()
    flow = TeeImageApprovalFlow(
        catalog, tmp_path / "output", cascade=cascade
    )

    result = flow.generate_batch("TJD-TEE-001", count=2)

    assert len(cascade.calls) == 1
    assert result.approved == ()
    assert result.failures[-1]["error"] == (
        "concept or image prompt changed before the next provider attempt"
    )


def test_stale_chat_failure_does_not_recreate_cancelled_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    pending_root = tmp_path / "pending"
    monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", pending_root)
    flow = TeeImageApprovalFlow(
        catalog,
        tmp_path / "output",
        cascade=FakeCascade(),
        pending_root=pending_root,
    )
    stage = flow.start_chat_batch("TJD-TEE-001", count=1)
    session_dir, stale_state = flow._load_chat_session(str(stage["session_id"]))
    flow.cancel_chat_batch(str(stage["session_id"]))

    recorded = flow._record_chat_failure_if_active(
        session_dir,
        stale_state,
        {
            "candidate_id": str(stage["candidate_id"]),
            "error": "late staged-write failure",
            "diagnostics": [],
        },
    )

    assert not recorded
    assert not session_dir.exists()
    assert not (pending_root / f".{stage['session_id']}.presentation.json").exists()


def test_batch_decision_callback_runs_without_approval_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    lock_path = tmp_path / "tee-image-approval.lock"
    _patch_tee_lock(monkeypatch, lock_path, 0.05)
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(catalog, tmp_path / "output", cascade=cascade)
    callback_lock_availability: list[bool] = []

    def decide(candidate: TeeImageCandidate) -> bool:
        callback_lock_availability.append(
            _lock_available_to_another_thread(tee_image_approval, lock_path)
        )
        return False

    flow.generate_batch("TJD-TEE-001", count=1, decide=decide)

    assert callback_lock_availability == [True]


@pytest.mark.parametrize("entry_path", ("batch", "chat"))
def test_catalog_approval_update_runs_under_tee_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
    entry_path: str,
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    lock_path = tmp_path / "tee-image-approval.lock"
    _patch_tee_lock(monkeypatch, lock_path, 0.05)
    monkeypatch.setattr(
        tee_image_approval,
        "_create_transparent_derivative",
        lambda *_args: {"status": "success"},
    )
    original_approve = catalog.approve_exact_image
    lock_available_during_commit: list[bool] = []

    def record_lock_boundary(*args: object, **kwargs: object) -> object:
        lock_available_during_commit.append(
            _lock_available_to_another_thread(tee_image_approval, lock_path)
        )
        return original_approve(*args, **kwargs)

    monkeypatch.setattr(catalog, "approve_exact_image", record_lock_boundary)
    output_root = tmp_path / "output"
    pending_root = tmp_path / "pending"
    flow = TeeImageApprovalFlow(
        catalog,
        output_root,
        cascade=FakeCascade(),
        pending_root=pending_root,
    )

    if entry_path == "chat":
        stage = flow.start_chat_batch("TJD-TEE-001", count=1)
        flow.decide_chat_candidate(
            str(stage["session_id"]), str(stage["candidate_id"]), decision="y"
        )
    else:
        flow.generate_batch("TJD-TEE-001", count=1, decide=lambda _candidate: True)

    assert lock_available_during_commit == [False]


@pytest.mark.ci_unavailable
@pytest.mark.skipif(
    os.name == "nt",
    reason="POSIX symlink-parent writer guard; Windows uses native no-follow handles",
)
def test_secure_writer_rejects_symlinked_parent(tmp_path: Path) -> None:
    from src.merch import tee_image_approval

    outside_root = tmp_path / "outside"
    outside_root.mkdir()
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(outside_root, target_is_directory=True)

    with pytest.raises((OSError, RuntimeError), match="reparse|symbolic|symlink|path"):
        tee_image_approval._write_file_exclusive_without_reparse_components(
            linked_parent / "escaped.bin", b"must not escape"
        )

    assert list(outside_root.iterdir()) == []


def test_transparency_conversion_preserves_raced_final_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PIL import Image

    from src.merch import tee_image_approval

    source_path = tmp_path / "approved.png"
    Image.new("RGB", (64, 64), (255, 255, 255)).save(source_path)
    derivative_path, _ = tee_image_approval._transparency_output_paths(source_path)
    protected_bytes = b"pre-existing output must survive"

    def race_final_output(command: list[str], **_kwargs: object) -> None:
        output_path = Path(command[command.index("--output") + 1])
        if output_path != derivative_path:
            Image.new("RGBA", (64, 64), (0, 0, 0, 0)).save(output_path)
        derivative_path.write_bytes(protected_bytes)

    monkeypatch.setattr(tee_image_approval.subprocess, "run", race_final_output)

    result = tee_image_approval._create_transparent_derivative(
        source_path, "01234567-01"
    )

    assert result["status"] == "failed"
    assert derivative_path.read_bytes() == protected_bytes


def test_transparency_readback_failure_removes_new_final_derivative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PIL import Image

    from src.merch import tee_image_approval

    source_path = tmp_path / "approved.png"
    Image.new("RGB", (64, 64), (255, 255, 255)).save(source_path)
    derivative_path, sidecar_path = tee_image_approval._transparency_output_paths(
        source_path
    )
    monkeypatch.setattr(
        tee_image_approval,
        "_sample_perimeter_key",
        lambda _path: {
            "selected_color": "#ffffff",
            "evidence": {"sample_count": 1},
            "error": None,
        },
    )

    def write_valid_temporary_derivative(
        command: list[str], **_kwargs: object
    ) -> None:
        output_path = Path(command[command.index("--output") + 1])
        Image.new("RGBA", (64, 64), (0, 0, 0, 0)).save(output_path)

    original_read = tee_image_approval._read_file_without_reparse_components

    def fail_final_readback(
        path: Path, *, expected_fingerprint: object = None
    ) -> bytes:
        if path == derivative_path:
            raise OSError("final derivative readback failed")
        return original_read(path, expected_fingerprint=expected_fingerprint)

    monkeypatch.setattr(
        tee_image_approval.subprocess, "run", write_valid_temporary_derivative
    )
    monkeypatch.setattr(
        tee_image_approval, "_read_file_without_reparse_components", fail_final_readback
    )

    result = tee_image_approval._create_transparent_derivative(
        source_path, "01234567-01"
    )

    assert result["status"] == "failed"
    assert "final derivative readback failed" in result["error"]
    assert not derivative_path.exists()
    assert json.loads(sidecar_path.read_text(encoding="utf-8"))["status"] == "failed"


def test_explicit_test_workspace_source_loads_without_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.merch import tee_image_approval

    workspace_root = tmp_path / "workspace"
    approved_hashes = _write_workspace_cascade_fixture(
        workspace_root / "src",
        image_cascade_source=(
            "class Cascade:\n"
            "    def generate(self, prompt, *, output_dir=None):\n"
            "        raise AssertionError('generation must not run in this test')\n"
            "\n"
            "def tee_image_cascade():\n"
            "    return Cascade()\n"
        ),
    )
    monkeypatch.setattr(tee_image_approval, "_WORKSPACE_ROOT", workspace_root)
    monkeypatch.setattr(
        tee_image_approval,
        "_APPROVED_WORKSPACE_CASCADE_SHA256_BY_PATH",
        approved_hashes,
    )

    cascade = tee_image_approval._workspace_cascade()

    assert callable(cascade.generate)


def test_workspace_loader_rejects_unpinned_relative_import_before_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.merch import tee_image_approval

    workspace_root = tmp_path / "workspace"
    workspace_src = workspace_root / "src"
    marker = tmp_path / "unpinned-client-executed"
    approved_hashes = _write_workspace_cascade_fixture(
        workspace_src,
        image_cascade_source=(
            "from .huggingface import HuggingFaceImageClient\n"
            "def tee_image_cascade():\n"
            "    return HuggingFaceImageClient()\n"
        ),
        huggingface_init_source="from .unreviewed_client import HuggingFaceImageClient\n",
    )
    unpinned_client = (
        workspace_src / "integrations" / "huggingface" / "unreviewed_client.py"
    )
    unpinned_client.write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n"
        "class HuggingFaceImageClient: pass\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(tee_image_approval, "_WORKSPACE_ROOT", workspace_root)
    monkeypatch.setattr(
        tee_image_approval,
        "_APPROVED_WORKSPACE_CASCADE_SHA256_BY_PATH",
        approved_hashes,
    )

    with pytest.raises((ImportError, RuntimeError)):
        tee_image_approval._workspace_cascade()

    assert not marker.exists()


def test_workspace_loader_blocks_quantum_module_outside_verified_import_closure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.util
    import sys

    from src.merch import tee_image_approval

    workspace_root = tmp_path / "workspace"
    marker = tmp_path / "quantum-module-executed"
    approved_hashes = _write_workspace_cascade_fixture(
        workspace_root / "src",
        image_cascade_source=(
            "from .huggingface.client import HuggingFaceImageClient\n"
            "def tee_image_cascade():\n"
            "    return HuggingFaceImageClient()\n"
        ),
        huggingface_client_source=(
            "try:\n"
            "    from src.utils.quantum_rt import qRandom\n"
            "except Exception:\n"
            "    def qRandom():\n"
            "        return 0.5\n"
            "class HuggingFaceImageClient: pass\n"
        ),
    )

    class MarkerLoader:
        def create_module(self, spec):
            return None

        def exec_module(self, module) -> None:
            marker.write_text("executed", encoding="utf-8")
            module.qRandom = lambda: 0.5

    class MarkerFinder:
        def find_spec(self, fullname, path=None, target=None):
            if fullname == "src.utils.quantum_rt":
                return importlib.util.spec_from_loader(fullname, MarkerLoader())
            return None

    monkeypatch.setattr(tee_image_approval, "_WORKSPACE_ROOT", workspace_root)
    monkeypatch.setattr(
        tee_image_approval,
        "_APPROVED_WORKSPACE_CASCADE_SHA256_BY_PATH",
        approved_hashes,
    )
    monkeypatch.setattr(sys, "meta_path", [MarkerFinder(), *sys.meta_path])

    cascade = tee_image_approval._workspace_cascade()

    assert not marker.exists()


@pytest.mark.parametrize(
    "relative_path",
    ("huggingface/client.py", "huggingface/__init__.py"),
)
def test_workspace_loader_rejects_tampered_provider_source_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative_path: str,
) -> None:
    from src.merch import tee_image_approval

    workspace_root = tmp_path / "workspace"
    workspace_src = workspace_root / "src"
    marker = tmp_path / "tampered-client-executed"
    approved_hashes = _write_workspace_cascade_fixture(
        workspace_src,
        image_cascade_source=(
            "from .huggingface.client import HuggingFaceImageClient\n"
            "def tee_image_cascade():\n"
            "    return HuggingFaceImageClient()\n"
        ),
    )
    monkeypatch.setattr(tee_image_approval, "_WORKSPACE_ROOT", workspace_root)
    monkeypatch.setattr(
        tee_image_approval,
        "_APPROVED_WORKSPACE_CASCADE_SHA256_BY_PATH",
        approved_hashes,
    )
    cascade_path = workspace_src / "integrations" / "image_cascade.py"
    cascade_bytes = cascade_path.read_bytes()
    tampered_source_path = workspace_src / "integrations" / relative_path
    tampered_source_path.write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n"
        "class HuggingFaceImageClient: pass\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="provenance"):
        tee_image_approval._workspace_cascade()

    assert cascade_path.read_bytes() == cascade_bytes
    assert not marker.exists()


def test_workspace_loader_rejects_tampered_top_level_hash_before_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.merch import tee_image_approval

    workspace_root = tmp_path / "workspace"
    workspace_src = workspace_root / "src"
    marker = tmp_path / "wrong-top-level-hash-executed"
    approved_hashes = _write_workspace_cascade_fixture(
        workspace_src,
        image_cascade_source=(
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n"
            "def tee_image_cascade():\n"
            "    return object()\n"
        ),
    )
    approved_hashes["image_cascade.py"] = "0" * 64
    monkeypatch.setattr(tee_image_approval, "_WORKSPACE_ROOT", workspace_root)
    monkeypatch.setattr(
        tee_image_approval,
        "_APPROVED_WORKSPACE_CASCADE_SHA256_BY_PATH",
        approved_hashes,
    )

    with pytest.raises(RuntimeError, match="provenance"):
        tee_image_approval._workspace_cascade()

    assert not marker.exists()


def test_workspace_loader_executes_verified_bytes_after_source_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.merch import tee_image_approval

    workspace_root = tmp_path / "workspace"
    workspace_src = workspace_root / "src"
    marker = tmp_path / "changed-client-executed"
    changed_client_source = (
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n"
        "class HuggingFaceImageClient:\n    value = 'changed'\n"
    )
    approved_hashes = _write_workspace_cascade_fixture(
        workspace_src,
        image_cascade_source=(
            "from .huggingface.client import HuggingFaceImageClient\n"
            "def tee_image_cascade():\n"
            "    return HuggingFaceImageClient()\n"
        ),
        huggingface_client_source=(
            "class HuggingFaceImageClient:\n    value = 'verified'\n"
        ),
        dalle3_init_source=(
            "from pathlib import Path\n"
            "from .client import DallE3Client\n"
            "target = Path(__file__).resolve().parents[1] / 'huggingface' / 'client.py'\n"
            f"target.write_text({changed_client_source!r}, encoding='utf-8')\n"
        ),
    )
    monkeypatch.setattr(tee_image_approval, "_WORKSPACE_ROOT", workspace_root)
    monkeypatch.setattr(
        tee_image_approval,
        "_APPROVED_WORKSPACE_CASCADE_SHA256_BY_PATH",
        approved_hashes,
    )

    cascade = tee_image_approval._workspace_cascade()

    assert cascade.value == "verified"
    assert not marker.exists()
    assert (
        workspace_src / "integrations" / "huggingface" / "client.py"
    ).read_text(encoding="utf-8") == changed_client_source


def test_production_workspace_loader_rejects_environment_source_before_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.merch import tee_image_approval

    trusted_root = tmp_path / "trusted-workspace"
    trusted_src = trusted_root / "src"
    attacker_src = tmp_path / "attacker" / "src"
    trusted_marker = tmp_path / "trusted-executed"
    attacker_marker = tmp_path / "attacker-executed"
    approved_hashes = _write_workspace_cascade_fixture(
        trusted_src,
        image_cascade_source=(
            "def tee_image_cascade():\n"
            "    return object()\n"
        ),
    )
    (trusted_src / "integrations" / "image_cascade.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(trusted_marker)!r}).write_text('executed', encoding='utf-8')\n"
        "def tee_image_cascade():\n"
        "    return object()\n",
        encoding="utf-8",
    )
    attacker_cascade = attacker_src / "integrations" / "image_cascade.py"
    attacker_cascade.parent.mkdir(parents=True)
    attacker_cascade.write_text(
        "from pathlib import Path\n"
        f"Path({str(attacker_marker)!r}).write_text('executed', encoding='utf-8')\n"
        "def tee_image_cascade():\n"
        "    return object()\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(tee_image_approval, "_WORKSPACE_ROOT", trusted_root)
    monkeypatch.setattr(
        tee_image_approval,
        "_APPROVED_WORKSPACE_CASCADE_SHA256_BY_PATH",
        approved_hashes,
    )
    monkeypatch.setenv("WORKSPACE_SRC", str(attacker_src))
    with pytest.raises(RuntimeError, match="provenance"):
        tee_image_approval._workspace_cascade()

    assert not trusted_marker.exists()
    assert not attacker_marker.exists()


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


def test_production_workspace_source_ignores_environment_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.merch import tee_image_approval

    workspace_root = tmp_path / "workspace"
    override_src = tmp_path / "configured-workspace" / "src"
    monkeypatch.setenv("WORKSPACE_SRC", str(override_src))
    monkeypatch.setattr(tee_image_approval, "_WORKSPACE_ROOT", workspace_root)

    assert tee_image_approval._resolve_workspace_src() == workspace_root / "src"


def test_approved_asset_keeps_provenance_from_selected_workspace_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    workspace_root = tmp_path / "workspace"
    canonical_src = workspace_root / "src"
    image_cascade_source = (
        "from pathlib import Path\n"
        "from types import SimpleNamespace\n"
        "\n"
        "class Cascade:\n"
        "    def generate(self, prompt, *, output_dir=None):\n"
        "        path = Path(output_dir) / 'candidate.png'\n"
        "        path.write_bytes(b'\\x89PNG\\r\\n\\x1a\\nworkspace-image')\n"
        "        return SimpleNamespace(path=path, provider='fal-ai', "
        "model='black-forest-labs/FLUX.1-Krea-dev', route='fal-ai/flux/krea', "
        "diagnostics=())\n"
        "\n"
        "def tee_image_cascade():\n"
        "    return Cascade()\n"
    )
    approved_hashes = _write_workspace_cascade_fixture(
        canonical_src,
        image_cascade_source=image_cascade_source,
    )
    monkeypatch.setattr(tee_image_approval, "_WORKSPACE_ROOT", workspace_root)
    monkeypatch.setattr(
        tee_image_approval,
        "_APPROVED_WORKSPACE_CASCADE_SHA256_BY_PATH",
        approved_hashes,
    )

    catalog, _ = db_catalog
    flow = TeeImageApprovalFlow(
        catalog, tmp_path / "output", cascade=tee_image_approval._workspace_cascade()
    )

    run = flow.generate_batch("TJD-TEE-001", count=1, decide=lambda candidate: True)

    sidecar = json.loads(run.approved[0].path.with_suffix(".json").read_text(encoding="utf-8"))
    assert sidecar["provider"] == "fal-ai"
    assert sidecar["model"] == "black-forest-labs/FLUX.1-Krea-dev"
    assert sidecar["provider_route"] == "fal-ai/flux/krea"


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



def test_generation_prompt_omits_catalog_garment_use(tmp_path: Path) -> None:
    connection, catalog = _in_memory_catalog()
    prompt_entry = catalog.read_prompt("TJD-TEE-001")
    garment_use = str(prompt_entry["intended_garment_use"])
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(catalog, tmp_path / "output", cascade=cascade)

    try:
        flow.generate_batch("TJD-TEE-001", count=1, decide=lambda candidate: False)

        generated_prompt = cascade.calls[0][0]
        assert f"Garment use: {garment_use}" not in generated_prompt
        assert "Garment use:" not in generated_prompt
        assert "Prompt revision: tee-artwork-prompt-v3" in generated_prompt
        assert catalog.read_prompt("TJD-TEE-001")["intended_garment_use"] == garment_use
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
        assert sidecar["prompt_revision"] == "tee-artwork-prompt-v3"
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


def test_chat_rejects_coordinated_session_candidate_and_presentation_edits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    pending_root = tmp_path / "pending"
    output_root = tmp_path / "output"
    monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", pending_root)
    monkeypatch.setattr(
        tee_image_approval,
        "_create_transparent_derivative",
        lambda *_args: {"status": "not_requested"},
    )
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=FakeCascade())
    stage = flow.start_chat_batch("TJD-TEE-001", count=1)
    pending_path = Path(stage["image_path"])
    session_dir = pending_path.parent
    session_path = session_dir / "session.json"
    session = json.loads(session_path.read_text(encoding="utf-8"))
    pending = session["pending_candidate"]
    forged_bytes = b"\x89PNG\r\n\x1a\nforged-provider-provenance"
    pending_path.write_bytes(forged_bytes)
    pending["provider_metadata"] = {"request_id": "forged-request-reference"}
    pending["content_sha256"] = hashlib.sha256(forged_bytes).hexdigest()
    pending["file_fingerprint"] = list(
        tee_image_approval._stat_fingerprint(pending_path.stat())
    )
    session_path.write_text(
        json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    presentation_path = (
        session_dir.parent / f".{stage['session_id']}.presentation.json"
    )
    presentation = json.loads(presentation_path.read_text(encoding="utf-8"))
    original_directory_fingerprint = presentation["directory_fingerprint"]
    directory_stat = session_dir.stat()
    os.utime(
        session_dir,
        ns=(directory_stat.st_atime_ns, directory_stat.st_mtime_ns + 100_000_000),
    )
    presentation["directory_fingerprint"] = list(
        tee_image_approval._stat_fingerprint(session_dir.stat())
    )
    presentation_path.write_text(
        json.dumps(presentation, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    assert pending["content_sha256"] == hashlib.sha256(forged_bytes).hexdigest()
    assert pending["file_fingerprint"] == list(
        tee_image_approval._stat_fingerprint(pending_path.stat())
    )
    assert presentation["directory_fingerprint"] != original_directory_fingerprint

    with pytest.raises(ValueError, match="candidate changed after presentation"):
        flow.decide_chat_candidate(
            stage["session_id"], stage["candidate_id"], decision="y"
        )

    assert not output_root.exists()
    assert catalog.read_prompt("TJD-TEE-001")["exact_image_approval_status"] == (
        "not_started"
    )


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


def test_chat_rejects_approved_image_changed_before_readback(
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
    original_writer = tee_image_approval._write_file_exclusive_without_reparse_components
    replacement_bytes = b"\x89PNG\r\n\x1a\nchanged after approved write"
    replacement_applied = False

    def replace_after_write(path: Path, content: bytes) -> None:
        nonlocal replacement_applied
        original_writer(path, content)
        if Path(path).suffix == ".png" and Path(path).is_relative_to(output_root):
            Path(path).write_bytes(replacement_bytes)
            replacement_applied = True

    monkeypatch.setattr(
        tee_image_approval,
        "_write_file_exclusive_without_reparse_components",
        replace_after_write,
    )

    with pytest.raises(OSError, match="readback"):
        flow.decide_chat_candidate(
            stage["session_id"], stage["candidate_id"], decision="y"
        )

    assert replacement_applied
    assert catalog.read_prompt("TJD-TEE-001")["exact_image_approval_status"] == (
        "not_started"
    )
    assert list(output_root.rglob("*.json")) == []


def test_chat_staging_rejects_provider_image_replaced_before_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    from src.merch import tee_image_approval

    catalog, _ = db_catalog
    pending_root = tmp_path / "pending"
    monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", pending_root)
    cascade = FakeCascade()
    flow = TeeImageApprovalFlow(catalog, tmp_path / "output", cascade=cascade)
    original_reparse_check = tee_image_approval._is_reparse_point
    replacement_bytes = b"\x89PNG\r\n\x1a\nsubstituted provider image"
    replacement_applied = False

    def replace_after_path_check(path: Path) -> bool:
        nonlocal replacement_applied
        result = original_reparse_check(path)
        if (
            not replacement_applied
            and cascade.calls
            and Path(path) == cascade.calls[0][1] / "candidate-1.png"
        ):
            source_path = Path(path)
            replacement_path = source_path.with_name("replacement.png")
            replacement_path.write_bytes(replacement_bytes)
            replacement_path.replace(source_path)
            replacement_applied = True
        return result

    monkeypatch.setattr(
        tee_image_approval, "_is_reparse_point", replace_after_path_check
    )

    stage = flow.start_chat_batch("TJD-TEE-001", count=1)

    assert replacement_applied
    assert stage["status"] != "candidate_pending"
    assert list(pending_root.rglob("*.png")) == []


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


def test_default_output_root_uses_shared_repository_root_from_worktree() -> None:
    import subprocess

    from src.merch import tee_image_approval

    project_root = Path(__file__).resolve().parents[1]
    git_common_dir = subprocess.run(
        [
            "git",
            "-C",
            str(project_root),
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    main_project_root = Path(git_common_dir).parent.resolve()

    assert tee_image_approval._OUTPUT_ROOT == (
        main_project_root / "output" / "images" / "tee-merch"
    )
