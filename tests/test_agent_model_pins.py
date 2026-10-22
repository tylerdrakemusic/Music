from pathlib import Path
import json
import re

import pytest
import yaml


MUSIC_ROOT = Path(__file__).resolve().parents[1]
def _parse_frontmatter(text: str) -> dict[str, object]:
    lines = text.splitlines()
    assert lines and lines[0].strip() == "---", "Agent file must start with YAML frontmatter"
    closing_index = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
        None,
    )
    assert closing_index is not None, "Agent YAML frontmatter must have a closing delimiter"

    yaml_lines = lines[1:closing_index]
    for index, line in enumerate(yaml_lines):
        if not line.startswith("description:"):
            continue
        value = line.partition(":")[2].strip()
        if value and value[0] not in "'\"|>":
            yaml_lines[index] = f"description: {json.dumps(value, ensure_ascii=False)}"

    parsed = yaml.safe_load("\n".join(yaml_lines))
    assert isinstance(parsed, dict), "Agent YAML frontmatter must be a mapping"
    return parsed


def _load_agent_frontmatter(path: Path) -> dict[str, object]:
    return _parse_frontmatter(path.read_text(encoding="utf-8"))


def _find_forbidden_fields(frontmatter: dict[str, object]) -> list[str]:
    forbidden = []
    for field_name in frontmatter:
        normalized = re.sub(r"(?<!^)(?=[A-Z])", "_", str(field_name))
        normalized = normalized.replace("-", "_").lower()
        is_pin_field = normalized in {"model", "provider"} or (
            "multiplier" in normalized and ("model" in normalized or "cost" in normalized)
        )
        if is_pin_field:
            forbidden.append(str(field_name))
    return sorted(forbidden)


@pytest.mark.parametrize(
    "field_name",
    (
        "model",
        "provider",
        "model_multiplier",
        "cost_multiplier",
        "model_cost_multiplier",
        "cost_model_multiplier",
        "model-cost-multiplier",
        "token_cost_multiplier",
    ),
)
def test_top_level_model_pins_are_detected(field_name: str) -> None:
    frontmatter = f"---\n{field_name}: pinned-value\n---\n"

    assert _find_forbidden_fields(_parse_frontmatter(frontmatter)) == [field_name]


def test_nested_model_metadata_is_not_treated_as_a_pin() -> None:
    frontmatter = "---\nmetadata:\n  model: descriptive-value\n---\n"

    assert _find_forbidden_fields(_parse_frontmatter(frontmatter)) == []


def test_unquoted_description_colon_remains_parseable() -> None:
    frontmatter = "---\nname: agent\ndescription: Tool: use for music\n---\n"

    assert _parse_frontmatter(frontmatter)["description"] == "Tool: use for music"


def test_music_agent_frontmatter_has_no_model_pins() -> None:
    agent_dir = MUSIC_ROOT / ".github" / "agents"
    agent_files = sorted(agent_dir.rglob("*.agent.md"))
    assert agent_files, f"No agent definitions found under {agent_dir}"

    violations = {
        str(path.relative_to(MUSIC_ROOT)): fields
        for path in agent_files
        if (fields := _find_forbidden_fields(_load_agent_frontmatter(path)))
    }

    assert not violations, f"Agent definitions contain pinned model fields: {violations}"