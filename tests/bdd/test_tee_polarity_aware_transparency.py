from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator, Sequence

import pytest
from PIL import Image
from pytest_bdd import given, scenario, then, when

from src.merch import tee_image_approval
from src.merch.tee_image_approval import TeeImageApprovalFlow, TeeImageBatchResult
from src.merch.tee_prompt_catalog import TeePromptCatalog
from src.utils import init_db


class _SyntheticCascade:
    def __init__(self, perimeter_mode: str = "confident") -> None:
        self.prompts: list[str] = []
        self.perimeter_mode = perimeter_mode
        self.generated_payloads: list[bytes] = []

    def generate(self, prompt: str, *, output_dir: Path) -> SimpleNamespace:
        self.prompts.append(prompt)
        output_dir.mkdir(parents=True, exist_ok=True)
        image_path = output_dir / "candidate.png"
        dark_blank = "darker key edge" not in prompt.lower()
        background = (24, 28, 34) if dark_blank else (238, 236, 230)
        key_color = (238, 226, 197) if dark_blank else (28, 32, 38)
        runner_up = (110, 110, 110)
        image = Image.new("RGB", (64, 64), background)
        perimeter = (
            [(x, 0) for x in range(64)]
            + [(63, y) for y in range(1, 64)]
            + [(x, 63) for x in range(62, -1, -1)]
            + [(0, y) for y in range(62, 0, -1)]
        )
        for index, point in enumerate(perimeter):
            if self.perimeter_mode == "ambiguous":
                use_key = index < len(perimeter) // 2
            elif self.perimeter_mode == "confident":
                use_key = index >= len(perimeter) // 8
            else:
                use_key = True
            image.putpixel(point, key_color if use_key else runner_up)
        image.save(image_path, format="PNG")
        self.generated_payloads.append(image_path.read_bytes())
        return SimpleNamespace(
            path=image_path,
            provider="synthetic",
            model="offline-fixture",
            diagnostics=(),
        )


@dataclass
class _FlowContext:
    flow: TeeImageApprovalFlow
    cascade: _SyntheticCascade
    connection: sqlite3.Connection
    catalog: TeePromptCatalog
    output_root: Path
    result: TeeImageBatchResult | None = None
    prompt_batches: list[tuple[str, ...]] = field(default_factory=list)
    state: dict[str, object] = field(default_factory=dict)


def _new_flow_context(
    tmp_path: Path,
    *,
    perimeter_mode: str = "confident",
    monkeypatch: pytest.MonkeyPatch | None = None,
) -> _FlowContext:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(init_db._SCHEMA_SQL)
    init_db.import_tee_catalog_bootstrap(connection)
    catalog = TeePromptCatalog(connection)
    cascade = _SyntheticCascade(perimeter_mode)
    output_root = tmp_path / "tee-output"
    if monkeypatch is not None:
        monkeypatch.setattr(tee_image_approval, "_PENDING_ROOT", tmp_path / "pending")
    flow = TeeImageApprovalFlow(catalog, output_root, cascade=cascade)
    return _FlowContext(
        flow=flow,
        cascade=cascade,
        connection=connection,
        catalog=catalog,
        output_root=output_root,
    )


def _managed_context(context: _FlowContext) -> Iterator[_FlowContext]:
    try:
        yield context
    finally:
        context.connection.close()


def _derivative_path(source_path: Path) -> Path:
    return source_path.with_name(f"{source_path.stem}_transparent.png")


def _transformation_sidecar_path(source_path: Path) -> Path:
    return source_path.with_name(f"{source_path.stem}_transparency.json")


@scenario(
    "tee_polarity_aware_transparency.feature",
    "Authorized candidate prompts alternate edge polarity",
)
def test_authorized_candidate_prompts_alternate_edge_polarity() -> None:
    pass


@given(
    "an approved tee concept with authorization for one through four candidates",
    target_fixture="prompt_context",
)
def approved_tee_flow(tmp_path: Path) -> Iterator[_FlowContext]:
    yield from _managed_context(_new_flow_context(tmp_path))


