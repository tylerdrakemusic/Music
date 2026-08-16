from __future__ import annotations

import json
from pathlib import Path

import pytest

from utils.database_backup_inventory import (
    build_backup_manifest,
    load_database_inventory,
    resolve_database_path,
)


INVENTORY_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "config"
    / "database_backup_inventory.json"
)


def _inventory(databases: list[dict[str, object]], exclusions: list[dict[str, str]] | None = None) -> dict[str, object]:
    return {
        "schema_version": 1,
        "project": "music",
        "fr": "FR-20260816-workspace-local-database-backup",
        "content_boundary": "Redacted database policy metadata only; database contents and credentials are never included.",
        "databases": databases,
        "exclusions": exclusions or [],
    }


def _database(**overrides: object) -> dict[str, object]:
    database: dict[str, object] = {
        "id": "music-heartmusic",
        "locator": "music/heartmusic-store",
        "basename": "heartmusic.db",
        "classification": "canonical",
        "backup_allowed": True,
        "encryption": "sqlcipher",
        "key_env_var": "HEARTMUSIC_DB_KEY",
        "reason": "Approved canonical music store.",
    }
    database.update(overrides)
    return database


def test_load_database_inventory_exposes_only_redacted_encrypted_metadata(
    tmp_path: Path,
) -> None:
    inventory_path = tmp_path / "database_backup_inventory.json"
    inventory_path.write_text(
        json.dumps(_inventory([_database()])), encoding="utf-8"
    )

    inventory = load_database_inventory(inventory_path)

    assert inventory["project"] == "music"
    assert inventory["databases"] == [_database()]
    serialized = json.dumps(inventory).lower()
    assert "src/data" not in serialized
    assert "key_value" not in serialized
    assert "secret" not in serialized


def test_inventory_entries_are_configuration_driven(tmp_path: Path) -> None:
    future_database = _database(
        id="music-approved-future-store",
        locator="music/future-store",
        basename="future_store.sqlite3",
        classification="canonical",
        backup_allowed=True,
        key_env_var="FUTURE_STORE_DB_KEY",
    )
    inventory_path = tmp_path / "database_backup_inventory.json"
    inventory_path.write_text(
        json.dumps(_inventory([_database(), future_database])), encoding="utf-8"
    )

    inventory = load_database_inventory(inventory_path)

    assert [entry["id"] for entry in inventory["databases"]] == [
        "music-heartmusic",
        "music-approved-future-store",
    ]


def test_inventory_projects_all_entries_into_generic_backup_manifest(tmp_path: Path) -> None:
    future_database = _database(
        id="music-approved-future-store",
        locator="music/future-store",
        basename="future_store.sqlite3",
    )
    inventory_path = tmp_path / "database_backup_inventory.json"
    inventory_path.write_text(json.dumps(_inventory([future_database])), encoding="utf-8")

    manifest = build_backup_manifest(load_database_inventory(inventory_path))

    assert manifest["databases"] == [
        {
            "id": "music-approved-future-store",
            "path": "music/future-store",
            "classification": "canonical",
            "backup_allowed": True,
            "reason": "Approved canonical music store.",
            "discovery": {"project": "music", "basename": "future_store.sqlite3"},
            "encryption": "sqlcipher",
            "key_env": "HEARTMUSIC_DB_KEY",
        }
    ]


def test_committed_inventory_registers_canonical_encrypted_store() -> None:
    inventory = load_database_inventory(INVENTORY_PATH)

    assert inventory["databases"] == [_database()]


def test_committed_inventory_excludes_legacy_and_plaintext_backup_artifacts() -> None:
    inventory = load_database_inventory(INVENTORY_PATH)

    assert inventory["exclusions"] == [
        {
            "pattern": "src/data/backups/**",
            "reason": "Legacy plaintext backup artifacts are excluded from future backup discovery.",
        },
        {
            "pattern": "data/legacy_heartmusic.db",
            "reason": "Legacy database store is excluded from future backup discovery.",
        },
    ]


def test_canonical_music_database_resolves_under_active_project_root(tmp_path: Path) -> None:
    inventory = load_database_inventory(INVENTORY_PATH)
    project_root = tmp_path / "music-project"
    canonical = project_root / "src" / "data" / "heartmusic.db"
    canonical.parent.mkdir(parents=True)
    canonical.touch()

    resolved = resolve_database_path(project_root, inventory["databases"][0])

    assert resolved == canonical.resolve()


def test_committed_inventory_keeps_locator_redacted() -> None:
    inventory = load_database_inventory(INVENTORY_PATH)

    assert inventory["databases"][0]["locator"] == "music/heartmusic-store"


@pytest.mark.parametrize(
    "entry",
    [
        _database(locator="../outside-store"),
        _database(encryption="sqlite"),
        _database(key_env_var="not-an-environment-variable"),
        _database(basename="backup.txt"),
    ],
)
def test_load_database_inventory_rejects_unsafe_entries(
    tmp_path: Path, entry: dict[str, object]
) -> None:
    inventory_path = tmp_path / "database_backup_inventory.json"
    inventory_path.write_text(
        json.dumps(_inventory([entry])), encoding="utf-8"
    )

    with pytest.raises(ValueError):
        load_database_inventory(inventory_path)


def test_projection_preserves_denied_source_reason(tmp_path: Path) -> None:
    denied = _database(
        id="music-legacy-store",
        locator="music/legacy-store",
        basename="legacy.db",
        classification="legacy",
        backup_allowed=False,
        reason="Legacy plaintext artifact; excluded from backup.",
    )
    inventory_path = tmp_path / "database_backup_inventory.json"
    inventory_path.write_text(json.dumps(_inventory([denied])), encoding="utf-8")

    manifest = build_backup_manifest(load_database_inventory(inventory_path))

    assert manifest["databases"][0]["backup_allowed"] is False
    assert manifest["databases"][0]["reason"] == denied["reason"]
