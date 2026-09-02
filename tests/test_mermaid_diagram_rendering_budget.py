from pathlib import Path


DIAGRAM_DIR = Path(__file__).resolve().parents[1] / "diagrams"
EXPECTED_DIAGRAMS = (
    "music-architecture.mmd",
    "music-db-schema.mmd",
    "music-tech-stack.mmd",
    "music-icecast-primary-architecture.mmd",
)
MAX_RENDERING_BYTES = 10_000


def test_music_mermaid_sources_fit_local_rendering_budget():
    for filename in EXPECTED_DIAGRAMS:
        source = DIAGRAM_DIR / filename

        assert source.is_file(), f"Missing canonical Music diagram: {filename}"
        content = source.read_text(encoding="utf-8")
        diagram_body = "\n".join(
            line for line in content.splitlines() if not line.startswith("%%{init")
        ).lstrip()
        assert diagram_body.startswith(
            ("flowchart", "graph", "sequenceDiagram", "classDiagram", "erDiagram")
        )
        assert source.stat().st_size <= MAX_RENDERING_BYTES