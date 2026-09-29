from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.utils import init_db


def test_fresh_initializer_bootstraps_tee_catalog_and_preserves_edits(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = tmp_path / "heartmusic-init.sqlite"

    def connect_to_temporary_database(*, create_if_missing: bool = False) -> sqlite3.Connection:
        del create_if_missing
        return sqlite3.connect(database_path)

    monkeypatch.setattr(init_db, "get_connection", connect_to_temporary_database)

    init_db.init_db()

    connection = sqlite3.connect(database_path)
    try:
        prompt_ids = [
            row[0]
            for row in connection.execute("SELECT id FROM tee_prompts ORDER BY id")
        ]
        assert prompt_ids == [
            "TJD-TEE-001",
            "TJD-TEE-002",
            "TJD-TEE-003",
            "TJD-TEE-004",
            "TJD-TEE-005",
            "TJD-TEE-006",
        ]
        connection.execute(
            "UPDATE tee_prompts SET title = ? WHERE id = ?",
            ("Curated title", "TJD-TEE-001"),
        )
        connection.commit()
    finally:
        connection.close()

    init_db.init_db()

    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute(
            "SELECT title FROM tee_prompts WHERE id = ?", ("TJD-TEE-001",)
        ).fetchone() == ("Curated title",)
    finally:
        connection.close()


def test_initializer_without_seed_imports_tee_catalog_without_album_or_track_seeds(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = tmp_path / "heartmusic-no-seed.sqlite"

    def connect_to_temporary_database(*, create_if_missing: bool = False) -> sqlite3.Connection:
        del create_if_missing
        return sqlite3.connect(database_path)

    monkeypatch.setattr(init_db, "get_connection", connect_to_temporary_database)

    init_db.init_db(seed=False)

    connection = sqlite3.connect(database_path)
    try:
        assert [
            row[0]
            for row in connection.execute("SELECT id FROM tee_prompts ORDER BY id")
        ] == [
            "TJD-TEE-001",
            "TJD-TEE-002",
            "TJD-TEE-003",
            "TJD-TEE-004",
            "TJD-TEE-005",
            "TJD-TEE-006",
        ]
        assert connection.execute("SELECT COUNT(*) FROM albums").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0] == 0
    finally:
        connection.close()


def test_bootstrap_import_preserves_curated_catalog_edits(tmp_path: Path) -> None:
    connection = sqlite3.connect(tmp_path / "tee-catalog.sqlite")
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript(init_db._SCHEMA_SQL)
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {
            "tee_prompt_catalogs",
            "tee_prompts",
            "tee_catalog_bootstrap_imports",
        } <= tables

        importer = getattr(init_db, "import_tee_catalog_bootstrap", None)
        assert callable(importer), "canonical tee bootstrap importer is missing"
        assert importer(connection) is True

        catalog = connection.execute(
            "SELECT * FROM tee_prompt_catalogs WHERE catalog_id = ?",
            ("TJD-MERCH-TEE-PROMPTS",),
        ).fetchone()
        assert catalog["version"] == "1.0.0"
        assert catalog["artist"] == "Tyler James Drake"
        assert json.loads(catalog["aliases_json"]) == ["EchoTy"]
        assert json.loads(catalog["approval_workflow_json"])[-1] == "exact_image_approved"

        prompts = connection.execute(
            "SELECT * FROM tee_prompts ORDER BY id"
        ).fetchall()
        assert [prompt["id"] for prompt in prompts] == [
            "TJD-TEE-001",
            "TJD-TEE-002",
            "TJD-TEE-003",
            "TJD-TEE-004",
            "TJD-TEE-005",
            "TJD-TEE-006",
        ]
        assert len(prompts) == 6
        first = prompts[0]
        assert first["concept_revision"] == 1
        assert first["concept_approval_revision"] == 1
        assert first["concept_approval_status"] == "concept_approved"
        assert first["exact_image_approval_status"] == "exact_image_approved"
        assert first["provenance_source"] == "Brand/t-design prompts.txt"
        assert first["provenance_source_entry"].startswith("gritty vintage illustration")
        last = prompts[-1]
        assert last["provenance_source"] == "operator-authored"
        assert last["concept_approval_status"] == "concept_approved"
        assert last["exact_image_approval_status"] == "exact_image_approved"
        assert all("Denver Nuggets" not in prompt["provenance_source_entry"] for prompt in prompts)

        connection.execute(
            "UPDATE tee_prompts SET title = ? WHERE id = ?",
            ("Curated title", "TJD-TEE-001"),
        )
        connection.execute(
            "UPDATE tee_prompt_catalogs SET version = ? WHERE catalog_id = ?",
            ("edited-in-db", "TJD-MERCH-TEE-PROMPTS"),
        )
        connection.commit()

        assert importer(connection) is False
        assert connection.execute(
            "SELECT COUNT(*) FROM tee_prompts"
        ).fetchone()[0] == 6
        assert connection.execute(
            "SELECT title FROM tee_prompts WHERE id = ?", ("TJD-TEE-001",)
        ).fetchone()[0] == "Curated title"
        assert connection.execute(
            "SELECT version FROM tee_prompt_catalogs WHERE catalog_id = ?",
            ("TJD-MERCH-TEE-PROMPTS",),
        ).fetchone()[0] == "edited-in-db"
    finally:
        connection.close()