@when("candidate prompts are assembled for each authorized count")
def assemble_prompts_for_authorized_counts(prompt_context: _FlowContext) -> None:
    for count in range(1, 5):
        first_prompt = len(prompt_context.cascade.prompts)
        prompt_context.result = prompt_context.flow.generate_batch(
            "TJD-TEE-001", count=count, decide=lambda _candidate: False
        )
        prompt_context.prompt_batches.append(
            tuple(prompt_context.cascade.prompts[first_prompt:])
        )


@then(
    "the prompts alternate lighter keys on dark blanks and darker keys on light blanks"
)
def prompts_alternate_edge_polarity(prompt_context: _FlowContext) -> None:
    expected_polarities = (
        ("lighter key edge", "dark blank"),
        ("darker key edge", "light blank"),
        ("lighter key edge", "dark blank"),
        ("darker key edge", "light blank"),
    )
    assert [len(batch) for batch in prompt_context.prompt_batches] == [1, 2, 3, 4]
    for batch in prompt_context.prompt_batches:
        for prompt, (edge, blank) in zip(batch, expected_polarities):
            assert edge in prompt.lower()
            assert blank in prompt.lower()
            assert "reserve the key shade for the border" in prompt.lower()
            assert "touch at least one point on the image perimeter" in prompt.lower()
            assert "irregular or partial" in prompt.lower()


@scenario(
    "tee_polarity_aware_transparency.feature",
    "Only explicitly approved authorized candidates get derivatives",
)
def test_only_explicitly_approved_candidates_get_derivatives() -> None:
    pass


@given(
    "chat and batch flows authorize two individually decided candidates",
    target_fixture="approval_context",
)
def two_candidate_approval_flows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[_FlowContext]:
    yield from _managed_context(
        _new_flow_context(tmp_path, monkeypatch=monkeypatch)
    )


@when("one candidate is approved and one is rejected through each flow")
def decide_candidates_through_both_flows(approval_context: _FlowContext) -> None:
    batch_result = approval_context.flow.generate_batch(
        "TJD-TEE-001",
        count=2,
        decide=lambda candidate: candidate.candidate_id.endswith("-01"),
    )
    batch_approved_path = batch_result.approved[0].path
    batch_rejected_id = f"{batch_result.run_id[:8]}-02"

    chat_cascade = _SyntheticCascade()
    chat_flow = TeeImageApprovalFlow(
        approval_context.catalog,
        approval_context.output_root,
        cascade=chat_cascade,
    )
    first_stage = chat_flow.start_chat_batch("TJD-TEE-001", count=2)
    first_id = str(first_stage["candidate_id"])
    second_stage = chat_flow.decide_chat_candidate(
        str(first_stage["session_id"]), first_id, decision="n"
    )
    second_id = str(second_stage["candidate_id"])
    chat_result = chat_flow.decide_chat_candidate(
        str(second_stage["session_id"]), second_id, decision="y"
    )
    chat_approved_path = (
        approval_context.output_root
        / "TJD-TEE-001"
        / str(first_stage["run_id"])
        / f"{second_id}.png"
    )

    with pytest.raises(ValueError, match="between 1 and 4"):
        approval_context.flow.generate_batch("TJD-TEE-001", count=5)
    with pytest.raises(ValueError, match="between 1 and 4"):
        chat_flow.start_chat_batch("TJD-TEE-001", count=5)

    approval_context.result = batch_result
    approval_context.state.update(
        {
            "batch_approved_path": batch_approved_path,
            "batch_rejected_id": batch_rejected_id,
            "chat_approved_path": chat_approved_path,
            "chat_rejected_id": first_id,
            "chat_result": chat_result,
            "chat_cascade": chat_cascade,
        }
    )


