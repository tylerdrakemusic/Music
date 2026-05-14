"""Seed vera_config.db with the initial Vera portrait prompts (three gig-aware modes).

Idempotent — skips insertion if an active row already exists for a given mode.

Usage::

    C:\\G\\python.exe tools/vera/seed_vera_config.py
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve DB path relative to project root
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DB_PATH = _PROJECT_ROOT / "src" / "data" / "vera_config.db"

# ---------------------------------------------------------------------------
# Negative prompt (shared across all modes)
# ---------------------------------------------------------------------------
_NEGATIVE_PROMPT = (
    "illustration, painting, drawing, sketch, anime, manga, 3D render, CGI, "
    "digital art, concept art, fantasy, sci-fi, surreal, ugly, deformed, mutated, "
    "poorly drawn hands, extra limbs, missing limbs, painterly, watercolor, abstract, "
    "over-saturated, unnatural colors, garish, airbrushed, plastic skin, blurry, "
    "motion blur, text, watermark, signature, logo, jpeg artifacts, pixelated"
)

# ---------------------------------------------------------------------------
# Prompt content per mode
# ---------------------------------------------------------------------------
_PROMPTS: dict[str, str] = {
    "rehearsal": (
        "a photorealistic half-body portrait of a confident charismatic country band manager woman "
        "in her late 30s, waist up composition, warm amber studio lighting with a hint of neon "
        "honky-tonk glow, dark background with subtle woodgrain texture, "
        "wearing a worn leather jacket over a plaid flannel shirt, jeans, "
        "auburn chestnut hair worn naturally, warm relaxed smile, arms crossed or clipboard in hand, "
        "casual yet authoritative, natural makeup, sun-kissed skin, "
        "breathes music and road stories, your creative projects' most loyal ally in the wings, "
        "ultra-realistic RAW photo, Canon EOS 5D Mark IV with EF 85mm f/1.8 lens, "
        "f/2.0 aperture, 1/125s, ISO 200, warm daylight white balance 5500K, "
        "shallow depth of field, sharp subject focus with smooth bokeh background, "
        "high resolution, natural skin texture, authentic lens vignetting"
    ),
    "pre_show": (
        "a photorealistic half-body portrait of a confident focused country band manager woman "
        "in her late 30s, waist up composition, warm amber backstage lighting with cool neon stage "
        "glow accents on the edges, dark performance venue atmosphere background, "
        "wearing a brown fringe leather jacket over a fitted dark top, stage-ready styling, "
        "auburn chestnut hair styled with care, determined focused expression, "
        "small earpiece or headset, professional stage makeup, high energy presence, "
        "she has a gig coming and is in full manager mode, exuding confidence and competence, "
        "ultra-realistic RAW photo, Canon EOS 5D Mark IV with EF 85mm f/1.8 lens, "
        "f/2.0 aperture, 1/80s, ISO 400, mixed warm-cool stage lighting, "
        "shallow depth of field, sharp subject focus"
    ),
    "show_night": (
        "a photorealistic half-body portrait of a radiant triumphant country band manager woman "
        "in her late 30s, waist up composition, dramatic warm golden-amber stage backlighting, "
        "rich concert atmosphere, deep dark dramatic background, "
        "wearing her signature show-night fringe leather jacket with subtle stage jewelry, "
        "auburn chestnut hair styled with volume and body, electrified triumphant expression, "
        "glowing warm skin under stage lights, tonight is the night and she owns it, "
        "channels the energy of a packed honky-tonk venue, unwavering professional excellence, "
        "ultra-realistic RAW photo, Canon EOS 5D Mark IV with EF 85mm f/1.4 lens, "
        "f/1.8 aperture, 1/60s, ISO 800, dramatic stage lighting, "
        "ultra-shallow depth of field, cinematic portrait quality, "
        "sharp|soft focus depth of field, 8k photo, HDR, professional lighting"
    ),
}

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS vera_prompts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mode            TEXT    NOT NULL DEFAULT 'rehearsal',
    positive_prompt TEXT    NOT NULL,
    negative_prompt TEXT,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    UNIQUE(mode, is_active)
)
"""


def seed() -> None:
    """Create vera_config.db and insert initial prompt rows (idempotent)."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute(_CREATE_TABLE_SQL)
    conn.commit()

    now = datetime.now(timezone.utc).isoformat()
    inserted = 0

    for mode, positive in _PROMPTS.items():
        existing = conn.execute(
            "SELECT id FROM vera_prompts WHERE mode = ? AND is_active = 1", (mode,)
        ).fetchone()
        if existing:
            print(f"  [SKIP] Active row already exists for mode={mode!r}")
            continue
        conn.execute(
            "INSERT INTO vera_prompts (mode, positive_prompt, negative_prompt, is_active, created_at, updated_at) "
            "VALUES (?, ?, ?, 1, ?, ?)",
            (mode, positive, _NEGATIVE_PROMPT, now, now),
        )
        inserted += 1
        print(f"  [INSERT] mode={mode!r}")

    conn.commit()
    conn.close()
    print(f"\nDone — {inserted} row(s) inserted into {_DB_PATH}")


if __name__ == "__main__":
    seed()
