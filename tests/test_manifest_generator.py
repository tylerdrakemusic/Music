import os
import json
import tempfile
from pathlib import Path
from src.utils import manifest_generator

def test_manifest_generation(tmp_path):
    # Setup: create a fake catalog with files
    catalog_dir = tmp_path / "catalog"
    catalog_dir.mkdir()
    (catalog_dir / "song1.mp3").write_bytes(b"fake mp3 data")
    (catalog_dir / "song2.wav").write_bytes(b"fake wav data")
    manifest_path = catalog_dir / "manifest.json"

    # Patch generator paths
    orig_catalog = manifest_generator.CATALOG_DIR
    orig_manifest = manifest_generator.MANIFEST_PATH
    manifest_generator.CATALOG_DIR = catalog_dir
    manifest_generator.MANIFEST_PATH = manifest_path

    try:
        manifest = manifest_generator.generate_manifest()
        assert manifest_path.exists()
        with open(manifest_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["manifest_version"] == 1
        assert "generated_at" in data
        assert len(data["catalog"]) == 2
        for entry in data["catalog"]:
            assert set(entry.keys()) == set(manifest_generator.METADATA_FIELDS)
    finally:
        manifest_generator.CATALOG_DIR = orig_catalog
        manifest_generator.MANIFEST_PATH = orig_manifest
