"""Loader for the committed Line 6 HX Edit reference snapshot
(FR-20260705-guitar-tech-persona-agent).

Reads catalog/helix_reference/*.models (JSON arrays of model definitions)
and default_preset_hxs.hlx (the empty routing-only preset skeleton), both
copied verbatim from a local HX Edit install (see
catalog/helix_reference/README.md for provenance).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REFERENCE_DIR = Path(__file__).resolve().parents[2] / "catalog" / "helix_reference"

HX_STOMP_DEVICE_ID = 2162694

_category_cache: dict[str, list[dict[str, Any]]] = {}
_skeleton_cache: dict[str, Any] | None = None


def load_category(category: str) -> list[dict[str, Any]]:
    """Load and cache a *.models category file as a list of model dicts."""
    if category in _category_cache:
        return _category_cache[category]
    path = REFERENCE_DIR / f"{category}.models"
    if not path.is_file():
        raise FileNotFoundError(f"No such HX Edit model category: {category!r} ({path})")
    with open(path, encoding="utf-8") as f:
        models = json.load(f)
    _category_cache[category] = models
    return models


def get_model(category: str, symbolic_id: str) -> dict[str, Any]:
    """Find a model by symbolicID within a category. Raises KeyError if absent."""
    for model in load_category(category):
        if model.get("symbolicID") == symbolic_id:
            return model
    raise KeyError(f"{symbolic_id!r} not found in category {category!r}")


def default_params(model: dict[str, Any]) -> dict[str, Any]:
    """Build a {paramSymbolicID: default_value} dict from a model's declared params."""
    return {p["symbolicID"]: p["default"] for p in model.get("params", [])}


def model_supports_device(model: dict[str, Any], device_id: int = HX_STOMP_DEVICE_ID) -> bool:
    """Return True if the model is usable on the given device.

    Models with no "devices" field are universally compatible. Models with a
    "devices" field are restricted to the listed device ids (firmware
    version strings, if present, are not checked -- best-effort only).
    """
    devices = model.get("devices")
    if not devices:
        return True
    return any(d.get("id") == device_id for d in devices)


def load_skeleton() -> dict[str, Any]:
    """Load and cache the empty routing-only preset skeleton."""
    global _skeleton_cache
    if _skeleton_cache is None:
        path = REFERENCE_DIR / "default_preset_hxs.hlx"
        with open(path, encoding="utf-8") as f:
            _skeleton_cache = json.load(f)
    return _skeleton_cache


def list_categories() -> list[str]:
    """List all *.models category names available in the reference snapshot."""
    return sorted(p.stem for p in REFERENCE_DIR.glob("*.models"))


def find_model_category(symbolic_id: str) -> str | None:
    """Search every known category for a model, returning its category name.

    Returns None if the symbolic id is not found in any category. Used by
    the validator to confirm a block's `@model` id -- including routing
    primitives such as HD2_AppDSPFlowJoin, which live in io.models -- refers
    to a real, known model rather than a typo or hallucinated id.
    """
    for category in list_categories():
        for model in load_category(category):
            if model.get("symbolicID") == symbolic_id:
                return category
    return None
