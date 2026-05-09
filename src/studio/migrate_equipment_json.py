"""Migrate studio_equipment.json into the heartmusic.db studio_equipment table.

Run standalone:
    C:\\G\\python.exe src/studio/migrate_equipment_json.py

Idempotent — checks if data is already seeded before inserting.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.init_db import get_connection  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
JSON_PATH = ROOT / "studio_master" / "studio_equipment.json"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS studio_equipment (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    studio_name TEXT NOT NULL,
    category    TEXT NOT NULL,
    label       TEXT NOT NULL,
    spec_json   TEXT NOT NULL DEFAULT '{}',
    status      TEXT NOT NULL DEFAULT 'active',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# Key-prefix → category mapping (matched against the equipment dict key)
# All categories use lowercase_underscore plural to match HyperThreat convention.
_KEY_CATEGORY = {
    "guitar_pedals": "pedals",          # special: nested dict
    "microphone": "microphones",
    "audio_interface": "audio_interfaces",
    "studio_monitors": "monitors",
    "pa_speakers": "pa_speakers",
    "headphones": "headphones",
    "midi_controller": "midi_controllers",
    "amplifier": "amplifiers",
    "keyboard": "keyboards",
    "bass_guitar": "bass_guitars",
    "acoustic_guitar": "acoustic_guitars",
    "electric_drumset": "drums",
    "guitar": "guitars",
}


def _infer_category(key: str) -> str:
    """Infer equipment category from the dict key."""
    for prefix, cat in _KEY_CATEGORY.items():
        if key.lower().startswith(prefix):
            return cat
    return "Other"


def _infer_label(key: str, eq_data: dict) -> str:
    """Build a human-readable label: '{manufacturer} {model_name}' where available."""
    mfr = eq_data.get("manufacturer", "")
    model = eq_data.get("model_name", "")
    if mfr and model:
        return f"{mfr} {model}"
    if model:
        return model
    if mfr:
        return mfr
    # Some guitar entries nest make_and_model
    nested = eq_data.get("make_and_model", {})
    if isinstance(nested, dict):
        mfr = nested.get("manufacturer", "")
        model = nested.get("model_name", "")
        if mfr and model:
            return f"{mfr} {model}"
    return key.replace("_", " ").title()


def _build_spec_json(eq_data: dict) -> str:
    """Serialize equipment data as spec JSON, excluding serial_number as a top-level key."""
    if not isinstance(eq_data, dict):
        return "{}"
    # Keep all fields (including serial_number inside spec_json per FR spec)
    return json.dumps(eq_data, ensure_ascii=False)


def _collect_rows(studios: list) -> list[dict]:
    """Flatten studio_equipment.json into a list of row dicts."""
    rows = []
    for studio in studios:
        studio_name = studio.get("studio_name", "Unknown")
        equipment: dict = studio.get("equipment", {})

        for key, value in equipment.items():
            if key == "guitar_pedals" and isinstance(value, dict):
                # Each pedal key becomes a separate Pedal row
                for pedal_key, pedal_data in value.items():
                    if not isinstance(pedal_data, dict):
                        continue
                    label = _infer_label(pedal_key, pedal_data)
                    rows.append(
                        {
                            "studio_name": studio_name,
                            "category": "pedals",
                            "label": label,
                            "spec_json": _build_spec_json(pedal_data),
                            "status": "active",
                        }
                    )
            else:
                category = _infer_category(key)
                label = _infer_label(key, value if isinstance(value, dict) else {})
                spec = _build_spec_json(value if isinstance(value, dict) else {})
                rows.append(
                    {
                        "studio_name": studio_name,
                        "category": category,
                        "label": label,
                        "spec_json": spec,
                        "status": "active",
                    }
                )
    return rows


def migrate(conn=None) -> int:
    """Create table and seed rows. Returns number of rows inserted (0 if already seeded)."""
    close_after = conn is None
    if conn is None:
        conn = get_connection()

    try:
        conn.execute(CREATE_TABLE_SQL)
        conn.commit()

        # Idempotency check
        existing = conn.execute("SELECT COUNT(*) FROM studio_equipment").fetchone()[0]
        if existing > 0:
            print(f"Already seeded ({existing} rows). Skipping insert.")
            return 0

        with open(JSON_PATH, encoding="utf-8") as f:
            studios = json.load(f)

        rows = _collect_rows(studios)
        conn.executemany(
            """INSERT INTO studio_equipment (studio_name, category, label, spec_json, status)
               VALUES (:studio_name, :category, :label, :spec_json, :status)""",
            rows,
        )
        conn.commit()
        print(f"Inserted {len(rows)} equipment rows into studio_equipment.")
        return len(rows)
    finally:
        if close_after:
            conn.close()


if __name__ == "__main__":
    migrate()
