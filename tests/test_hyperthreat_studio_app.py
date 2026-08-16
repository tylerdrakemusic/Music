"""Focused tests for the isolated Hyperthreat Studios templates app."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture()
def client():
    from studio.hyperthreat_app import app

    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def test_launcher_links_templates_and_health(client):
    response = client.get("/")

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert 'href="/mic-config"' in html
    assert 'href="/patch-bay"' in html
    assert 'href="/"' in html
    assert client.get("/health").get_json() == {"status": "ok", "ready": True}


def test_template_routes_preserve_existing_documents(client):
    mic_response = client.get("/mic-config")
    patch_response = client.get("/patch-bay")

    assert mic_response.status_code == 200
    assert patch_response.status_code == 200
    assert mic_response.data == (ROOT / "studio" / "mic_config_template.html").read_bytes()
    assert patch_response.data == (ROOT / "studio" / "patch_bay.html").read_bytes()


@pytest.mark.parametrize(
    ("template", "markers"),
    [
        (
            "mic_config_template.html",
            ["window.print()", "Save to File", "localStorage", "clear-button"],
        ),
        (
            "patch_bay.html",
            ["@media print", "Save to File", "localStorage", "legend-reset-button"],
        ),
    ],
)
def test_templates_keep_local_print_reset_and_export_behaviors(template, markers):
    html = (ROOT / "studio" / template).read_text(encoding="utf-8")

    for marker in markers:
        assert marker in html


def test_isolated_deployment_files_use_minimal_context():
    dockerfile = (ROOT / "Dockerfile.hyperthreat-studio").read_text(encoding="utf-8")
    fly_config = (ROOT / "fly.hyperthreat-studio.toml").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "deploy-hyperthreat-studio.yml").read_text(
        encoding="utf-8"
    )

    assert "COPY src/studio/hyperthreat_app.py" in dockerfile
    assert "COPY studio/mic_config_template.html" in dockerfile
    assert "COPY studio/patch_bay.html" in dockerfile
    assert "heartmusic.db" not in dockerfile
    assert "app = 'ht'" in fly_config
    assert "guitartrainer" not in fly_config
    assert "pytest" in workflow
    assert "flyctl deploy" in workflow
    assert "fly.toml" not in workflow