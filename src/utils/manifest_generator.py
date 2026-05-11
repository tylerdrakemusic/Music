import os
import json
from pathlib import Path
from datetime import datetime

CATALOG_DIR = Path(__file__).parent.parent.parent / "catalog"
MANIFEST_PATH = CATALOG_DIR / "manifest.json"

METADATA_FIELDS = [
    "filename", "path", "size", "date_added", "source", "artist", "album", "genre", "duration", "bitrate"
]

def get_file_metadata(file_path: Path) -> dict:
    stat = file_path.stat()
    return {
        "filename": file_path.name,
        "path": str(file_path.relative_to(CATALOG_DIR)),
        "size": stat.st_size,
        "date_added": datetime.utcfromtimestamp(stat.st_ctime).isoformat() + "Z",
        "source": None,
        "artist": None,
        "album": None,
        "genre": None,
        "duration": None,
        "bitrate": None
    }

def scan_catalog() -> list:
    entries = []
    for root, _, files in os.walk(CATALOG_DIR):
        for fname in files:
            if fname == "manifest.json":
                continue
            fpath = Path(root) / fname
            entries.append(get_file_metadata(fpath))
    return entries

def generate_manifest():
    catalog_entries = scan_catalog()
    manifest = {
        "manifest_version": 1,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "catalog": catalog_entries
    }
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    return manifest

if __name__ == "__main__":
    manifest = generate_manifest()
    print(f"Manifest generated with {len(manifest['catalog'])} entries at {MANIFEST_PATH}")
