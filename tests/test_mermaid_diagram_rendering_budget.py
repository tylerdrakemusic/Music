from pathlib import Path


DIAGRAM_DIR = Path(__file__).resolve().parents[1] / "diagrams"
EXPECTED_DIAGRAMS = (
    "music-architecture.mmd",
    "music-derived-catalog-pipeline.mmd",
    "music-derived-operations-surfaces.mmd",
    "music-db-schema.mmd",
    "music-tech-stack.mmd",
)
MAX_RENDERING_BYTES = 10_000


def test_music_mermaid_sources_fit_local_rendering_budget():
    for filename in EXPECTED_DIAGRAMS:
        source = DIAGRAM_DIR / filename

        assert source.is_file(), f"Missing canonical Music diagram: {filename}"
        content = source.read_text(encoding="utf-8")
        diagram_body = "\n".join(
            line for line in content.splitlines() if not line.startswith("%%")
        ).lstrip()
        assert diagram_body.startswith(
            ("flowchart", "graph", "sequenceDiagram", "classDiagram", "erDiagram")
        )
        assert source.stat().st_size <= MAX_RENDERING_BYTES


def test_music_architecture_split_preserves_canonical_relationships() -> None:
    architecture = (DIAGRAM_DIR / "music-architecture.mmd").read_text(encoding="utf-8")
    catalog = (DIAGRAM_DIR / "music-derived-catalog-pipeline.mmd").read_text(encoding="utf-8")
    operations = (DIAGRAM_DIR / "music-derived-operations-surfaces.mmd").read_text(encoding="utf-8")

    assert "Traceability.derived_views: diagrams/music-derived-catalog-pipeline.mmd, diagrams/music-derived-operations-surfaces.mmd" in architecture
    assert "Inputs --> Catalog" in architecture
    assert "AudioFiles -->|scan| AutoTagger" in catalog
    assert "Dashboard --> BandMgmtPanel" in operations
    assert "Dashboard --> StudioPanel" in operations