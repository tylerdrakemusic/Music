"""Validator for generated .hlx presets (FR-20260705-guitar-tech-persona-agent).

Checks, in order:
  1. JSON validity (when reading from a file)
  2. Top-level skeleton conformance (required keys, schema, version, dsp0 present)
  3. @model id existence (every block's model must resolve to a real catalog
     entry -- including routing primitives like HD2_AppDSPFlowJoin, found in
     io.models)
  4. Declared-param range compliance (only params the model itself declares
     in its own catalog params[] are range-checked; structural keys like
     @type/@path/@position/@cab/@no_snapshot_bypass are skipped)
  5. Device compatibility (best-effort; flags a model that declares explicit
     device support excluding the target device)

Supports validating a single already-parsed dict, a single file on disk, or
a batch of files.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from guitar_tech.hlx_catalog import (
    HX_STOMP_DEVICE_ID,
    find_model_category,
    get_model,
    model_supports_device,
)

REQUIRED_TOP_LEVEL_KEYS = ("data", "meta", "schema", "version")


@dataclass(frozen=True)
class ValidationIssue:
    location: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    source: str
    ok: bool
    issues: list[ValidationIssue] = field(default_factory=list)


def validate_preset_dict(preset: dict[str, Any], source: str = "<preset>") -> ValidationResult:
    issues: list[ValidationIssue] = []

    for key in REQUIRED_TOP_LEVEL_KEYS:
        if key not in preset:
            issues.append(ValidationIssue(key, f"missing required top-level key {key!r}"))
    if issues:
        return ValidationResult(source, False, issues)

    if preset.get("schema") != "L6Preset":
        issues.append(ValidationIssue("schema", f"expected schema 'L6Preset', got {preset.get('schema')!r}"))
    if preset.get("version") != 6:
        issues.append(ValidationIssue("version", f"expected version 6, got {preset.get('version')!r}"))

    data = preset.get("data", {})
    if "device" not in data:
        issues.append(ValidationIssue("data.device", "missing data.device"))

    dsp0 = data.get("tone", {}).get("dsp0")
    if not isinstance(dsp0, dict):
        issues.append(ValidationIssue("data.tone.dsp0", "missing or invalid data.tone.dsp0"))
        return ValidationResult(source, False, issues)

    for block_key, block in dsp0.items():
        if not isinstance(block, dict):
            continue
        model_id = block.get("@model")
        if model_id is None:
            continue
        location_prefix = f"data.tone.dsp0.{block_key}"

        category = find_model_category(model_id)
        if category is None:
            issues.append(ValidationIssue(location_prefix, f"unknown @model id {model_id!r}"))
            continue

        model = get_model(category, model_id)
        if not model_supports_device(model, HX_STOMP_DEVICE_ID):
            issues.append(
                ValidationIssue(
                    location_prefix,
                    f"model {model_id!r} does not declare support for device {HX_STOMP_DEVICE_ID}",
                )
            )

        declared = {p["symbolicID"]: p for p in model.get("params", [])}
        for param_name, value in block.items():
            spec = declared.get(param_name)
            if spec is None:
                continue  # structural key not declared by this model -- skip range check
            lo, hi = spec.get("min"), spec.get("max")
            if lo is None or hi is None or not isinstance(value, (int, float, bool)):
                continue
            if not (lo <= value <= hi):
                issues.append(
                    ValidationIssue(
                        f"{location_prefix}.{param_name}",
                        f"value {value} out of range [{lo}, {hi}]",
                    )
                )

    return ValidationResult(source, len(issues) == 0, issues)


def validate_preset_file(path: Path | str) -> ValidationResult:
    path = Path(path)
    try:
        with open(path, encoding="utf-8") as f:
            preset = json.load(f)
    except json.JSONDecodeError as exc:
        return ValidationResult(str(path), False, [ValidationIssue("<root>", f"invalid JSON: {exc}")])
    return validate_preset_dict(preset, source=str(path))


def validate_batch(paths: list[Path | str]) -> list[ValidationResult]:
    return [validate_preset_file(p) for p in paths]
