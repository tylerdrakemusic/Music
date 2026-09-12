from __future__ import annotations

import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPOSITORY_ROOT / "diagrams" / "diagram-manifest.json"


def test_music_manifest_declares_only_canonical_diagram_sources() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["schema_version"] == 1
    assert manifest["repository"] == "music"
    assert [record["path"] for record in manifest["diagrams"]] == [
        "diagrams/music-architecture.mmd",
        "diagrams/music-derived-catalog-pipeline.mmd",
        "diagrams/music-derived-operations-surfaces.mmd",
        "diagrams/music-db-schema.mmd",
        "diagrams/music-tech-stack.mmd",
    ]
    assert all(
        set(record) == {
            "path",
            "kind",
            "renderer_risk",
            "fallback_risk",
            "split_required",
            "lineage",
        }
        for record in manifest["diagrams"]
    )
    assert "docs/studio-wiring-decision.mmd" not in {
        record["path"] for record in manifest["diagrams"]
    }


def test_music_manifest_declares_parent_child_lineage_for_architecture_split() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    records = {record["path"]: record for record in manifest["diagrams"]}

    assert records["diagrams/music-architecture.mmd"]["lineage"] == {
        "parent": None,
        "derived_views": [
            "diagrams/music-derived-catalog-pipeline.mmd",
            "diagrams/music-derived-operations-surfaces.mmd",
        ],
    }
    assert records["diagrams/music-derived-catalog-pipeline.mmd"]["lineage"] == {
        "parent": "diagrams/music-architecture.mmd",
        "derived_views": [],
    }
    assert records["diagrams/music-derived-operations-surfaces.mmd"]["lineage"] == {
        "parent": "diagrams/music-architecture.mmd",
        "derived_views": [],
    }