from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from src.merch.tee_prompt_catalog import TeePromptCatalog
from src.utils import init_db


@pytest.fixture
def tee_catalog(tmp_path: Path) -> tuple[TeePromptCatalog, sqlite3.Connection]:
    connection = sqlite3.connect(tmp_path / "tee-catalog.sqlite")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(init_db._SCHEMA_SQL)
    init_db.import_tee_catalog_bootstrap(connection)
    yield TeePromptCatalog(connection), connection
    connection.close()


def _new_prompt(prompt_id: str = "TJD-TEE-007") -> dict[str, object]:
    return {
        "id": prompt_id,
        "title": "Rain on the Soundcheck",
        "concept": "A fictional guitarist carries an instrument case through rain after a show.",
        "intended_garment_use": "Centered front print for a dark tee.",
        "palette": ["ink black", "aged cream", "storm gray"],
        "print_notes": "Opaque two-color screen print with open negative space.",
        "provenance": {
            "source": "operator-authored",
            "source_entry": "Tyler's newly approved rainy-night direction",
            "curation_decision": "original concept, rights-aware and print-conscious",
        },
    }


def _catalog_version(connection: sqlite3.Connection) -> str:
    row = connection.execute(
        "SELECT version FROM tee_prompt_catalogs WHERE catalog_id = ?",
        ("TJD-MERCH-TEE-PROMPTS",),
    ).fetchone()
    return str(row[0])


def _prompt_count(connection: sqlite3.Connection) -> int:
    return int(connection.execute("SELECT COUNT(*) FROM tee_prompts").fetchone()[0])


def test_new_concept_is_persisted_only_after_explicit_approval(
    tee_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    catalog, connection = tee_catalog

    created = catalog.create_prompt(_new_prompt(), approved_by_tyler=True)

    assert created["id"] == "TJD-TEE-007"
    assert created["concept_revision"] == 1
    assert created["concept_approval_revision"] == 1
    assert created["concept_approval_status"] == "concept_approved"
    assert created["exact_image_approval_status"] == "not_started"
    assert created["provenance"]["source"] == "operator-authored"
    assert _prompt_count(connection) == 7
    assert _catalog_version(connection) == "1.0.1"


def test_rejected_new_concept_writes_nothing(
    tee_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    catalog, connection = tee_catalog

    with pytest.raises(PermissionError, match="explicit Tyler approval"):
        catalog.create_prompt(_new_prompt(), approved_by_tyler=False)

    assert _prompt_count(connection) == 6
    assert _catalog_version(connection) == "1.0.0"
    assert catalog.list_prompts()[-1]["id"] == "TJD-TEE-006"


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "TJD-TEE-07"},
        {"title": "   "},
        {"palette": ["ink black", 7]},
        {"unexpected_field": "must not be silently dropped"},
    ],
)
def test_create_rejects_invalid_fields_without_writing(
    tee_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
    changes: dict[str, object],
) -> None:
    catalog, connection = tee_catalog
    proposed = _new_prompt()
    proposed.update(changes)

    with pytest.raises(ValueError):
        catalog.create_prompt(proposed, approved_by_tyler=True)

    assert _prompt_count(connection) == 6
    assert _catalog_version(connection) == "1.0.0"


def test_create_rejects_an_existing_stable_id(
    tee_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    catalog, connection = tee_catalog
    duplicate = _new_prompt("TJD-TEE-001")

    with pytest.raises(ValueError, match="already exists"):
        catalog.create_prompt(duplicate, approved_by_tyler=True)

    assert _prompt_count(connection) == 6
    assert _catalog_version(connection) == "1.0.0"


def test_non_core_edit_preserves_concept_and_provenance(
    tee_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    catalog, connection = tee_catalog
    before = catalog.read_prompt("TJD-TEE-001")

    edited = catalog.edit_prompt("TJD-TEE-001", {"title": "Jukebox at Dawn"})

    assert edited["title"] == "Jukebox at Dawn"
    assert edited["concept"] == before["concept"]
    assert edited["concept_revision"] == before["concept_revision"] == 1
    assert edited["concept_approval_revision"] == before["concept_approval_revision"] == 1
    assert edited["concept_approval_status"] == "concept_approved"
    assert edited["provenance"] == before["provenance"]
    assert edited["exact_image_approval_status"] == "not_started"
    assert _catalog_version(connection) == "1.0.1"


def test_core_concept_requires_approval_and_approval_advances_revision(
    tee_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    catalog, connection = tee_catalog
    original = catalog.read_prompt("TJD-TEE-001")
    revised_concept = "A fictional guitarist leaves an unlit jukebox behind at dawn."

    with pytest.raises(PermissionError, match="explicit Tyler approval"):
        catalog.edit_prompt("TJD-TEE-001", {"concept": revised_concept})
    assert catalog.read_prompt("TJD-TEE-001") == original
    assert _catalog_version(connection) == "1.0.0"

    edited = catalog.edit_prompt(
        "TJD-TEE-001",
        {"concept": revised_concept},
        approved_by_tyler=True,
    )

    assert edited["concept"] == revised_concept
    assert edited["concept_revision"] == 2
    assert edited["concept_approval_revision"] == 2
    assert edited["concept_approval_status"] == "concept_approved"
    assert edited["exact_image_approval_status"] == "not_started"
    assert _catalog_version(connection) == "1.0.1"


def test_image_input_change_invalidates_current_image_approval_without_deleting_assets(
    tee_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
    tmp_path: Path,
) -> None:
    catalog, connection = tee_catalog
    connection.execute(
        "UPDATE tee_prompts SET exact_image_approval_status = ? WHERE id = ?",
        ("exact_image_approved", "TJD-TEE-001"),
    )
    connection.commit()
    prior_asset = tmp_path / "approved" / "TJD-TEE-001" / "revision-1.png"
    prior_asset.parent.mkdir(parents=True)
    prior_asset.write_bytes(b"previously approved artwork")

    edited = catalog.edit_prompt(
        "TJD-TEE-001",
        {"palette": ["ink black", "aged cream"]},
    )

    assert edited["exact_image_approval_status"] == "not_started"
    assert _catalog_version(connection) == "1.0.1"
    assert prior_asset.read_bytes() == b"previously approved artwork"


def test_failed_edit_rolls_back_prompt_and_catalog_revision(
    tee_catalog: tuple[TeePromptCatalog, sqlite3.Connection],
) -> None:
    catalog, connection = tee_catalog
    connection.execute(
        """
        CREATE TRIGGER reject_tee_prompt_update
        BEFORE UPDATE ON tee_prompts
        BEGIN
            SELECT RAISE(ABORT, 'forced test failure');
        END
        """
    )
    connection.commit()

    with pytest.raises(sqlite3.IntegrityError, match="forced test failure"):
        catalog.edit_prompt("TJD-TEE-001", {"title": "Should Roll Back"})

    assert catalog.read_prompt("TJD-TEE-001")["title"] == "Walk Away From the Jukebox"
    assert _catalog_version(connection) == "1.0.0"
    assert not connection.in_transaction
