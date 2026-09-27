"""Contract checks for the phase-one Tyler James Drake merch catalog."""

import json
from pathlib import Path


REPO_ROOT = Path(__file__).parents[1]
CATALOG_PATH = REPO_ROOT / "Brand" / "tyler-james-drake-tee-prompt-catalog.json"
BRAND_SYSTEM_PATH = REPO_ROOT / "Brand" / "tyler-james-drake-merch-brand-system.md"


def test_catalog_has_stable_rights_aware_prompt_records() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

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