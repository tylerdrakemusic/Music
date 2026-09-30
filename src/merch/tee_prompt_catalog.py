"""Validated read/write access to the canonical tee prompt catalog."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping
from contextlib import contextmanager
from typing import Any, Iterator


CATALOG_ID = "TJD-MERCH-TEE-PROMPTS"
_ID_PATTERN = re.compile(r"TJD-TEE-\d{3}\Z")
_VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)\.(\d+)\Z")
_IMAGE_INPUT_FIELDS = frozenset(
    {"title", "concept", "intended_garment_use", "palette", "print_notes"}
)
_TEXT_FIELDS = frozenset(
    {"title", "concept", "intended_garment_use", "print_notes"}
)
_PROVENANCE_FIELDS = frozenset(
    {"source", "source_entry", "curation_decision"}
)
_CREATE_FIELDS = frozenset(
    {"id", *_IMAGE_INPUT_FIELDS, "provenance"}
)
_EDIT_FIELDS = frozenset(_IMAGE_INPUT_FIELDS | {"provenance"})


@contextmanager
def _write_transaction(connection: sqlite3.Connection) -> Iterator[None]:
    savepoint = "tee_prompt_catalog_write"
    connection.execute(f"SAVEPOINT {savepoint}")
    try:
        yield
        connection.execute(f"RELEASE SAVEPOINT {savepoint}")
    except Exception:
        connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        connection.execute(f"RELEASE SAVEPOINT {savepoint}")
        raise


def _row_dict(cursor: sqlite3.Cursor, row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    names = [column[0] for column in cursor.description or ()]
    if isinstance(row, sqlite3.Row):
        return dict(row)
    return dict(zip(names, row, strict=True))


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _validate_id(value: object) -> str:
    catalog_id = _require_text(value, "id")
    if not _ID_PATTERN.fullmatch(catalog_id):
        raise ValueError("id must use the stable TJD-TEE-NNN format")
    return catalog_id


def _validate_palette(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError("palette must be a non-empty list of strings")
    return [_require_text(color, "palette item") for color in value]


def _validate_provenance(value: object, *, partial: bool) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError("provenance must be a non-empty object")
    unknown = set(value) - _PROVENANCE_FIELDS
    if unknown:
        raise ValueError(f"unsupported provenance fields: {sorted(unknown)!r}")
    if not partial and set(value) != _PROVENANCE_FIELDS:
        raise ValueError("provenance must include source, source_entry, and curation_decision")
    return {field: _require_text(item, f"provenance.{field}") for field, item in value.items()}


def _validate_prompt(prompt: object) -> dict[str, Any]:
    if not isinstance(prompt, Mapping):
        raise ValueError("prompt must be an object")
    unknown = set(prompt) - _CREATE_FIELDS
    missing = _CREATE_FIELDS - set(prompt)
    if unknown or missing:
        raise ValueError(
            f"prompt fields mismatch; missing={sorted(missing)!r}, unknown={sorted(unknown)!r}"
        )
    validated: dict[str, Any] = {"id": _validate_id(prompt["id"])}
    for field in _TEXT_FIELDS:
        validated[field] = _require_text(prompt[field], field)
    validated["palette"] = _validate_palette(prompt["palette"])
    validated["provenance"] = _validate_provenance(prompt["provenance"], partial=False)
    return validated


def _validate_changes(changes: object) -> dict[str, Any]:
    if not isinstance(changes, Mapping) or not changes:
        raise ValueError("changes must be a non-empty object")
    unknown = set(changes) - _EDIT_FIELDS
    if unknown:
        raise ValueError(f"unsupported edit fields: {sorted(unknown)!r}")
    validated: dict[str, Any] = {}
    for field, value in changes.items():
        if field in _TEXT_FIELDS:
            validated[field] = _require_text(value, field)
        elif field == "palette":
            validated[field] = _validate_palette(value)
        else:
            validated[field] = _validate_provenance(value, partial=True)
    return validated


def _next_catalog_version(version: str) -> str:
    match = _VERSION_PATTERN.fullmatch(version)
    if match is None:
        raise ValueError(f"unsupported catalog version: {version!r}")
    major, minor, patch = (int(part) for part in match.groups())
    return f"{major}.{minor}.{patch + 1}"


def _prompt_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "concept": row["concept"],
        "intended_garment_use": row["intended_garment_use"],
        "palette": json.loads(row["palette_json"]),
        "print_notes": row["print_notes"],
        "provenance": {
            "source": row["provenance_source"],
            "source_entry": row["provenance_source_entry"],
            "curation_decision": row["provenance_curation_decision"],
        },
        "concept_revision": row["concept_revision"],
        "image_prompt_revision": row["image_prompt_revision"],
        "concept_approval_revision": row["concept_approval_revision"],
        "concept_approval_status": row["concept_approval_status"],
        "exact_image_approval_status": row["exact_image_approval_status"],
        "catalog_version": row["catalog_version"],
    }


class TeePromptCatalog:
    """Read and transactionally curate concepts in the tee catalog tables."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def read_catalog(self) -> dict[str, Any]:
        cursor = self.connection.execute(
            """SELECT catalog_id, version, phase, artist, aliases_json, evidence_json,
                      approval_workflow_json, provider_tracking_json
               FROM tee_prompt_catalogs WHERE catalog_id = ?""",
            (CATALOG_ID,),
        )
        catalog = _row_dict(cursor, cursor.fetchone())
        if catalog is None:
            raise ValueError(f"tee catalog not found: {CATALOG_ID}")
        result = {
            "catalog_id": catalog["catalog_id"],
            "version": catalog["version"],
            "phase": catalog["phase"],
            "artist": catalog["artist"],
            "aliases": json.loads(catalog["aliases_json"]),
            "evidence": json.loads(catalog["evidence_json"]),
            "approval_workflow": json.loads(catalog["approval_workflow_json"]),
            "provider_tracking": json.loads(catalog["provider_tracking_json"]),
            "prompts": self.list_prompts(),
        }
        return result

    def list_prompts(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """SELECT p.*, c.version AS catalog_version
               FROM tee_prompts p
               JOIN tee_prompt_catalogs c ON c.catalog_id = p.catalog_id
               WHERE p.catalog_id = ? ORDER BY p.id""",
            (CATALOG_ID,),
        ).fetchall()
        if not rows:
            self._require_catalog()
        return [_prompt_from_row(row) for row in rows]

    def read_prompt(self, prompt_id: str) -> dict[str, Any]:
        stable_id = _validate_id(prompt_id)
        row = self._get_prompt_row(stable_id)
        if row is None:
            raise KeyError(f"tee concept not found: {stable_id}")
        return _prompt_from_row(row)

    def create_prompt(
        self, prompt: Mapping[str, Any], *, approved_by_tyler: bool = False
    ) -> dict[str, Any]:
        validated = _validate_prompt(prompt)
        if approved_by_tyler is not True:
            raise PermissionError("creation requires explicit Tyler approval")

        with _write_transaction(self.connection):
            self._require_catalog()
            exists = self.connection.execute(
                "SELECT 1 FROM tee_prompts WHERE id = ?", (validated["id"],)
            ).fetchone()
            if exists is not None:
                raise ValueError(f"tee concept ID already exists: {validated['id']}")
            self._advance_catalog_version()
            provenance = validated["provenance"]
            self.connection.execute(
                """INSERT INTO tee_prompts
                   (id, catalog_id, title, concept, intended_garment_use, palette_json,
                    print_notes, provenance_source, provenance_source_entry,
                    provenance_curation_decision, concept_revision,
                    concept_approval_revision, concept_approval_status,
                    exact_image_approval_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1,
                           'concept_approved', 'not_started')""",
                (
                    validated["id"], CATALOG_ID, validated["title"],
                    validated["concept"], validated["intended_garment_use"],
                    json.dumps(validated["palette"], ensure_ascii=False),
                    validated["print_notes"], provenance["source"],
                    provenance["source_entry"], provenance["curation_decision"],
                ),
            )
        return self.read_prompt(validated["id"])

    def edit_prompt(
        self,
        prompt_id: str,
        changes: Mapping[str, Any],
        *,
        approved_by_tyler: bool = False,
    ) -> dict[str, Any]:
        stable_id = _validate_id(prompt_id)
        validated = _validate_changes(changes)
        with _write_transaction(self.connection):
            row = self._get_prompt_row(stable_id)
            if row is None:
                raise KeyError(f"tee concept not found: {stable_id}")
            current = _prompt_from_row(row)
            normalized = dict(validated)
            if "provenance" in normalized:
                normalized["provenance"] = {
                    **current["provenance"], **normalized["provenance"]
                }

            changed = {
                field: value
                for field, value in normalized.items()
                if value != current[field]
            }
            concept_changed = "concept" in changed
            if concept_changed and approved_by_tyler is not True:
                raise PermissionError("concept changes require explicit Tyler approval")
            if not changed:
                return current

            image_input_changed = bool(_IMAGE_INPUT_FIELDS.intersection(changed))
            columns: dict[str, Any] = {}
            for field, value in changed.items():
                if field == "palette":
                    columns["palette_json"] = json.dumps(value, ensure_ascii=False)
                elif field == "provenance":
                    columns.update(
                        {
                            "provenance_source": value["source"],
                            "provenance_source_entry": value["source_entry"],
                            "provenance_curation_decision": value["curation_decision"],
                        }
                    )
                else:
                    columns[field] = value

            if concept_changed:
                revision = int(current["concept_revision"]) + 1
                columns["concept_revision"] = revision
                columns["concept_approval_revision"] = revision
                columns["concept_approval_status"] = "concept_approved"
            if image_input_changed:
                self._advance_catalog_version()
                columns["image_prompt_revision"] = int(current["image_prompt_revision"]) + 1
                columns["exact_image_approval_status"] = "not_started"

            assignments = ", ".join(f"{column} = ?" for column in columns)
            self.connection.execute(
                f"UPDATE tee_prompts SET {assignments}, updated_at = datetime('now') WHERE id = ?",
                (*columns.values(), stable_id),
            )
        return self.read_prompt(stable_id)

    def approve_exact_image(
        self,
        prompt_id: str,
        *,
        expected_image_prompt_revision: int,
        expected_concept_revision: int,
        approved_by_tyler: bool = False,
    ) -> dict[str, Any]:
        """Persist an exact-image decision only for the approved current revision."""
        stable_id = _validate_id(prompt_id)
        if type(expected_image_prompt_revision) is not int or expected_image_prompt_revision < 1:
            raise ValueError("image prompt revision must be a positive integer")
        if type(expected_concept_revision) is not int or expected_concept_revision < 1:
            raise ValueError("concept revision must be a positive integer")
        if approved_by_tyler is not True:
            raise PermissionError("exact-image approval requires Tyler's explicit decision")

        with _write_transaction(self.connection):
            row = self._get_prompt_row(stable_id)
            if row is None:
                raise KeyError(f"tee concept not found: {stable_id}")
            current = _prompt_from_row(row)
            if (
                current["image_prompt_revision"] != expected_image_prompt_revision
                or current["concept_revision"] != expected_concept_revision
                or current["concept_approval_revision"] != expected_concept_revision
                or current["concept_approval_status"] != "concept_approved"
            ):
                raise ValueError("tee catalog or concept revision changed before image approval")
            self.connection.execute(
                "UPDATE tee_prompts SET exact_image_approval_status = 'exact_image_approved', "
                "updated_at = datetime('now') WHERE id = ?",
                (stable_id,),
            )
            current["exact_image_approval_status"] = "exact_image_approved"
        return current

    def reconcile_exact_image_approval(
        self,
        prompt_id: str,
        *,
        expected_image_prompt_revision: int,
        expected_concept_revision: int,
        has_matching_approved_sidecar: bool,
    ) -> dict[str, Any]:
        """Reconcile current image state from verified sidecars for one revision."""
        stable_id = _validate_id(prompt_id)
        if type(expected_image_prompt_revision) is not int or expected_image_prompt_revision < 1:
            raise ValueError("image prompt revision must be a positive integer")
        if type(expected_concept_revision) is not int or expected_concept_revision < 1:
            raise ValueError("concept revision must be a positive integer")
        if type(has_matching_approved_sidecar) is not bool:
            raise ValueError("sidecar approval state must be a boolean")

        status = "exact_image_approved" if has_matching_approved_sidecar else "not_started"
        with _write_transaction(self.connection):
            row = self._get_prompt_row(stable_id)
            if row is None:
                raise KeyError(f"tee concept not found: {stable_id}")
            current = _prompt_from_row(row)
            if (
                current["image_prompt_revision"] != expected_image_prompt_revision
                or current["concept_revision"] != expected_concept_revision
                or current["concept_approval_revision"] != expected_concept_revision
                or current["concept_approval_status"] != "concept_approved"
            ):
                raise ValueError("tee catalog or concept revision changed during reconciliation")
            if current["exact_image_approval_status"] != status:
                self.connection.execute(
                    "UPDATE tee_prompts SET exact_image_approval_status = ?, "
                    "updated_at = datetime('now') WHERE id = ?",
                    (status, stable_id),
                )
        return self.read_prompt(stable_id)

    def _require_catalog(self) -> dict[str, Any]:
        cursor = self.connection.execute(
            "SELECT * FROM tee_prompt_catalogs WHERE catalog_id = ?", (CATALOG_ID,)
        )
        catalog = _row_dict(cursor, cursor.fetchone())
        if catalog is None:
            raise ValueError(f"tee catalog not found: {CATALOG_ID}")
        return catalog

    def _get_prompt_row(self, prompt_id: str) -> dict[str, Any] | None:
        cursor = self.connection.execute(
            """SELECT p.*, c.version AS catalog_version
               FROM tee_prompts p
               JOIN tee_prompt_catalogs c ON c.catalog_id = p.catalog_id
               WHERE p.catalog_id = ? AND p.id = ?""",
            (CATALOG_ID, prompt_id),
        )
        return _row_dict(cursor, cursor.fetchone())

    def _advance_catalog_version(self) -> str:
        catalog = self._require_catalog()
        version = _next_catalog_version(catalog["version"])
        self.connection.execute(
            "UPDATE tee_prompt_catalogs SET version = ?, updated_at = datetime('now') WHERE catalog_id = ?",
            (version, CATALOG_ID),
        )
        return version
