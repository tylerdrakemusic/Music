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
from collections import Counter
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

from PIL import Image

from src.merch.tee_prompt_catalog import TeePromptCatalog
from src.utils import init_db
from tools.color_transparency import delta_e_ciede2000, rgb_to_lab


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_OUTPUT_ROOT = _PROJECT_ROOT / "output" / "images" / "tee-merch"
_PENDING_ROOT = Path(tempfile.gettempdir()) / "tee-image-approval-sessions"
_WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_ROOT", r"F:\⊕Workspace"))
_PROMPT_REVISION = "tee-artwork-prompt-v3"
_MAX_BATCH_SIZE = 4
_CANDIDATE_ART_DIRECTIONS = (
    "Vintage screen-print artwork: center the main subject in a "
    "balanced, emblematic composition with a sparse background.",
    "Abstract artwork: use a wide environmental composition, placing the "
    "main subject off-center and giving the setting more space.",
    "Line-work artwork: use an intimate close crop on the concept's key "
    "subjects, reducing secondary setting details.",
    "Woodcut-inspired artwork: use a dynamic diagonal composition with "
    "the main subject crossing the frame and bold, simplified background shapes.",
)
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
_DIRECTORY_MTIME_SENTINEL_NS = 4_000_000_000_000_000_000


def _matches_image_signature(suffix: str, content: bytes) -> bool:
    if suffix == ".png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix in {".jpg", ".jpeg"}:
        return content.startswith(b"\xff\xd8\xff")
    if suffix == ".webp":
        return len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP"
    return False


def _is_reparse_point(path: Path) -> bool:
    try:
        path_stat = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(path_stat.st_mode) or bool(
        getattr(path_stat, "st_file_attributes", 0) & 0x400
    )


def _stat_fingerprint(path_stat: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        path_stat.st_dev,
        path_stat.st_ino,
        path_stat.st_size,
        path_stat.st_mtime_ns,
        path_stat.st_ctime_ns,
    )


def _pin_directory_mtime_for_mutation_detection(path: Path) -> None:
    directory_stat = path.stat()
    # Future mtime makes directory-entry changes visible on coarse-resolution filesystems.
    os.utime(
        path,
        ns=(
            directory_stat.st_atime_ns,
            max(directory_stat.st_mtime_ns, _DIRECTORY_MTIME_SENTINEL_NS),
        ),
    )
