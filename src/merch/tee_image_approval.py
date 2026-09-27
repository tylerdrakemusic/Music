r"""Generate tee artwork from approved concepts and retain exact-image approvals.
Run from the Music repository root with
``python -m src.merch.tee_image_approval --chat-start --catalog-id TJD-TEE-001``.
Use ``--count`` to authorize one through four independent candidate calls; the
default is two. Resolve each displayed image with ``--chat-decide`` and cancel
an unfinished session with ``--chat-cancel``. Set ``WORKSPACE_SRC`` when the
Workspace source is not at its standard ``F:\\⊕Workspace\\src`` location.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CATALOG_PATH = _PROJECT_ROOT / "Brand" / "tyler-james-drake-tee-prompt-catalog.json"
_OUTPUT_ROOT = _PROJECT_ROOT / "output" / "images" / "tee-merch"
_PENDING_ROOT = Path(tempfile.gettempdir()) / "tee-image-approval-sessions"
_WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_ROOT", r"F:\⊕Workspace"))
_FEATURE_WORKSPACE_SRC = (
    _WORKSPACE_ROOT
    / ".worktrees"
    / "FR-20260927-tee-image-generation-approval"
    / "workspace"
    / "src"
)
_PROMPT_REVISION = "tee-artwork-prompt-v2"
_MAX_BATCH_SIZE = 4
_CANDIDATE_ART_DIRECTIONS = (
    "T-shirt design in vintage screen-print style: center the main subject in a "
    "balanced, emblematic composition with a sparse background.",
    "Abstract t-shirt design: use a wide environmental composition, placing the "
    "main subject off-center and giving the setting more space.",
    "Line-work t-shirt design: use an intimate close crop on the concept's key "
    "subjects, reducing secondary setting details.",
    "Woodcut-inspired t-shirt design: use a dynamic diagonal composition with "
    "the main subject crossing the frame and bold, simplified background shapes.",
)
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


class ImageCascade(Protocol):
    def generate(self, prompt: str, *, output_dir: Path) -> object: ...


@dataclass(frozen=True)
class TeeImageCandidate:
    """One generated candidate shown to the operator for an exact-image decision."""

    candidate_id: str
    path: Path
    provider: str
    model: str
    exact_prompt: str


@dataclass(frozen=True)
class TeeImageBatchResult:
    """Summary of a batch without retaining rejected image files or decisions."""

    run_id: str
    approved: tuple[TeeImageCandidate, ...]
    rejected_count: int
    failures: tuple[dict[str, object], ...]


Decision = Callable[[TeeImageCandidate], bool]


def _resolve_workspace_src() -> Path:
    configured_src = os.environ.get("WORKSPACE_SRC")
    if configured_src:
        return Path(configured_src)
    if (_FEATURE_WORKSPACE_SRC / "integrations" / "image_cascade.py").is_file():
        return _FEATURE_WORKSPACE_SRC
    return _WORKSPACE_ROOT / "src"


def _workspace_cascade(workspace_src: Path | None = None) -> ImageCascade:
    workspace_src = workspace_src or _resolve_workspace_src()
    integration_dir = workspace_src / "integrations"
    cascade_path = integration_dir / "image_cascade.py"
    if not cascade_path.is_file():
        raise RuntimeError(
            "Workspace image cascade is unavailable; set WORKSPACE_SRC to the Workspace src directory"
        )
    module_name = "_music_workspace_image_cascade_" + hashlib.sha256(
        str(cascade_path.resolve()).encode("utf-8")
    ).hexdigest()[:12]
    module = sys.modules.get(module_name)
    if module is None:
        spec = importlib.util.spec_from_file_location(
            module_name,
            cascade_path,
            submodule_search_locations=[str(integration_dir)],
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"unable to load Workspace cascade from {cascade_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            del sys.modules[module_name]
            raise
    return module.default_image_cascade()


def _diagnostic_dict(diagnostic: object) -> dict[str, object]:
    if isinstance(diagnostic, dict):
        return {str(key): value for key, value in diagnostic.items()}
    if hasattr(diagnostic, "__dict__"):
        return {str(key): value for key, value in vars(diagnostic).items()}
    return {"error": str(diagnostic)}


def _read_catalog(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as catalog_file:
        data = json.load(catalog_file)
    if not isinstance(data, dict) or not isinstance(data.get("prompts"), list):
        raise ValueError("tee prompt catalog must contain a prompts list")
    return data


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _write_catalog(path: Path, catalog: dict[str, object]) -> None:
    _write_json(path, catalog)


def _find_entry(catalog: dict[str, object], catalog_id: str) -> dict[str, object]:
    entries = catalog["prompts"]
    for entry in entries:
        if isinstance(entry, dict) and entry.get("id") == catalog_id:
            return entry
    raise KeyError(f"tee concept not found: {catalog_id}")


def _has_approved_images(output_root: Path, catalog_id: str) -> bool:
    catalog_dir = output_root / catalog_id
    if not catalog_dir.is_dir():
        return False
    for sidecar_path in catalog_dir.rglob("*.json"):
        if sidecar_path.name == "provider-failures.json":
            continue
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            isinstance(sidecar, dict)
            and sidecar.get("catalog_id") == catalog_id
            and sidecar.get("approval") == "approved"
        ):
            return True
    return False


def _compose_prompt(entry: dict[str, object], catalog_revision: str) -> str:
    palette = entry.get("palette", [])
    palette_text = ", ".join(str(color) for color in palette) if isinstance(palette, list) else str(palette)
    return "\n".join(
        (
            f"Catalog ID: {entry['id']}",
            f"Catalog revision: {catalog_revision}",
            f"Prompt revision: {_PROMPT_REVISION}",
            f"Title: {entry['title']}",
            f"Concept: {entry['concept']}",
            f"Garment use: {entry['intended_garment_use']}",
            f"Palette: {palette_text}",
            f"Print notes: {entry['print_notes']}",
            "Create one standalone, opaque tee artwork image. Do not show a garment, person, product mockup, or transparent rendering.",
        )
    )


def _compose_candidate_prompt(exact_prompt: str, candidate_number: int) -> str:
    direction = _CANDIDATE_ART_DIRECTIONS[candidate_number - 1]
    return f"{direction}\n{exact_prompt}"


def _interactive_decision(candidate: TeeImageCandidate) -> bool:
    opener = getattr(os, "startfile", None)
    if opener is not None:
        opener(str(candidate.path))
    print(f"Candidate {candidate.candidate_id}: {candidate.path}")
    while True:
        decision = input("Approve this exact image? [y/n]: ").strip().lower()
        if decision in {"y", "yes"}:
            return True
        if decision in {"n", "no"}:
            return False
        print("Enter y or n.")


class TeeImageApprovalFlow:
    """Run operator-authorized candidate batches and persist approved artwork only."""

    def __init__(
        self,
        catalog_path: Path = _CATALOG_PATH,
        output_root: Path = _OUTPUT_ROOT,
        *,
        cascade: ImageCascade | None = None,
        workspace_src: Path | None = None,
        pending_root: Path | None = None,
    ) -> None:
        self.catalog_path = Path(catalog_path)
        self.output_root = Path(output_root)
        self.pending_root = Path(pending_root) if pending_root is not None else _PENDING_ROOT
        self.cascade = cascade if cascade is not None else _workspace_cascade(workspace_src)

    def _prepare_generation(
        self, catalog_id: str
    ) -> tuple[dict[str, object], dict[str, object], int, str, str, bool]:
        if not re.fullmatch(r"TJD-TEE-\d{3}", catalog_id):
            raise ValueError("catalog ID must use the TJD-TEE-NNN format")

        catalog = _read_catalog(self.catalog_path)
        entry = _find_entry(catalog, catalog_id)
        if entry.get("concept_approval_status") != "concept_approved":
            raise ValueError("tee concept must be concept_approved before image generation")
        try:
            concept_revision = int(entry["concept_revision"])
            approval_revision = int(entry["concept_approval_revision"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                "concept approval revision is missing; return the concept to curation"
            ) from exc

        has_approved_images = (
            entry.get("exact_image_approval_status") == "exact_image_approved"
            or _has_approved_images(self.output_root, catalog_id)
        )
        if approval_revision != concept_revision:
            entry["concept_approval_status"] = "concept_pending"
            if not has_approved_images:
                entry["exact_image_approval_status"] = "not_started"
            _write_catalog(self.catalog_path, catalog)
            raise ValueError("concept revision changed; curation and explicit reapproval are required")

        catalog_revision = f"{catalog.get('version', 'unversioned')}:{concept_revision}"
        exact_prompt = _compose_prompt(entry, catalog_revision)
        entry["exact_image_approval_status"] = (
            "exact_image_approved" if has_approved_images else "exact_image_pending"
        )
        _write_catalog(self.catalog_path, catalog)
        return catalog, entry, concept_revision, catalog_revision, exact_prompt, has_approved_images

    def _chat_session_directory(self, session_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", session_id):
            raise ValueError("chat approval session ID is invalid")
        root = self.pending_root.resolve()
        session_dir = root / session_id
        if session_dir.is_symlink() or session_dir.resolve().parent != root:
            raise ValueError("chat approval session path is invalid")
        return session_dir

    @staticmethod
    def _write_chat_session(session_dir: Path, state: dict[str, object]) -> None:
        _write_json(session_dir / "session.json", state)

    def start_chat_batch(self, catalog_id: str, *, count: int = 2) -> dict[str, object]:
        if type(count) is not int or not 1 <= count <= _MAX_BATCH_SIZE:
            raise ValueError("candidate count must be between 1 and 4")

        catalog, _, concept_revision, catalog_revision, exact_prompt, _ = self._prepare_generation(
            catalog_id
        )
        run_id = uuid.uuid4().hex
        session_id = uuid.uuid4().hex
        session_dir = self._chat_session_directory(session_id)
        session_dir.mkdir(parents=True, exist_ok=False)
        state: dict[str, object] = {
            "session_id": session_id,
            "catalog_id": catalog_id,
            "concept_revision": concept_revision,
            "catalog_revision": catalog_revision,
            "exact_prompt": exact_prompt,
            "run_id": run_id,
            "total_count": count,
            "next_candidate_number": 1,
            "generated_count": 0,
            "approved_count": 0,
            "rejected_count": 0,
            "failures": [],
            "pending_candidate": None,
        }
        self._write_chat_session(session_dir, state)
        return self._stage_next_chat_candidate(session_dir, state)

    def _stage_next_chat_candidate(
        self, session_dir: Path, state: dict[str, object]
    ) -> dict[str, object]:
        session_id = str(state["session_id"])
        catalog_id = str(state["catalog_id"])
        run_id = str(state["run_id"])
        total_count = int(state["total_count"])
        failures = state["failures"]
        assert isinstance(failures, list)

        while int(state["next_candidate_number"]) <= total_count:
            candidate_number = int(state["next_candidate_number"])
            state["next_candidate_number"] = candidate_number + 1
            self._write_chat_session(session_dir, state)
            candidate_id = f"{run_id[:8]}-{candidate_number:02d}"
            candidate_prompt = _compose_candidate_prompt(
                str(state["exact_prompt"]), candidate_number
            )
            with tempfile.TemporaryDirectory(prefix="tee-image-candidate-") as temporary_dir:
                temporary_root = Path(temporary_dir)
                try:
                    result = self.cascade.generate(candidate_prompt, output_dir=temporary_root)
                except Exception as exc:
                    failures.append(
                        {
                            "candidate_id": candidate_id,
                            "error": str(exc),
                            "diagnostics": [
                                _diagnostic_dict(item)
                                for item in getattr(exc, "diagnostics", ())
                            ],
                        }
                    )
                    self._write_chat_session(session_dir, state)
                    continue

                source_path = Path(result.path)
                suffix = source_path.suffix.lower()
                if (
                    not source_path.is_file()
                    or suffix not in _IMAGE_SUFFIXES
                    or not source_path.resolve().is_relative_to(temporary_root.resolve())
                ):
                    failures.append(
                        {
                            "candidate_id": candidate_id,
                            "error": "image cascade returned a missing or unsupported image file",
                            "diagnostics": [
                                _diagnostic_dict(item)
                                for item in getattr(result, "diagnostics", ())
                            ],
                        }
                    )
                    self._write_chat_session(session_dir, state)
                    continue

                image_name = f"{candidate_id}{suffix}"
                staged_path = session_dir / image_name
                shutil.copyfile(source_path, staged_path)
                state["generated_count"] = int(state["generated_count"]) + 1
                state["pending_candidate"] = {
                    "candidate_id": candidate_id,
                    "candidate_number": candidate_number,
                    "image_name": image_name,
                    "provider": str(result.provider),
                    "model": str(result.model),
                    "exact_prompt": candidate_prompt,
                    "provider_diagnostics": [
                        _diagnostic_dict(item)
                        for item in getattr(result, "diagnostics", ())
                    ],
                }
                self._write_chat_session(session_dir, state)
                return {
                    "status": "candidate_pending",
                    "session_id": session_id,
                    "run_id": run_id,
                    "candidate_id": candidate_id,
                    "candidate_number": candidate_number,
                    "count": total_count,
                    "image_path": str(staged_path),
                    "art_direction": candidate_prompt.splitlines()[0],
                    "provider": str(result.provider),
                    "model": str(result.model),
                }

        if failures:
            run_dir = self.output_root / catalog_id / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "provider-failures.json").write_text(
                json.dumps(failures, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        summary = {
            "status": "completed",
            "run_id": run_id,
            "generated": int(state["generated_count"]),
            "approved": int(state["approved_count"]),
            "rejected": int(state["rejected_count"]),
            "failed": len(failures),
            "failures": failures,
        }
        shutil.rmtree(session_dir)
        return summary

    def _load_chat_session(self, session_id: str) -> tuple[Path, dict[str, object]]:
        session_dir = self._chat_session_directory(session_id)
        session_path = session_dir / "session.json"
        try:
            state = json.loads(session_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("chat approval session is unavailable") from exc
        if not isinstance(state, dict) or state.get("session_id") != session_id:
            raise ValueError("chat approval session is invalid")
        if not re.fullmatch(r"TJD-TEE-\d{3}", str(state.get("catalog_id", ""))):
            raise ValueError("chat approval session catalog ID is invalid")
        if not re.fullmatch(r"[0-9a-f]{32}", str(state.get("run_id", ""))):
            raise ValueError("chat approval session run ID is invalid")
        return session_dir, state

    @staticmethod
    def _pending_candidate_path(
        session_dir: Path, pending: dict[str, object]
    ) -> Path:
        candidate_id = str(pending.get("candidate_id", ""))
        image_name = pending.get("image_name")
        if not re.fullmatch(r"[0-9a-f]{8}-\d{2}", candidate_id):
            raise ValueError("pending candidate ID is invalid")
        if not isinstance(image_name, str):
            raise ValueError("pending candidate image is invalid")
        suffix = Path(image_name).suffix.lower()
        if (
            Path(image_name).name != image_name
            or suffix not in _IMAGE_SUFFIXES
            or image_name != f"{candidate_id}{suffix}"
        ):
            raise ValueError("pending candidate image path is invalid")
        image_path = session_dir / image_name
        if image_path.resolve().parent != session_dir.resolve() or not image_path.is_file():
            raise ValueError("pending candidate image is unavailable")
        return image_path

    def decide_chat_candidate(
        self, session_id: str, candidate_id: str, *, decision: str
    ) -> dict[str, object]:
        if decision not in {"y", "n"}:
            raise ValueError("chat decision must be exactly y or n")
        session_dir, state = self._load_chat_session(session_id)
        pending = state.get("pending_candidate")
        if not isinstance(pending, dict):
            raise ValueError("chat approval session has no pending candidate")
        if pending.get("candidate_id") != candidate_id:
            raise ValueError("candidate ID does not match the pending candidate")
        pending_path = self._pending_candidate_path(session_dir, pending)

        if decision == "y":
            catalog = _read_catalog(self.catalog_path)
            entry = _find_entry(catalog, str(state["catalog_id"]))
            try:
                current_revision = int(entry["concept_revision"])
                approval_revision = int(entry["concept_approval_revision"])
            except (KeyError, TypeError, ValueError) as exc:
                pending_path.unlink(missing_ok=True)
                shutil.rmtree(session_dir)
                raise ValueError("concept approval changed while image was pending") from exc
            if (
                entry.get("concept_approval_status") != "concept_approved"
                or current_revision != int(state["concept_revision"])
                or approval_revision != current_revision
            ):
                pending_path.unlink(missing_ok=True)
                shutil.rmtree(session_dir)
                raise ValueError("concept changed while image was pending; return to curation")

            run_dir = self.output_root / str(state["catalog_id"]) / str(state["run_id"])
            approved_path = run_dir / f"{candidate_id}{pending_path.suffix}"
            sidecar_path = run_dir / f"{candidate_id}.json"
            if approved_path.exists() or sidecar_path.exists():
                raise FileExistsError("approved candidate output already exists")
            sidecar = {
                "candidate_id": candidate_id,
                "catalog_id": state["catalog_id"],
                "provider": pending["provider"],
                "model": pending["model"],
                "exact_prompt": pending["exact_prompt"],
                "catalog_revision": state["catalog_revision"],
                "prompt_revision": _PROMPT_REVISION,
                "content_sha256": hashlib.sha256(pending_path.read_bytes()).hexdigest(),
                "approval": "approved",
                "approved_at": datetime.now(timezone.utc).isoformat(),
                "provider_diagnostics": pending["provider_diagnostics"],
            }
            run_dir.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copyfile(pending_path, approved_path)
                _write_json(sidecar_path, sidecar)
                entry["exact_image_approval_status"] = "exact_image_approved"
                _write_catalog(self.catalog_path, catalog)
            except Exception:
                approved_path.unlink(missing_ok=True)
                sidecar_path.unlink(missing_ok=True)
                raise
            state["approved_count"] = int(state["approved_count"]) + 1
        else:
            state["rejected_count"] = int(state["rejected_count"]) + 1

        pending_path.unlink(missing_ok=True)
        state["pending_candidate"] = None
        self._write_chat_session(session_dir, state)
        return self._stage_next_chat_candidate(session_dir, state)

    def cancel_chat_batch(self, session_id: str) -> dict[str, object]:
        session_dir, state = self._load_chat_session(session_id)
        pending = state.get("pending_candidate")
        if isinstance(pending, dict):
            self._pending_candidate_path(session_dir, pending).unlink(missing_ok=True)
        result = {
            "status": "cancelled",
            "run_id": state["run_id"],
            "generated": int(state["generated_count"]),
            "approved": int(state["approved_count"]),
            "rejected": int(state["rejected_count"]),
            "failed": len(state["failures"]),
        }
        shutil.rmtree(session_dir)
        return result

    def generate_batch(
        self,
        catalog_id: str,
        *,
        count: int = 2,
        decide: Decision | None = None,
    ) -> TeeImageBatchResult:
        """Generate an authorized batch and require a decision for each successful image."""
        if type(count) is not int or not 1 <= count <= _MAX_BATCH_SIZE:
            raise ValueError("candidate count must be between 1 and 4")

        catalog, entry, concept_revision, catalog_revision, exact_prompt, has_approved_images = (
            self._prepare_generation(catalog_id)
        )

        run_id = uuid.uuid4().hex
        run_dir = self.output_root / catalog_id / run_id
        approved: list[TeeImageCandidate] = []
        rejected_count = 0
        failures: list[dict[str, object]] = []
        decision_callback = decide if decide is not None else _interactive_decision

        for candidate_number in range(1, count + 1):
            candidate_id = f"{run_id[:8]}-{candidate_number:02d}"
            candidate_prompt = _compose_candidate_prompt(exact_prompt, candidate_number)
            with tempfile.TemporaryDirectory(prefix="tee-image-candidate-") as temporary_dir:
                temporary_root = Path(temporary_dir)
                try:
                    result = self.cascade.generate(candidate_prompt, output_dir=temporary_root)
                except Exception as exc:
                    diagnostics = getattr(exc, "diagnostics", ())
                    failures.append(
                        {
                            "candidate_id": candidate_id,
                            "error": str(exc),
                            "diagnostics": [_diagnostic_dict(item) for item in diagnostics],
                        }
                    )
                    continue

                source_path = Path(result.path)
                if not source_path.is_file() or source_path.suffix.lower() not in {
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".webp",
                }:
                    failures.append(
                        {
                            "candidate_id": candidate_id,
                            "error": "image cascade returned a missing or unsupported image file",
                            "diagnostics": [
                                _diagnostic_dict(item)
                                for item in getattr(result, "diagnostics", ())
                            ],
                        }
                    )
                    continue

                candidate = TeeImageCandidate(
                    candidate_id=candidate_id,
                    path=source_path,
                    provider=str(result.provider),
                    model=str(result.model),
                    exact_prompt=candidate_prompt,
                )
                if not decision_callback(candidate):
                    rejected_count += 1
                    continue

                run_dir.mkdir(parents=True, exist_ok=True)
                suffix = source_path.suffix.lower()
                approved_path = run_dir / f"{candidate_id}{suffix}"
                shutil.copyfile(source_path, approved_path)
                content_hash = hashlib.sha256(approved_path.read_bytes()).hexdigest()
                sidecar = {
                    "candidate_id": candidate_id,
                    "catalog_id": catalog_id,
                    "provider": candidate.provider,
                    "model": candidate.model,
                    "exact_prompt": candidate_prompt,
                    "catalog_revision": catalog_revision,
                    "prompt_revision": _PROMPT_REVISION,
                    "content_sha256": content_hash,
                    "approval": "approved",
                    "approved_at": datetime.now(timezone.utc).isoformat(),
                    "provider_diagnostics": [
                        _diagnostic_dict(item)
                        for item in getattr(result, "diagnostics", ())
                    ],
                }
                sidecar_path = run_dir / f"{candidate_id}.json"
                sidecar_path.write_text(
                    json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                approved.append(
                    TeeImageCandidate(
                        candidate_id=candidate_id,
                        path=approved_path,
                        provider=candidate.provider,
                        model=candidate.model,
                        exact_prompt=exact_prompt,
                    )
                )
                entry["exact_image_approval_status"] = "exact_image_approved"
                _write_catalog(self.catalog_path, catalog)

        if failures:
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "provider-failures.json").write_text(
                json.dumps(failures, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        return TeeImageBatchResult(
            run_id=run_id,
            approved=tuple(approved),
            rejected_count=rejected_count,
            failures=tuple(failures),
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-id")
    parser.add_argument("--count", type=int)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--chat-start", action="store_true")
    mode.add_argument("--chat-decide", action="store_true")
    mode.add_argument("--chat-cancel", action="store_true")
    parser.add_argument("--session-id")
    parser.add_argument("--candidate-id")
    parser.add_argument("--decision", choices=("y", "n"))
    args = parser.parse_args(argv)

    flow = TeeImageApprovalFlow(
        _CATALOG_PATH,
        _OUTPUT_ROOT,
        pending_root=_PENDING_ROOT,
    )
    if args.chat_start:
        if not args.catalog_id or args.session_id or args.candidate_id or args.decision:
            parser.error("--chat-start requires --catalog-id and no decision fields")
        result = flow.start_chat_batch(
            args.catalog_id,
            count=args.count if args.count is not None else 2,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.chat_decide:
        if args.catalog_id or args.count is not None or not all(
            (args.session_id, args.candidate_id, args.decision)
        ):
            parser.error("--chat-decide requires --session-id, --candidate-id, and --decision")
        result = flow.decide_chat_candidate(
            args.session_id,
            args.candidate_id,
            decision=args.decision,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.chat_cancel:
        if (
            args.catalog_id
            or args.count is not None
            or args.candidate_id
            or args.decision
            or not args.session_id
        ):
            parser.error("--chat-cancel requires only --session-id")
        result = flow.cancel_chat_batch(args.session_id)
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if not args.catalog_id or args.session_id or args.candidate_id or args.decision:
        parser.error("--catalog-id is required for terminal-interactive generation")
    result = flow.generate_batch(
        args.catalog_id,
        count=args.count if args.count is not None else 2,
    )
    print(
        f"Run {result.run_id}: {len(result.approved)} approved, "
        f"{result.rejected_count} rejected, {len(result.failures)} provider failures"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())