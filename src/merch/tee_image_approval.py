"""Generate tee artwork from approved concepts and retain exact-image approvals.

Run from the Music repository root with
``python -m src.merch.tee_image_approval --catalog-id TJD-TEE-001``.
Use ``--count`` to authorize one through four independent candidate calls; the
default is two. Set ``WORKSPACE_SRC`` when the Workspace source is not at its
standard ``F:\\⊕Workspace\\src`` location.
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
_WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_ROOT", r"F:\⊕Workspace"))
_FEATURE_WORKSPACE_SRC = (
    _WORKSPACE_ROOT
    / ".worktrees"
    / "FR-20260927-tee-image-generation-approval"
    / "workspace"
    / "src"
)
_PROMPT_REVISION = "tee-artwork-prompt-v1"
_MAX_BATCH_SIZE = 4


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


def _write_catalog(path: Path, catalog: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary_path.write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


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
    ) -> None:
        self.catalog_path = Path(catalog_path)
        self.output_root = Path(output_root)
        self.cascade = cascade if cascade is not None else _workspace_cascade(workspace_src)

    def generate_batch(
        self,
        catalog_id: str,
        *,
        count: int = 2,
        decide: Decision | None = None,
    ) -> TeeImageBatchResult:
        """Generate an authorized batch and require a decision for each successful image."""
        if not re.fullmatch(r"TJD-TEE-\d{3}", catalog_id):
            raise ValueError("catalog ID must use the TJD-TEE-NNN format")
        if type(count) is not int or not 1 <= count <= _MAX_BATCH_SIZE:
            raise ValueError("candidate count must be between 1 and 4")

        catalog = _read_catalog(self.catalog_path)
        entry = _find_entry(catalog, catalog_id)
        concept_revision = int(entry.setdefault("concept_revision", 1))
        approval_revision = entry.get("concept_approval_revision")
        has_approved_images = (
            entry.get("exact_image_approval_status") == "exact_image_approved"
            or _has_approved_images(self.output_root, catalog_id)
        )
        if approval_revision is None and entry.get("concept_approval_status") == "concept_approved":
            entry["concept_approval_revision"] = concept_revision
            _write_catalog(self.catalog_path, catalog)
        elif approval_revision is not None and int(approval_revision) != concept_revision:
            entry["concept_approval_status"] = "concept_pending"
            if not has_approved_images:
                entry["exact_image_approval_status"] = "not_started"
            _write_catalog(self.catalog_path, catalog)
            raise ValueError("concept revision changed; curation and explicit reapproval are required")
        if entry.get("concept_approval_status") != "concept_approved":
            raise ValueError("tee concept must be concept_approved before image generation")

        catalog_revision = f"{catalog.get('version', 'unversioned')}:{concept_revision}"
        exact_prompt = _compose_prompt(entry, catalog_revision)
        if has_approved_images:
            entry["exact_image_approval_status"] = "exact_image_approved"
            _write_catalog(self.catalog_path, catalog)
        else:
            entry["exact_image_approval_status"] = "exact_image_pending"
            _write_catalog(self.catalog_path, catalog)

        run_id = uuid.uuid4().hex
        run_dir = self.output_root / catalog_id / run_id
        approved: list[TeeImageCandidate] = []
        rejected_count = 0
        failures: list[dict[str, object]] = []
        decision_callback = decide if decide is not None else _interactive_decision

        for candidate_number in range(1, count + 1):
            candidate_id = f"{run_id[:8]}-{candidate_number:02d}"
            with tempfile.TemporaryDirectory(prefix="tee-image-candidate-") as temporary_dir:
                temporary_root = Path(temporary_dir)
                try:
                    result = self.cascade.generate(exact_prompt, output_dir=temporary_root)
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
                    exact_prompt=exact_prompt,
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
                    "exact_prompt": exact_prompt,
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
    parser.add_argument("--catalog-id", required=True)
    parser.add_argument("--count", type=int, default=2)
    args = parser.parse_args(argv)
    result = TeeImageApprovalFlow().generate_batch(args.catalog_id, count=args.count)
    print(
        f"Run {result.run_id}: {len(result.approved)} approved, "
        f"{result.rejected_count} rejected, {len(result.failures)} provider failures"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())