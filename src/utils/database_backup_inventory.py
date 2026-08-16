"""Validate the ❤Music database inventory used by the shared backup contract."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


_REQUIRED_ROOT_FIELDS = {
    "schema_version",
    "project",
    "fr",
    "content_boundary",
    "databases",
    "exclusions",
}
_REQUIRED_DATABASE_FIELDS = {
    "id",
    "locator",
    "basename",
    "classification",
    "backup_allowed",
    "encryption",
    "key_env_var",
    "reason",
}
_EXCLUSION_FIELDS = {"pattern", "reason"}
_CLASSIFICATIONS = {
    "canonical",
    "coordination",
    "derived",
    "temporary",
    "legacy",
    "unknown",
    "approval-required",
}
_ENV_VAR_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")
_DATABASE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}


def _validate_database_entry(entry: Any) -> None:
    if not isinstance(entry, dict):
        raise ValueError("each database inventory entry must be an object")
    missing = _REQUIRED_DATABASE_FIELDS - entry.keys()
    unknown = entry.keys() - _REQUIRED_DATABASE_FIELDS
    if missing:
        raise ValueError(f"database inventory entry missing fields: {sorted(missing)}")
    if unknown:
        raise ValueError(f"unknown database inventory fields: {sorted(unknown)}")

    if not isinstance(entry["id"], str) or not _IDENTIFIER_PATTERN.fullmatch(entry["id"]):
        raise ValueError("database inventory id must be a safe identifier")

    locator = entry["locator"]
    if not isinstance(locator, str) or not locator.strip():
        raise ValueError("database inventory locator must be non-empty")
    locator_parts = locator.replace("\\", "/").split("/")
    if (
        Path(locator).is_absolute()
        or any(part in {"", ".", ".."} for part in locator_parts)
        or "\\" in locator
        or ":" in locator
        or any(ord(character) < 32 or ord(character) == 127 for character in locator)
    ):
        raise ValueError("database inventory locator must be relative and redacted")

    basename = entry["basename"]
    if (
        not isinstance(basename, str)
        or not basename.strip()
        or Path(basename).name != basename
        or Path(basename).suffix.lower() not in _DATABASE_SUFFIXES
    ):
        raise ValueError("database inventory basename must be a database filename")

    if entry["classification"] not in _CLASSIFICATIONS:
        raise ValueError("database inventory classification is invalid")
    if not isinstance(entry["backup_allowed"], bool):
        raise ValueError("database inventory backup_allowed must be boolean")
    if entry["classification"] in {"legacy", "approval-required"} and entry["backup_allowed"]:
        raise ValueError("legacy and approval-required database entries are default-denied")
    if entry["encryption"] != "sqlcipher":
        raise ValueError("❤Music database inventory requires SQLCipher")
    if not isinstance(entry["key_env_var"], str) or not _ENV_VAR_PATTERN.fullmatch(entry["key_env_var"]):
        raise ValueError("database inventory key_env_var must be an environment variable name")
    if not isinstance(entry["reason"], str) or not entry["reason"].strip():
        raise ValueError("database inventory reason must be non-empty")


def _validate_exclusion(entry: Any) -> None:
    if not isinstance(entry, dict) or set(entry) != _EXCLUSION_FIELDS:
        raise ValueError("database inventory exclusions must contain pattern and reason")
    if not all(isinstance(entry[field], str) and entry[field].strip() for field in _EXCLUSION_FIELDS):
        raise ValueError("database inventory exclusion fields must be non-empty strings")


def load_database_inventory(path: Path) -> dict[str, Any]:
    """Load and validate redacted Music database policy metadata."""
    with Path(path).open(encoding="utf-8") as handle:
        inventory = json.load(handle)
    if not isinstance(inventory, dict):
        raise ValueError("database inventory root must be an object")
    missing = _REQUIRED_ROOT_FIELDS - inventory.keys()
    unknown = inventory.keys() - _REQUIRED_ROOT_FIELDS
    if missing:
        raise ValueError(f"database inventory missing fields: {sorted(missing)}")
    if unknown:
        raise ValueError(f"unknown database inventory root fields: {sorted(unknown)}")
    if inventory["schema_version"] != 1:
        raise ValueError("unsupported database inventory schema version")
    if inventory["project"] != "music":
        raise ValueError("database inventory project must be music")
    if not isinstance(inventory["fr"], str) or not inventory["fr"].strip():
        raise ValueError("database inventory fr must be non-empty")
    if not isinstance(inventory["content_boundary"], str) or not inventory["content_boundary"].strip():
        raise ValueError("database inventory content_boundary must be non-empty")

    databases = inventory["databases"]
    if not isinstance(databases, list) or not databases:
        raise ValueError("database inventory databases must be a non-empty list")
    exclusions = inventory["exclusions"]
    if not isinstance(exclusions, list):
        raise ValueError("database inventory exclusions must be a list")

    ids: set[str] = set()
    locators: set[str] = set()
    for entry in databases:
        _validate_database_entry(entry)
        if entry["id"] in ids:
            raise ValueError(f"duplicate database inventory id: {entry['id']}")
        if entry["locator"] in locators:
            raise ValueError(f"duplicate database inventory locator: {entry['locator']}")
        ids.add(entry["id"])
        locators.add(entry["locator"])
    for entry in exclusions:
        _validate_exclusion(entry)
    return inventory


def resolve_database_path(project_root: Path, entry: dict[str, Any]) -> Path:
    """Resolve a registered Music database under its canonical project root."""
    _validate_database_entry(entry)
    root = Path(project_root).resolve()
    resolved = (root / "src" / "data" / entry["basename"]).resolve()
    if root not in resolved.parents:
        raise ValueError("database inventory path escaped the project root")
    return resolved


def build_backup_manifest(inventory: dict[str, Any]) -> dict[str, Any]:
    """Project every inventory entry into the generic backup lifecycle contract."""
    databases = []
    for entry in inventory["databases"]:
        databases.append(
            {
                "id": entry["id"],
                "path": entry["locator"],
                "classification": entry["classification"],
                "backup_allowed": entry["backup_allowed"],
                "reason": entry["reason"],
                "discovery": {"project": inventory["project"], "basename": entry["basename"]},
                "encryption": entry["encryption"],
                "key_env": entry["key_env_var"],
            }
        )
    return {
        "schema_version": 1,
        "fr": inventory["fr"],
        "policy_status": "reviewed",
        "purpose": "Project database backup inventory.",
        "content_boundary": inventory["content_boundary"],
        "classifications": sorted(_CLASSIFICATIONS),
        "databases": databases,
        "exclusions": inventory["exclusions"],
        "not_implemented": [],
        "separate_todos": [],
    }