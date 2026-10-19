from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

import pytest
from pytest_bdd import given, scenario, then, when

from src.merch import tee_image_approval
import hashlib
from src.merch.tee_image_approval import TeeImageApprovalFlow
from src.merch.tee_prompt_catalog import TeePromptCatalog
from src.utils import init_db


@dataclass
class _ProvenanceContext:
    flow: TeeImageApprovalFlow
    connection: sqlite3.Connection
    output_root: Path
    stage: dict[str, object] | None = None
    session: dict[str, object] | None = None
    sidecar: dict[str, object] | None = None


class _ProviderCascade:
    def generate(self, prompt: str, *, output_dir: Path) -> SimpleNamespace:
        output_dir.mkdir(parents=True, exist_ok=True)
        image_path = output_dir / "candidate.png"
        image_path.write_bytes(b"\x89PNG\r\n\x1a\nprovider image")
        return SimpleNamespace(
            path=image_path,
            provider="fal-ai",
            model="black-forest-labs/FLUX.1-Krea-dev",
            route="fal-ai/flux/krea",
            provider_metadata={"request_id": "fal-request-reference"},
            diagnostics=(),
        )


@scenario(
    "tee_image_provider_provenance.feature",
    "Pending and approved candidates preserve the actual provider route",
)
def test_pending_and_approved_candidates_preserve_the_actual_provider_route() -> None:
    pass


@scenario(
    "tee_image_provider_provenance.feature",
    "Music selects the Workspace tee authorization cascade",
)
def test_music_selects_the_workspace_tee_authorization_cascade() -> None:
    pass


@given(
    "an approved tee concept and a provider response with limited metadata",
    target_fixture="provenance_context",
)
def approved_concept_with_provider_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[_ProvenanceContext]:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(init_db._SCHEMA_SQL)
    init_db.import_tee_catalog_bootstrap(connection)
    output_root = tmp_path / "approved"
    monkeypatch.setenv(
        "HEARTMUSIC_DB_KEY",
        "test-only-music-approval-integrity-key-not-a-secret",
    )
    monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", tmp_path / "pending")
    monkeypatch.setattr(
        tee_image_approval,
        "_create_transparent_derivative",
        lambda *_args: {"status": "not_requested"},
    )
    flow = TeeImageApprovalFlow(
        TeePromptCatalog(connection), output_root, cascade=_ProviderCascade()
    )
    try:
        yield _ProvenanceContext(flow, connection, output_root)
    finally:
        connection.close()


@when("its image is staged and explicitly approved")
def stage_and_approve_provider_image(provenance_context: _ProvenanceContext) -> None:
    stage = provenance_context.flow.start_chat_batch("TJD-TEE-001", count=1)
    pending_path = Path(str(stage["image_path"]))
    session = json.loads((pending_path.parent / "session.json").read_text(encoding="utf-8"))
    provenance_context.flow.decide_chat_candidate(
        str(stage["session_id"]), str(stage["candidate_id"]), decision="y"
    )
    sidecar_path = (
        provenance_context.output_root
        / "TJD-TEE-001"
        / str(stage["run_id"])
        / f"{stage['candidate_id']}.json"
    )
    provenance_context.stage = stage
    provenance_context.session = session
    provenance_context.sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))


@then(
    "pending results and the approved sidecar preserve provenance and mark unavailable metadata unverified"
)
def assert_provider_provenance_and_metadata_status(
    provenance_context: _ProvenanceContext,
) -> None:
    assert provenance_context.stage is not None
    assert provenance_context.session is not None
    assert provenance_context.sidecar is not None
    expected_provenance = {
        "provider": "fal-ai",
        "model": "black-forest-labs/FLUX.1-Krea-dev",
        "provider_route": "fal-ai/flux/krea",
    }
    for source in (
        provenance_context.stage,
        provenance_context.session["pending_candidate"],
        provenance_context.sidecar,
    ):
        assert {key: source[key] for key in expected_provenance} == expected_provenance
        assert source["provider_metadata"] == {"request_id": "fal-request-reference"}
        assert source["provider_metadata_status"] == {
            "job_id": "unverified",
            "immutable_revision": "unverified",
            "seed": "unverified",
            "settings": "unverified",
        }


@given(
    "Workspace exports distinct generic and tee cascade factories",
    target_fixture="workspace_cascade_context",
)
def workspace_with_distinct_cascades(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Path]:
    workspace_root = tmp_path / "workspace"
    workspace_src = workspace_root / "src"
    integration_dir = workspace_src / "integrations"
    sources = {
        "image_cascade.py": (
            "from .dalle3 import DallE3Client\n"
            "from .huggingface import HuggingFaceImageClient\n"
            "from .pollinations import PollinationsClient\n\n"
            "def default_image_cascade():\n"
            "    raise AssertionError('generic image cascade must not be selected')\n\n"
            "def tee_image_cascade():\n"
            "    return 'tee-authorized-cascade'\n"
        ),
        "dalle3/__init__.py": "from .client import DallE3Client\n",
        "dalle3/client.py": "class DallE3Client: pass\n",
        "huggingface/__init__.py": "from .client import HuggingFaceImageClient\n",
        "huggingface/client.py": "class HuggingFaceImageClient: pass\n",
        "pollinations/__init__.py": "from .client import PollinationsClient\n",
        "pollinations/client.py": "class PollinationsClient: pass\n",
    }
    approved_hashes: dict[str, str] = {}
    for relative_path, source in sources.items():
        path = integration_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        approved_hashes[relative_path] = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(tee_image_approval, "_WORKSPACE_ROOT", workspace_root)
    monkeypatch.setattr(
        tee_image_approval,
        "_APPROVED_WORKSPACE_CASCADE_SHA256_BY_PATH",
        approved_hashes,
    )
    return {"workspace_src": workspace_src}


@when("Music resolves its default tee cascade")
def resolve_workspace_tee_cascade(
    workspace_cascade_context: dict[str, Path],
) -> None:
    workspace_cascade_context["cascade"] = tee_image_approval._workspace_cascade()


@then("it selects the tee factory and never calls the generic factory")
def assert_music_selects_tee_factory(
    workspace_cascade_context: dict[str, Path],
) -> None:
    assert workspace_cascade_context["cascade"] == "tee-authorized-cascade"