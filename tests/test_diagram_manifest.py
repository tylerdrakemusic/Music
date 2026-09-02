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
        "diagrams/music-db-schema.mmd",
        "diagrams/music-icecast-primary-architecture.mmd",
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