@then("only approved candidates get derivatives and unauthorized candidates are rejected")
def only_approved_candidates_get_derivatives(approval_context: _FlowContext) -> None:
    batch_approved_path = approval_context.state["batch_approved_path"]
    chat_approved_path = approval_context.state["chat_approved_path"]
    assert isinstance(batch_approved_path, Path)
    assert isinstance(chat_approved_path, Path)
    assert approval_context.result is not None
    assert len(approval_context.result.approved) == 1
    assert approval_context.result.rejected_count == 1
    assert approval_context.state["chat_result"]["status"] == "completed"
    assert approval_context.state["chat_result"]["approved"] == 1
    assert approval_context.state["chat_result"]["rejected"] == 1

    actual_derivatives = set(approval_context.output_root.rglob("*_transparent.png"))
    expected_derivatives = {
        _derivative_path(batch_approved_path),
        _derivative_path(chat_approved_path),
    }
    assert actual_derivatives == expected_derivatives
    chat_sidecar = json.loads(
        _transformation_sidecar_path(chat_approved_path).read_text(encoding="utf-8")
    )
    assert chat_sidecar["polarity"] == "darker-key-on-light-blank"
    for candidate_id in (
        approval_context.state["batch_rejected_id"],
        approval_context.state["chat_rejected_id"],
    ):
        assert not list(approval_context.output_root.rglob(f"{candidate_id}_transparent.png"))
    assert len(approval_context.cascade.prompts) == 2
    assert len(approval_context.state["chat_cascade"].prompts) == 2


@scenario(
    "tee_polarity_aware_transparency.feature",
    "A confident approved PNG creates a configured transparent derivative",
)
def test_confident_approved_png_creates_transparent_derivative() -> None:
    pass


@given(
    "a synthetic PNG whose perimeter key meets the confidence rule",
    target_fixture="success_context",
)
def confident_perimeter_png(tmp_path: Path) -> Iterator[_FlowContext]:
    yield from _managed_context(_new_flow_context(tmp_path))