def _write_json_exclusive(path: Path, data: object) -> None:
    with path.open("x", encoding="utf-8") as output_file:
        json.dump(data, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")


def _live_connection() -> sqlite3.Connection:
    init_db.use_worktree_aware_db_path(_PROJECT_ROOT)
    return init_db.get_connection()


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


def _find_entry(catalog: dict[str, object], catalog_id: str) -> dict[str, object]:
    entries = catalog["prompts"]
    for entry in entries:
        if isinstance(entry, dict) and entry.get("id") == catalog_id:
            return entry
    raise KeyError(f"tee concept not found: {catalog_id}")


def _has_approved_images(
    output_root: Path,
    catalog_id: str,
    image_prompt_revision: int,
    concept_revision: int,
    exact_prompt: str,
    *,
    allow_legacy_sidecars: bool,
) -> bool:
    catalog_dir = output_root / catalog_id
    if catalog_dir.is_symlink() or not catalog_dir.is_dir():
        return False

    resolved_catalog_dir = catalog_dir.resolve()
    for run_dir in catalog_dir.iterdir():
        if (
            run_dir.is_symlink()
            or not run_dir.is_dir()
            or not re.fullmatch(r"[0-9a-f]{32}", run_dir.name)
            or run_dir.resolve().parent != resolved_catalog_dir
        ):
            continue
        for sidecar_path in run_dir.glob("*.json"):
            match = re.fullmatch(r"([0-9a-f]{8})-([0-9]{2})\.json", sidecar_path.name)
            if (
                match is None
                or sidecar_path.is_symlink()
                or sidecar_path.resolve().parent != run_dir.resolve()
                or match.group(1) != run_dir.name[:8]
            ):
                continue
            candidate_number = int(match.group(2))
            if not 1 <= candidate_number <= _MAX_BATCH_SIZE:
                continue
            try:
                sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(sidecar, dict):
                continue
            is_legacy_sidecar = (
                allow_legacy_sidecars
                and "image_prompt_revision" not in sidecar
                and isinstance(sidecar.get("catalog_revision"), str)
                and sidecar.get("concept_revision") == concept_revision
            )
            if any(
                (
                    sidecar.get("candidate_id") != sidecar_path.stem,
                    sidecar.get("catalog_id") != catalog_id,
                    sidecar.get("approval") != "approved",
                    sidecar.get("image_prompt_revision") != image_prompt_revision
                    and not is_legacy_sidecar,
                    sidecar.get("prompt_revision") != _PROMPT_REVISION,
                )
            ):
                continue
            if sidecar.get("concept_revision") != concept_revision:
                continue
            expected_prompt = _compose_candidate_prompt(exact_prompt, candidate_number)
            if sidecar.get("exact_prompt") != expected_prompt and not (
                is_legacy_sidecar
                and _legacy_prompt_matches(sidecar.get("exact_prompt"), expected_prompt)
            ):
                continue
            image_paths = [
                run_dir / f"{sidecar_path.stem}{suffix}"
                for suffix in _IMAGE_SUFFIXES
                if (run_dir / f"{sidecar_path.stem}{suffix}").is_file()
            ]
            if len(image_paths) != 1 or image_paths[0].is_symlink():
                continue
            image_path = image_paths[0]
            if image_path.resolve().parent != run_dir.resolve():
                continue
            if sidecar.get("content_sha256") != hashlib.sha256(image_path.read_bytes()).hexdigest():
                continue
            return True
    return False


def _compose_prompt(entry: dict[str, object], image_prompt_revision: int) -> str:
    palette = entry.get("palette", [])
    palette_text = ", ".join(str(color) for color in palette) if isinstance(palette, list) else str(palette)
    return "\n".join(
        (
            f"Catalog ID: {entry['id']}",
            f"Image prompt revision: {image_prompt_revision}",
            f"Prompt revision: {_PROMPT_REVISION}",
            f"Title: {entry['title']}",
            f"Concept: {entry['concept']}",
            f"Palette: {palette_text}",
            f"Print notes: {entry['print_notes']}",
            "Create the selected concept itself as standalone 2D design artwork. Do not depict clothing or apparel, wearers, garments, or garment/product mockups. Do not use clothing or apparel as the background. Require opaque artwork; do not use transparent rendering.",
        )
    )


def _compose_candidate_prompt(exact_prompt: str, candidate_number: int) -> str:
    direction = _CANDIDATE_ART_DIRECTIONS[candidate_number - 1]
    polarity = (
        "Use a dark blank and a lighter key edge."
        if candidate_number % 2 == 1
        else "Use a light blank and a darker key edge."
    )
    edge_constraints = (
        "Reserve the key shade for the border, and make it touch at least one "
        "point on the image perimeter. The frame may be irregular or partial "
        "and does not need to span every side."
    )
    return f"{direction}\n{polarity} {edge_constraints}\n{exact_prompt}"


def _hex_color(color: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*color)


def _sample_perimeter_key(source_path: Path) -> dict[str, object]:
    with Image.open(source_path) as image:
        if image.format != "PNG":
            raise ValueError("transparent derivatives require an approved PNG")
        rgb_image = image.convert("RGB")
        width, height = rgb_image.size
        if width < 2 or height < 2:
            raise ValueError("PNG is too small to sample its perimeter")
        perimeter = (
            [(x, 0) for x in range(width)]
            + [(width - 1, y) for y in range(1, height)]
            + [(x, height - 1) for x in range(width - 2, -1, -1)]
            + [(0, y) for y in range(height - 2, 0, -1)]
        )
        if len(perimeter) < 64:
            raise ValueError("PNG perimeter has fewer than 64 distinct pixels")
        sample_positions = [
            round(index * len(perimeter) / 64) % len(perimeter)
            for index in range(64)
        ]
        sample_colors = [
            tuple(int(channel) for channel in rgb_image.getpixel(perimeter[position]))
            for position in sample_positions
        ]

    sample_labs = [rgb_to_lab(color) for color in sample_colors]
    clusters: list[list[int]] = []
    representatives: list[int] = []
    sample_cluster_ids: list[int] = []
    for sample_index, sample_lab in enumerate(sample_labs):
        cluster_id = next(
            (
                candidate_id
                for candidate_id, representative_index in enumerate(representatives)
                if delta_e_ciede2000(
                    sample_lab, sample_labs[representative_index]
                ) <= 10
            ),
            None,
        )
        if cluster_id is None:
            cluster_id = len(clusters)
            clusters.append([])
            representatives.append(sample_index)
        clusters[cluster_id].append(sample_index)
        sample_cluster_ids.append(cluster_id)

    cluster_order = sorted(range(len(clusters)), key=lambda item: len(clusters[item]), reverse=True)
    dominant_id = cluster_order[0]
    dominant_count = len(clusters[dominant_id])
    runner_up_count = len(clusters[cluster_order[1]]) if len(cluster_order) > 1 else 0
    dominant_samples = [cluster_id == dominant_id for cluster_id in sample_cluster_ids]
    if all(dominant_samples):
        longest_run = 64
    else:
        current_run = 0
        longest_run = 0
        for is_dominant in dominant_samples * 2:
            current_run = min(current_run + 1, 64) if is_dominant else 0
            longest_run = max(longest_run, current_run)

    selected_rgb = Counter(
        sample_colors[index] for index in clusters[dominant_id]
    ).most_common(1)[0][0]
    evidence: dict[str, object] = {
        "sample_count": 64,
        "sampled_colors": [_hex_color(color) for color in sample_colors],
        "clusters": [
            {
                "representative_color": _hex_color(sample_colors[representatives[index]]),
                "sample_count": len(clusters[index]),
            }
            for index in cluster_order
        ],
        "dominant_count": dominant_count,
        "runner_up_count": runner_up_count,
        "confidence_ratio": (
            round(dominant_count / runner_up_count, 3) if runner_up_count else None
        ),
        "longest_consecutive_dominant_run": longest_run,
        "delta_e00_cluster_threshold": 10,
        "minimum_consecutive_samples": 8,
        "minimum_dominant_multiple": 3,
    }
    if longest_run < 8 or dominant_count < 3 * runner_up_count:
        return {
            "selected_color": None,
            "evidence": evidence,
            "error": "perimeter key color did not meet the confidence rule",
        }
    return {
        "selected_color": _hex_color(selected_rgb),
        "evidence": evidence,
        "error": None,
    }


def _transparency_output_paths(source_path: Path) -> tuple[Path, Path]:
    for suffix_number in range(1, 1000):
        suffix = "" if suffix_number == 1 else f"_{suffix_number}"
        derivative_path = source_path.with_name(
            f"{source_path.stem}_transparent{suffix}.png"
        )
        sidecar_path = source_path.with_name(
            f"{source_path.stem}_transparency{suffix}.json"
        )
        if not any(
            path.exists() or _is_reparse_point(path)
            for path in (derivative_path, sidecar_path)
        ):
            return derivative_path, sidecar_path
    raise FileExistsError("no non-colliding transparent derivative name is available")


def _candidate_polarity(candidate_id: str) -> str:
    try:
        candidate_number = int(candidate_id.rsplit("-", 1)[1])
    except (IndexError, ValueError) as exc:
        raise ValueError("candidate ID does not contain an authorized number") from exc
    if not 1 <= candidate_number <= _MAX_BATCH_SIZE:
        raise ValueError("candidate ID is outside the authorized batch size")
    return (
        "lighter-key-on-dark-blank"
        if candidate_number % 2 == 1
        else "darker-key-on-light-blank"
    )


def _create_transparent_derivative(
    source_path: Path, candidate_id: str
) -> dict[str, object]:
    derivative_path: Path | None = None
    sidecar_path: Path | None = None
    cli_started = False
    sidecar_written = False
    sidecar: dict[str, object] = {
        "candidate_id": candidate_id,
        "status": "failed",
        "selected_color": None,
        "polarity": None,
        "sampling": {},
        "settings": {
            "global_match": True,
            "tolerance": 10,
            "smooth_radius": 1,
        },
        "source_sha256": None,
        "output_sha256": None,
    }
    try:
        if _is_reparse_point(source_path):
            raise ValueError("approved image cannot be a reparse point")
        source_bytes = source_path.read_bytes()
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        derivative_path, sidecar_path = _transparency_output_paths(source_path)
        sidecar.update(
            {
                "source_path": str(source_path),
                "output_path": str(derivative_path),
                "sidecar_path": str(sidecar_path),
                "source_sha256": source_sha256,
                "polarity": _candidate_polarity(candidate_id),
            }
        )
        if source_path.suffix.lower() != ".png":
            raise ValueError("transparent derivatives require an approved PNG")

        selection = _sample_perimeter_key(source_path)
        sidecar["sampling"] = selection["evidence"]
        selected_color = selection["selected_color"]
        if not isinstance(selected_color, str):
            raise ValueError(str(selection["error"]))
        sidecar["selected_color"] = selected_color

        cli_started = True
        subprocess.run(
            [
                sys.executable,
                str(_PROJECT_ROOT / "tools" / "color_transparency.py"),
                str(source_path),
                "--color",
                selected_color,
                "--global-match",
                "--tolerance",
                "10",
                "--smooth-radius",
                "1",
                "--output",
                str(derivative_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=_PROJECT_ROOT,
        )
        with Image.open(derivative_path) as derivative:
            if derivative.format != "PNG" or derivative.mode != "RGBA":
                raise OSError("transparency CLI did not produce an RGBA PNG")
        if hashlib.sha256(source_path.read_bytes()).hexdigest() != source_sha256:
            raise OSError("approved opaque source changed during conversion")
        sidecar["output_sha256"] = hashlib.sha256(
            derivative_path.read_bytes()
        ).hexdigest()
        sidecar["status"] = "success"
        _write_json_exclusive(sidecar_path, sidecar)
        sidecar_written = True
        return sidecar
    except Exception as exc:
        if cli_started and derivative_path is not None:
            derivative_path.unlink(missing_ok=True)
        error = str(exc)
        if isinstance(exc, subprocess.CalledProcessError):
            detail = exc.stderr or exc.stdout
            if detail:
                error = f"{error}: {str(detail).strip()}"
        sidecar["status"] = "failed"
        sidecar["error"] = error
        sidecar["output_sha256"] = None
        if sidecar_path is not None:
            try:
                if not sidecar_written:
                    sidecar_path.unlink(missing_ok=True)
                _write_json_exclusive(sidecar_path, sidecar)
            except Exception as sidecar_error:
                sidecar["sidecar_error"] = str(sidecar_error)
        return sidecar


def _legacy_prompt_matches(legacy_prompt: object, current_prompt: str) -> bool:
    if not isinstance(legacy_prompt, str):
        return False

    def without_revision(prompt: str) -> tuple[str, ...] | None:
        lines: list[str] = []
        revision_lines = 0
        for line in prompt.splitlines():
            if line.startswith("Catalog revision: ") or line.startswith(
                "Image prompt revision: "
            ):
                revision_lines += 1
                lines.append("<prompt revision>")
            else:
                lines.append(line)
        return tuple(lines) if revision_lines == 1 else None

    legacy_lines = without_revision(legacy_prompt)
    return legacy_lines is not None and legacy_lines == without_revision(current_prompt)


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
        catalog: TeePromptCatalog,
        output_root: Path = _OUTPUT_ROOT,
        *,
        cascade: ImageCascade | None = None,
        workspace_src: Path | None = None,
        pending_root: Path | None = None,
    ) -> None:
        self.catalog = catalog
        self.output_root = Path(output_root).absolute()
        self.pending_root = Path(pending_root) if pending_root is not None else _PENDING_ROOT
        self.cascade = cascade if cascade is not None else _workspace_cascade(workspace_src)

    def _output_path(self, *parts: str) -> Path:
        root = self.output_root
        for ancestor in (root, *root.parents):
            if _is_reparse_point(ancestor):
                raise ValueError("output path may not contain symlinked or reparse-point parents")

        try:
            resolved_root = root.resolve(strict=False)
            candidate = root
            for part in parts:
                candidate = candidate / part
                if _is_reparse_point(candidate):
                    raise ValueError("output path may not contain symlinks or reparse points")
                if not candidate.resolve(strict=False).is_relative_to(resolved_root):
                    raise ValueError("output path escapes the configured output root")
        except OSError as exc:
            raise ValueError("output path could not be safely resolved") from exc
        return candidate

    def _prepare_generation(
        self, catalog_id: str
    ) -> tuple[dict[str, object], dict[str, object], int, int, str, str, bool]:
        self._output_path()
        if not re.fullmatch(r"TJD-TEE-\d{3}", catalog_id):
            raise ValueError("catalog ID must use the TJD-TEE-NNN format")

        catalog = self.catalog.read_catalog()
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

        if approval_revision != concept_revision:
            raise ValueError("concept revision changed; curation and explicit reapproval are required")

        image_prompt_revision = int(entry["image_prompt_revision"])
        catalog_version = str(entry["catalog_version"])
        exact_prompt = _compose_prompt(entry, image_prompt_revision)
        has_approved_images = _has_approved_images(
            self.output_root,
            catalog_id,
            image_prompt_revision,
            concept_revision,
            exact_prompt,
            allow_legacy_sidecars=(
                entry.get("exact_image_approval_status") == "exact_image_approved"
            ),
        )
        entry = self.catalog.reconcile_exact_image_approval(
            catalog_id,
            expected_image_prompt_revision=image_prompt_revision,
            expected_concept_revision=concept_revision,
            has_matching_approved_sidecar=has_approved_images,
        )
        entry["exact_image_approval_status"] = (
            "exact_image_approved" if has_approved_images else "exact_image_pending"
        )
        return (
            catalog,
            entry,
            concept_revision,
            image_prompt_revision,
            catalog_version,
            exact_prompt,
            has_approved_images,
        )

    def _chat_session_directory(self, session_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", session_id):
            raise ValueError("chat approval session ID is invalid")
        root = self.pending_root.resolve()
        session_dir = root / session_id
        if _is_reparse_point(session_dir) or session_dir.resolve().parent != root:
            raise ValueError("chat approval session path is invalid")
        return session_dir

    @staticmethod
    def _write_chat_session(session_dir: Path, state: dict[str, object]) -> None:
        _write_json(session_dir / "session.json", state)

    @staticmethod
    def _presentation_record_path(session_dir: Path) -> Path:
        return session_dir.parent / f".{session_dir.name}.presentation.json"

    def start_chat_batch(self, catalog_id: str, *, count: int = 2) -> dict[str, object]:
        if type(count) is not int or not 1 <= count <= _MAX_BATCH_SIZE:
            raise ValueError("candidate count must be between 1 and 4")

        (
            catalog,
            _,
            concept_revision,
            image_prompt_revision,
            catalog_version,
            exact_prompt,
            _,
        ) = self._prepare_generation(catalog_id)
        run_id = uuid.uuid4().hex
        session_id = uuid.uuid4().hex
        session_dir = self._chat_session_directory(session_id)
        session_dir.mkdir(parents=True, exist_ok=False)
        state: dict[str, object] = {
            "session_id": session_id,
            "catalog_id": catalog_id,
            "concept_revision": concept_revision,
            "image_prompt_revision": image_prompt_revision,
            "catalog_version": catalog_version,
            "prompt_revision": _PROMPT_REVISION,
            "exact_prompt": exact_prompt,
            "run_id": run_id,
            "total_count": count,
            "next_candidate_number": 1,
            "generated_count": 0,
            "approved_count": 0,
            "rejected_count": 0,
            "failures": [],
            "transparency_failures": [],
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
                    or _is_reparse_point(source_path)
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
                try:
                    with source_path.open("rb") as source_file:
                        staged_bytes = source_file.read()
                    if not _matches_image_signature(suffix, staged_bytes):
                        raise ValueError("image file content does not match its extension")
                    with staged_path.open("xb") as staged_file:
                        staged_file.write(staged_bytes)
                except (OSError, ValueError) as exc:
                    failures.append(
                        {
                            "candidate_id": candidate_id,
                            "error": str(exc),
                            "diagnostics": [
                                _diagnostic_dict(item)
                                for item in getattr(result, "diagnostics", ())
                            ],
                        }
                    )
                    self._write_chat_session(session_dir, state)
                    continue
                state["generated_count"] = int(state["generated_count"]) + 1
                state["pending_candidate"] = {
                    "candidate_id": candidate_id,
                    "candidate_number": candidate_number,
                    "image_name": image_name,
                    "provider": str(result.provider),
                    "model": str(result.model),
                    "exact_prompt": candidate_prompt,
                    "content_sha256": hashlib.sha256(staged_bytes).hexdigest(),
                    "file_fingerprint": list(_stat_fingerprint(staged_path.stat())),
                    "provider_diagnostics": [
                        _diagnostic_dict(item)
                        for item in getattr(result, "diagnostics", ())
                    ],
                }
                self._write_chat_session(session_dir, state)
                _pin_directory_mtime_for_mutation_detection(session_dir)
                _write_json_exclusive(
                    self._presentation_record_path(session_dir),
                    {
                        "candidate_id": candidate_id,
                        "directory_fingerprint": list(
                            _stat_fingerprint(session_dir.stat())
                        ),
                    },
                )
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
            run_dir = self._output_path(catalog_id, run_id)
            run_dir.mkdir(parents=True, exist_ok=True)
            run_dir = self._output_path(catalog_id, run_id)
            _write_json_exclusive(
                self._output_path(catalog_id, run_id, "provider-failures.json"),
                failures,
            )
        transparency_failures = state.get("transparency_failures", [])
        assert isinstance(transparency_failures, list)
        if transparency_failures:
            run_dir = self._output_path(catalog_id, run_id)
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_json_exclusive(
                self._output_path(catalog_id, run_id, "transparency-failures.json"),
                transparency_failures,
            )
        summary = {
            "status": "completed",
            "run_id": run_id,
            "generated": int(state["generated_count"]),
            "approved": int(state["approved_count"]),
            "rejected": int(state["rejected_count"]),
            "failed": len(failures) + len(transparency_failures),
            "failures": failures,
            "transparency_failures": transparency_failures,
        }
        self._presentation_record_path(session_dir).unlink(missing_ok=True)
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
        if (
            _is_reparse_point(image_path)
            or image_path.resolve().parent != session_dir.resolve()
            or not image_path.is_file()
        ):
            raise ValueError("pending candidate image is unavailable")
        return image_path

    @staticmethod
    def _read_verified_pending_candidate(
        pending_path: Path, session_dir: Path, pending: dict[str, object]
    ) -> bytes:
        try:
            content = pending_path.read_bytes()
            current_fingerprint = _stat_fingerprint(pending_path.stat())
            directory_fingerprint = _stat_fingerprint(session_dir.stat())
            presentation_record = json.loads(
                TeeImageApprovalFlow._presentation_record_path(session_dir).read_text(
                    encoding="utf-8"
                )
            )
        except OSError as exc:
            raise ValueError("pending candidate changed after presentation") from exc
        except json.JSONDecodeError as exc:
            raise ValueError("pending candidate changed after presentation") from exc
        if (
            not isinstance(presentation_record, dict)
            or presentation_record.get("candidate_id") != pending.get("candidate_id")
            or presentation_record.get("directory_fingerprint")
            != list(directory_fingerprint)
            or pending.get("content_sha256") != hashlib.sha256(content).hexdigest()
            or pending.get("file_fingerprint") != list(current_fingerprint)
        ):
            raise ValueError("pending candidate changed after presentation")
        return content

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
        candidate_bytes = self._read_verified_pending_candidate(
            pending_path, session_dir, pending
        )
        transparency_result: dict[str, object] | None = None

        if decision == "y":
            entry = self.catalog.read_prompt(str(state["catalog_id"]))
            try:
                current_revision = int(entry["concept_revision"])
                approval_revision = int(entry["concept_approval_revision"])
            except (KeyError, TypeError, ValueError) as exc:
                pending_path.unlink(missing_ok=True)
                self._presentation_record_path(session_dir).unlink(missing_ok=True)
                shutil.rmtree(session_dir)
                raise ValueError("concept approval changed while image was pending") from exc
            if (
                entry.get("concept_approval_status") != "concept_approved"
                or current_revision != int(state["concept_revision"])
                or approval_revision != current_revision
                or int(entry["image_prompt_revision"])
                != int(state["image_prompt_revision"])
                or state.get("prompt_revision") != _PROMPT_REVISION
            ):
                pending_path.unlink(missing_ok=True)
                self._presentation_record_path(session_dir).unlink(missing_ok=True)
                shutil.rmtree(session_dir)
                raise ValueError("concept or prompt revision changed while image was pending")

            catalog_id = str(state["catalog_id"])
            run_id = str(state["run_id"])
            run_dir = self._output_path(catalog_id, run_id)
            run_dir.mkdir(parents=True, exist_ok=True)
            run_dir = self._output_path(catalog_id, run_id)
            approved_path = self._output_path(
                catalog_id, run_id, f"{candidate_id}{pending_path.suffix}"
            )
            sidecar_path = self._output_path(catalog_id, run_id, f"{candidate_id}.json")
            if approved_path.exists() or sidecar_path.exists():
                raise FileExistsError("approved candidate output already exists")
            sidecar = {
                "candidate_id": candidate_id,
                "catalog_id": state["catalog_id"],
                "concept_revision": current_revision,
                "provider": pending["provider"],
                "model": pending["model"],
                "exact_prompt": pending["exact_prompt"],
                "image_prompt_revision": int(state["image_prompt_revision"]),
                "catalog_version": state["catalog_version"],
                "prompt_revision": _PROMPT_REVISION,
                "content_sha256": pending["content_sha256"],
                "approval": "approved",
                "approved_at": datetime.now(timezone.utc).isoformat(),
                "provider_diagnostics": pending["provider_diagnostics"],
            }
            approved_created = False
            sidecar_created = False
            try:
                with approved_path.open("xb") as approved_file:
                    approved_created = True
                    approved_file.write(candidate_bytes)
                with sidecar_path.open("x", encoding="utf-8") as sidecar_file:
                    sidecar_created = True
                    json.dump(sidecar, sidecar_file, ensure_ascii=False, indent=2)
                    sidecar_file.write("\n")
                self.catalog.approve_exact_image(
                    catalog_id,
                    expected_image_prompt_revision=int(state["image_prompt_revision"]),
                    expected_concept_revision=current_revision,
                    approved_by_tyler=True,
                )
            except Exception:
                if approved_created:
                    approved_path.unlink(missing_ok=True)
                if sidecar_created:
                    sidecar_path.unlink(missing_ok=True)
                raise
            state["approved_count"] = int(state["approved_count"]) + 1
            transparency_result = _create_transparent_derivative(
                approved_path, candidate_id
            )
            if transparency_result["status"] == "failed":
                transparency_failures = state["transparency_failures"]
                assert isinstance(transparency_failures, list)
                transparency_failures.append(
                    {
                        "candidate_id": candidate_id,
                        "error": transparency_result.get("error"),
                        "sidecar_path": transparency_result.get("sidecar_path"),
                    }
                )
        else:
            state["rejected_count"] = int(state["rejected_count"]) + 1

        pending_path.unlink(missing_ok=True)
        self._presentation_record_path(session_dir).unlink(missing_ok=True)
        state["pending_candidate"] = None
        self._write_chat_session(session_dir, state)
        response = self._stage_next_chat_candidate(session_dir, state)
        if transparency_result is not None:
            response["transparency"] = transparency_result
        return response

    def cancel_chat_batch(self, session_id: str) -> dict[str, object]:
        session_dir, state = self._load_chat_session(session_id)
        pending = state.get("pending_candidate")
        if isinstance(pending, dict):
            self._pending_candidate_path(session_dir, pending).unlink(missing_ok=True)
        self._presentation_record_path(session_dir).unlink(missing_ok=True)
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

        (
            catalog,
            entry,
            concept_revision,
            image_prompt_revision,
            catalog_version,
            exact_prompt,
            has_approved_images,
        ) = self._prepare_generation(catalog_id)

        run_id = uuid.uuid4().hex
        run_dir = self._output_path(catalog_id, run_id)
        approved: list[TeeImageCandidate] = []
        rejected_count = 0
        failures: list[dict[str, object]] = []
        transparency_failures: list[dict[str, object]] = []
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
                source_bytes: bytes | None = None
                source_identity: os.stat_result | None = None
                source_parent_fingerprint: tuple[int, int, int, int, int] | None = None
                content_mismatch = False
                try:
                    if (
                        source_path.is_file()
                        and source_path.suffix.lower() in _IMAGE_SUFFIXES
                        and source_path.resolve(strict=True).is_relative_to(
                            temporary_root.resolve()
                        )
                    ):
                        with source_path.open("rb") as source_file:
                            opened_stat = os.fstat(source_file.fileno())
                            resolved_path = source_path.resolve(strict=True)
                            if (
                                resolved_path.is_relative_to(temporary_root.resolve())
                                and os.path.samestat(opened_stat, resolved_path.stat())
                            ):
                                content = source_file.read()
                                if _matches_image_signature(
                                    source_path.suffix.lower(), content
                                ):
                                    source_bytes = content
                                    source_identity = opened_stat
                                    _pin_directory_mtime_for_mutation_detection(
                                        source_path.parent
                                    )
                                    source_parent_fingerprint = _stat_fingerprint(
                                        source_path.parent.stat()
                                    )
                                else:
                                    content_mismatch = True
                except (OSError, RuntimeError):
                    pass

                if source_identity is None or source_bytes is None:
                    failures.append(
                        {
                            "candidate_id": candidate_id,
                            "error": (
                                "image file content does not match its extension"
                                if content_mismatch
                                else "image cascade returned a missing, unsupported, or out-of-directory image file"
                            ),
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

                try:
                    resolved_path = source_path.resolve(strict=True)
                    current_stat = resolved_path.stat()
                    candidate_path_is_unchanged = (
                        resolved_path.is_relative_to(temporary_root.resolve())
                        and os.path.samestat(source_identity, resolved_path.stat())
                        and source_parent_fingerprint is not None
                        and _stat_fingerprint(source_path.parent.stat())
                        == source_parent_fingerprint
                    )
                    candidate_content_is_unchanged = (
                        candidate_path_is_unchanged
                        and source_identity is not None
                        and _stat_fingerprint(current_stat)
                        == _stat_fingerprint(source_identity)
                        and resolved_path.read_bytes() == source_bytes
                    )
                except (OSError, RuntimeError):
                    candidate_path_is_unchanged = False
                    candidate_content_is_unchanged = False
                if not candidate_path_is_unchanged:
                    failures.append(
                        {
                            "candidate_id": candidate_id,
                            "error": "image candidate changed or escaped the generation directory during approval",
                            "diagnostics": [
                                _diagnostic_dict(item)
                                for item in getattr(result, "diagnostics", ())
                            ],
                        }
                    )
                    continue
                if not candidate_content_is_unchanged:
                    failures.append(
                        {
                            "candidate_id": candidate_id,
                            "error": "image candidate content changed during approval",
                            "diagnostics": [
                                _diagnostic_dict(item)
                                for item in getattr(result, "diagnostics", ())
                            ],
                        }
                    )
                    continue

                run_dir = self._output_path(catalog_id, run_id)
                run_dir.mkdir(parents=True, exist_ok=True)
                run_dir = self._output_path(catalog_id, run_id)
                suffix = source_path.suffix.lower()
                approved_path = self._output_path(
                    catalog_id, run_id, f"{candidate_id}{suffix}"
                )
                sidecar_path = self._output_path(
                    catalog_id, run_id, f"{candidate_id}.json"
                )
                sidecar = {
                    "candidate_id": candidate_id,
                    "catalog_id": catalog_id,
                    "concept_revision": concept_revision,
                    "provider": candidate.provider,
                    "model": candidate.model,
                    "exact_prompt": candidate_prompt,
                    "image_prompt_revision": image_prompt_revision,
                    "catalog_version": catalog_version,
                    "prompt_revision": _PROMPT_REVISION,
                    "content_sha256": hashlib.sha256(source_bytes).hexdigest(),
                    "approval": "approved",
                    "approved_at": datetime.now(timezone.utc).isoformat(),
                    "provider_diagnostics": [
                        _diagnostic_dict(item)
                        for item in getattr(result, "diagnostics", ())
                    ],
                }
                approved_created = False
                sidecar_created = False
                try:
                    with approved_path.open("xb") as approved_file:
                        approved_created = True
                        approved_file.write(source_bytes)
                    approved_content = approved_path.read_bytes()
                    if approved_content != source_bytes:
                        raise OSError("approved image changed while being written")
                    sidecar["content_sha256"] = hashlib.sha256(
                        approved_content
                    ).hexdigest()
                    with sidecar_path.open("x", encoding="utf-8") as sidecar_file:
                        sidecar_created = True
                        json.dump(sidecar, sidecar_file, ensure_ascii=False, indent=2)
                        sidecar_file.write("\n")
                    self.catalog.approve_exact_image(
                        catalog_id,
                        expected_image_prompt_revision=image_prompt_revision,
                        expected_concept_revision=concept_revision,
                        approved_by_tyler=True,
                    )
                except FileExistsError:
                    if approved_created:
                        approved_path.unlink(missing_ok=True)
                    if sidecar_created:
                        sidecar_path.unlink(missing_ok=True)
                    failures.append(
                        {
                            "candidate_id": candidate_id,
                            "error": "approved image or sidecar destination already exists",
                            "diagnostics": [
                                _diagnostic_dict(item)
                                for item in getattr(result, "diagnostics", ())
                            ],
                        }
                    )
                    continue
                except Exception:
                    if approved_created:
                        approved_path.unlink(missing_ok=True)
                    if sidecar_created:
                        sidecar_path.unlink(missing_ok=True)
                    raise
                approved.append(
                    TeeImageCandidate(
                        candidate_id=candidate_id,
                        path=approved_path,
                        provider=candidate.provider,
                        model=candidate.model,
                        exact_prompt=exact_prompt,
                    )
                )
                transparency_result = _create_transparent_derivative(
                    approved_path, candidate_id
                )
                if transparency_result["status"] == "failed":
                    transparency_failures.append(
                        {
                            "candidate_id": candidate_id,
                            "error": transparency_result.get("error"),
                            "sidecar_path": transparency_result.get("sidecar_path"),
                        }
                    )

        if failures:
            run_dir = self._output_path(catalog_id, run_id)
            run_dir.mkdir(parents=True, exist_ok=True)
            run_dir = self._output_path(catalog_id, run_id)
            _write_json_exclusive(
                self._output_path(catalog_id, run_id, "provider-failures.json"),
                failures,
            )
        if transparency_failures:
            run_dir = self._output_path(catalog_id, run_id)
            run_dir.mkdir(parents=True, exist_ok=True)
            _write_json_exclusive(
                self._output_path(
                    catalog_id, run_id, "transparency-failures.json"
                ),
                transparency_failures,
            )

        return TeeImageBatchResult(
            run_id=run_id,
            approved=tuple(approved),
            rejected_count=rejected_count,
            failures=tuple([*failures, *transparency_failures]),
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

    connection = _live_connection()
    try:
        flow = TeeImageApprovalFlow(
            TeePromptCatalog(connection),
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
        failure_count = len(result.failures)
        failure_label = "failure" if failure_count == 1 else "failures"
        print(
            f"Run {result.run_id}: {len(result.approved)} approved, "
            f"{result.rejected_count} rejected, {failure_count} candidate {failure_label}"
        )
        for failure in result.failures:
            print(
                f"{failure.get('candidate_id', 'unknown candidate')}: "
                f"{failure.get('error', 'unspecified failure')}"
            )
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())