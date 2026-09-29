"""Contract checks for the phase-one Tyler James Drake merch catalog."""

import sqlite3
from pathlib import Path

from src.merch.tee_prompt_catalog import TeePromptCatalog
from src.utils import init_db


REPO_ROOT = Path(__file__).parents[1]
BRAND_SYSTEM_PATH = REPO_ROOT / "Brand" / "tyler-james-drake-merch-brand-system.md"
CURATION_PROMPT_PATH = REPO_ROOT / ".github" / "prompts" / "tyler-merch-prompt-catalog.prompt.md"
IMAGE_PROMPT_PATH = REPO_ROOT / ".github" / "prompts" / "tyler-tee-image-generation.prompt.md"


def test_catalog_has_stable_rights_aware_prompt_records() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(init_db._SCHEMA_SQL)
    init_db.import_tee_catalog_bootstrap(connection)
    catalog = TeePromptCatalog(connection).read_catalog()

    assert catalog["phase"] == "phase-one"
    assert catalog["artist"] == "Tyler James Drake"
    assert catalog["approval_workflow"] == [
        "concept_pending",
        "concept_approved",
        "exact_image_pending",
        "exact_image_approved",
    ]

    prompts = catalog["prompts"]
    ids = [prompt["id"] for prompt in prompts]
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))
    assert len(prompts) >= 4

    required_fields = {
        "id",
        "title",
        "concept",
        "intended_garment_use",
        "palette",
        "print_notes",
        "provenance",
        "concept_revision",
        "concept_approval_revision",
        "concept_approval_status",
        "exact_image_approval_status",
    }
    for prompt in prompts:
        assert required_fields <= prompt.keys()
        assert prompt["provenance"]["source"] in {
            "Brand/t-design prompts.txt",
            "operator-authored",
        }
        assert prompt["concept_approval_status"] in {
            "concept_pending",
            "concept_approved",
            "rejected",
        }
        assert prompt["concept_revision"] >= 1
        assert prompt["concept_approval_revision"] == prompt["concept_revision"]
        assert prompt["exact_image_approval_status"] in {
            "not_started",
            "exact_image_pending",
            "exact_image_approved",
        }
    connection.close()


def test_brand_system_documents_phase_one_boundaries() -> None:
    guide = BRAND_SYSTEM_PATH.read_text(encoding="utf-8")

    for required_phrase in (
        "original music-world concepts only",
        "concept approval",
        "exact-image approval",
        "recognizable artists",
        "religious or cultural figures",
        "No image generation",
        "draft-only",
    ):
        assert required_phrase in guide


def test_curation_prompt_uses_catalog_api_instead_of_module_cli() -> None:
    prompt = CURATION_PROMPT_PATH.read_text(encoding="utf-8")

    assert "from src.utils.init_db import get_connection" in prompt
    assert "from src.merch.tee_prompt_catalog import TeePromptCatalog" in prompt
    for api_method in ("read_catalog(", "read_prompt(", "create_prompt(", "edit_prompt("):
        assert api_method in prompt
    assert "python -m src.merch.tee_prompt_catalog" not in prompt
    assert "explicit approval" in prompt.lower()


def test_image_prompt_preflight_reads_catalog_through_api() -> None:
    prompt = IMAGE_PROMPT_PATH.read_text(encoding="utf-8")

    assert "from src.utils.init_db import get_connection" in prompt
    assert "TeePromptCatalog(connection).read_prompt(catalog_id)" in prompt
    assert "python -m src.merch.tee_prompt_catalog" not in prompt