@when("exact-image approval triggers post-approval conversion")
def approve_and_convert_confident_image(
    success_context: _FlowContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_run = subprocess.run
    commands: list[list[str]] = []

    def record_command(
        command: Sequence[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        commands.append([str(part) for part in command])
        return real_run(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", record_command)
    success_context.result = success_context.flow.generate_batch(
        "TJD-TEE-001", count=1, decide=lambda _candidate: True
    )
    success_context.state["conversion_commands"] = commands
    success_context.state["source_bytes"] = success_context.cascade.generated_payloads[0]


@then("the opaque source is unchanged and a configured RGBA derivative and sidecar are saved")
def verify_confident_transparency_result(success_context: _FlowContext) -> None:
    assert success_context.result is not None
    assert len(success_context.result.approved) == 1
    source_path = success_context.result.approved[0].path
    source_bytes = success_context.state["source_bytes"]
    assert isinstance(source_bytes, bytes)
    assert source_path.read_bytes() == source_bytes
    derivative_path = _derivative_path(source_path)
    sidecar_path = _transformation_sidecar_path(source_path)
    assert derivative_path.is_file()
    assert sidecar_path.is_file()

    with Image.open(derivative_path) as derivative:
        assert derivative.mode == "RGBA"
        assert derivative.getpixel((0, 63))[3] == 0

    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["status"] == "success"
    assert sidecar["selected_color"].startswith("#")
    assert sidecar["polarity"] == "lighter-key-on-dark-blank"
    assert sidecar["sampling"]["sample_count"] == 64
    assert sidecar["sampling"]["dominant_count"] >= 3 * sidecar["sampling"]["runner_up_count"]
    assert sidecar["sampling"]["longest_consecutive_dominant_run"] >= 8
    assert sidecar["settings"] == {
        "global_match": True,
        "tolerance": 10,
        "smooth_radius": 1,
    }
    assert sidecar["source_sha256"] == hashlib.sha256(source_bytes).hexdigest()
    assert sidecar["output_sha256"] == hashlib.sha256(derivative_path.read_bytes()).hexdigest()

    commands = success_context.state["conversion_commands"]
    assert len(commands) == 1
    command = commands[0]
    assert "--global-match" in command
    assert command[command.index("--color") + 1] == sidecar["selected_color"]
    assert command[command.index("--tolerance") + 1] == "10"
    assert command[command.index("--smooth-radius") + 1] == "1"


@scenario(
    "tee_polarity_aware_transparency.feature",
    "Ambiguous perimeter colors preserve approval and source",
)
def test_ambiguous_perimeter_preserves_approval_and_source() -> None:
    pass


@given(
    "a synthetic PNG with ambiguous perimeter colors",
    target_fixture="ambiguous_context",
)
def ambiguous_perimeter_png(tmp_path: Path) -> Iterator[_FlowContext]:
    yield from _managed_context(
        _new_flow_context(tmp_path, perimeter_mode="ambiguous")
    )


@when("exact-image approval triggers an attempted conversion")
def approve_and_attempt_ambiguous_conversion(ambiguous_context: _FlowContext) -> None:
    ambiguous_context.result = ambiguous_context.flow.generate_batch(
        "TJD-TEE-001", count=1, decide=lambda _candidate: True
    )
    ambiguous_context.state["source_bytes"] = ambiguous_context.cascade.generated_payloads[0]


@then("approval and source remain intact, no derivative is created, and failure is reported")
def verify_ambiguous_perimeter_failure(ambiguous_context: _FlowContext) -> None:
    assert ambiguous_context.result is not None
    assert len(ambiguous_context.result.approved) == 1
    source_path = ambiguous_context.result.approved[0].path
    assert source_path.read_bytes() == ambiguous_context.state["source_bytes"]
    assert ambiguous_context.catalog.read_prompt("TJD-TEE-001")[
        "exact_image_approval_status"
    ] == "exact_image_approved"
    assert not _derivative_path(source_path).exists()
    assert ambiguous_context.result.failures
    sidecar_path = _transformation_sidecar_path(source_path)
    assert json.loads(sidecar_path.read_text(encoding="utf-8"))["status"] == "failed"


@scenario(
    "tee_polarity_aware_transparency.feature",
    "Conversion failure removes partial output without revoking approval",
)
def test_conversion_failure_cleans_partial_output_and_preserves_approval() -> None:
    pass


@given(
    "an approved PNG and a conversion process that fails after partial output",
    target_fixture="failed_conversion_context",
)
def failing_conversion_png(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[_FlowContext]:
    context = _new_flow_context(tmp_path, monkeypatch=monkeypatch)
    commands: list[list[str]] = []

    def fail_after_partial_output(
        command: Sequence[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        normalized = [str(part) for part in command]
        commands.append(normalized)
        derivative_path = Path(normalized[normalized.index("--output") + 1])
        derivative_path.write_bytes(b"partial derivative")
        raise subprocess.CalledProcessError(
            2, normalized, stderr="synthetic conversion failure"
        )

    monkeypatch.setattr(subprocess, "run", fail_after_partial_output)
    context.state["conversion_commands"] = commands
    yield from _managed_context(context)


@when("the chat-mediated exact-image decision approves the candidate")
def approve_chat_candidate_with_conversion_failure(
    failed_conversion_context: _FlowContext,
) -> None:
    stage = failed_conversion_context.flow.start_chat_batch("TJD-TEE-001", count=1)
    candidate_id = str(stage["candidate_id"])
    original_bytes = Path(str(stage["image_path"])).read_bytes()
    response = failed_conversion_context.flow.decide_chat_candidate(
        str(stage["session_id"]), candidate_id, decision="y"
    )
    source_path = (
        failed_conversion_context.output_root
        / "TJD-TEE-001"
        / str(stage["run_id"])
        / f"{candidate_id}.png"
    )
    failed_conversion_context.state.update(
        {"source_bytes": original_bytes, "source_path": source_path, "response": response}
    )


@then("approval and source remain intact, partial output is removed, and failure is reported")
def verify_failed_conversion_cleanup(
    failed_conversion_context: _FlowContext,
) -> None:
    source_path = failed_conversion_context.state["source_path"]
    assert isinstance(source_path, Path)
    source_bytes = failed_conversion_context.state["source_bytes"]
    assert isinstance(source_bytes, bytes)
    assert source_path.read_bytes() == source_bytes
    assert failed_conversion_context.catalog.read_prompt("TJD-TEE-001")[
        "exact_image_approval_status"
    ] == "exact_image_approved"
    assert not _derivative_path(source_path).exists()
    assert len(failed_conversion_context.state["conversion_commands"]) == 1
    response = failed_conversion_context.state["response"]
    assert response["transparency"]["status"] == "failed"
    sidecar = json.loads(
        _transformation_sidecar_path(source_path).read_text(encoding="utf-8")
    )
    assert sidecar["status"] == "failed"