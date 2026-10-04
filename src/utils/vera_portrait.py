"""Vera portrait generator — gig-aware AI-generated portrait for the Band Management panel.

Generates a half-body portrait of "Vera" (the Band Management AI persona) using
the shared portrait cascade with a local SVG silhouette fallback.

Vera has three gig-aware looks driven by the active setlist's gig_date in heartmusic.db:
    - rehearsal   : no gig within 14 days (casual, leather jacket + flannel)
    - pre_show    : gig within 14 days    (styled, fringe leather + headset)
    - show_night  : gig is today           (full stage look, dramatic lighting)

The portrait is cached per calendar-date + mode so it is generated at most once per
day per mode. Up to 3 dated portraits are kept; older ones are pruned automatically.

Usage::

    from src.utils.vera_portrait import get_daily_portrait, get_portrait_img_tag

    path = get_daily_portrait()           # Path to cached PNG (or SVG fallback)
    tag  = get_portrait_img_tag(max_width=160)   # <img> data-URI tag
"""

from __future__ import annotations

import base64
import importlib.util
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from types import ModuleType

# ---------------------------------------------------------------------------
# Workspace integration path bootstrap
# ---------------------------------------------------------------------------
_WORKSPACE_ROOT = Path(r"f:\⊕Workspace")


def _load_workspace_cascade() -> ModuleType | None:
    """Load the shared image cascade with its sibling providers available."""
    module_key = "_ws_integrations_image_cascade"
    if module_key in sys.modules:
        return sys.modules[module_key]
    file_path = _WORKSPACE_ROOT / "src" / "integrations" / "image_cascade.py"
    spec = importlib.util.spec_from_file_location(
        module_key,
        file_path,
        submodule_search_locations=[str(file_path.parent)],
    )
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_key] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        del sys.modules[module_key]
        return None
    return module


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_IMAGE_CACHE_DIR = _PROJECT_ROOT / "output" / "images"
_DB_PATH = _PROJECT_ROOT / "src" / "data" / "heartmusic.db"
_MAX_CACHED_PORTRAITS = 3

# ---------------------------------------------------------------------------
# Gig awareness — threshold in days before mode switches to pre_show
# ---------------------------------------------------------------------------
_PRE_SHOW_DAYS = 14


def _get_gig_mode() -> str:
    """Determine Vera's current gig-awareness mode.

    Reads the active setlist's gig_date from heartmusic.db.

    Returns
    -------
    str
        'show_night'  if gig_date is today,
        'pre_show'    if gig is within _PRE_SHOW_DAYS days,
        'rehearsal'   otherwise (or if DB is unavailable / no active setlist).
    """
    try:
        if not _DB_PATH.exists():
            return "rehearsal"
        conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT gig_date FROM setlists WHERE active = 1 AND gig_date IS NOT NULL "
            "ORDER BY gig_date ASC LIMIT 1"
        ).fetchone()
        conn.close()
        if row is None:
            return "rehearsal"
        gig_date = date.fromisoformat(str(row["gig_date"]))
        today = date.today()
        delta = (gig_date - today).days
        if delta == 0:
            return "show_night"
        if 0 < delta <= _PRE_SHOW_DAYS:
            return "pre_show"
        return "rehearsal"
    except Exception:
        return "rehearsal"


# ---------------------------------------------------------------------------
# Fallback prompts (used when DB is unavailable)
# ---------------------------------------------------------------------------
_FALLBACK_PROMPTS: dict[str, str] = {
    "rehearsal": (
        "A photorealistic half-body portrait of a confident, charismatic country band manager "
        "woman in her late 30s, waist up. Warm amber studio lighting with a hint of neon "
        "honky-tonk glow, dark background with subtle woodgrain texture. "
        "Wearing a worn leather jacket over a plaid flannel shirt, jeans. "
        "Auburn chestnut hair, warm relaxed smile, arms crossed or clipboard in hand. "
        "Casual yet authoritative. Natural makeup, sun-kissed skin. "
        "Canon EOS 5D Mark IV, f/2.0, shallow depth of field, sharp subject focus."
    ),
    "pre_show": (
        "A photorealistic half-body portrait of a confident, focused country band manager "
        "woman in her late 30s, waist up. Warm amber backstage lighting with cool neon stage "
        "glow accents on the edges, dark performance venue background. "
        "Wearing a fringe leather jacket over a fitted dark top, stage-ready styling. "
        "Auburn chestnut hair styled with care, determined expression, small headset or earpiece. "
        "Professional makeup, energized presence. "
        "Canon EOS 5D Mark IV, f/2.0, shallow depth of field."
    ),
    "show_night": (
        "A photorealistic half-body portrait of a radiant, triumphant country band manager "
        "woman in her late 30s, waist up. Dramatic warm golden-amber stage backlighting, "
        "rich concert atmosphere, deep dark background. "
        "Wearing her signature show-night fringe leather jacket with stage jewelry. "
        "Auburn chestnut hair styled with volume, electrified triumphant expression, glowing "
        "warm skin under stage lights. "
        "Canon EOS 5D Mark IV, f/1.8, ultra-shallow depth of field."
    ),
}

_NEGATIVE_PROMPT = (
    "illustration, painting, drawing, sketch, anime, manga, 3D render, CGI, "
    "digital art, concept art, fantasy, sci-fi, surreal, ugly, deformed, mutated, "
    "poorly drawn hands, extra limbs, missing limbs, painterly, watercolor, abstract, "
    "over-saturated, unnatural colors, garish, airbrushed, plastic skin, blurry, "
    "motion blur, text, watermark, signature, logo, jpeg artifacts, pixelated"
)

# Inline SVG fallback (monochrome silhouette)
_SVG_FALLBACK_B64 = base64.b64encode(
    b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 260" width="200" height="260">
  <rect width="200" height="260" fill="#1a1208"/>
  <circle cx="100" cy="75" r="40" fill="#5c3d1a"/>
  <ellipse cx="100" cy="195" rx="65" ry="75" fill="#5c3d1a"/>
  <text x="100" y="255" text-anchor="middle" fill="#c9a96e" font-size="11" font-family="sans-serif">Vera</text>
</svg>"""
).decode("ascii")


def _today_cache_path(mode: str) -> Path:
    """Return the expected cache path for today's portrait given a mode."""
    today = date.today().isoformat()
    return _IMAGE_CACHE_DIR / f"vera_portrait_{today}_{mode}.png"


def _today_svg_cache_path(mode: str) -> Path:
    """Return the expected SVG fallback path for today's portrait mode."""
    today = date.today().isoformat()
    return _IMAGE_CACHE_DIR / f"vera_portrait_{today}_{mode}.svg"


def _prune_old_portraits(mode: str) -> None:
    """Keep the most recent cached Vera portraits for one mode."""
    portraits = sorted(
        (
            path
            for path in _IMAGE_CACHE_DIR.glob("vera_portrait_*_*")
            if path.suffix.lower() in {".png", ".svg"}
            and path.stem.endswith(f"_{mode}")
        ),
        reverse=True,
    )
    for old in portraits[_MAX_CACHED_PORTRAITS:]:
        try:
            old.unlink()
        except OSError:
            pass


def _build_prompt(mode: str) -> tuple[str, str | None]:
    """Build the portrait prompt for the given mode, preferring the DB active row.

    Returns
    -------
    tuple[str, str | None]
        (positive_prompt, negative_prompt).
    """
    try:
        import importlib.util as _ilu
        import sys as _sys
        _db_mod_key = "_vera_config_db"
        if _db_mod_key not in _sys.modules:
            _db_path = Path(__file__).resolve().parent / "vera_config_db.py"
            _spec = _ilu.spec_from_file_location(_db_mod_key, _db_path)
            if _spec and _spec.loader:
                _mod = _ilu.module_from_spec(_spec)
                _sys.modules[_db_mod_key] = _mod
                _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
        _db_mod = _sys.modules.get(_db_mod_key)
        if _db_mod is not None:
            positive, negative = _db_mod.get_active_prompt(mode)
            return positive, negative
    except Exception:  # nosec B110
        pass

    # Fallback: built-in prompt for this mode
    return _FALLBACK_PROMPTS.get(mode, _FALLBACK_PROMPTS["rehearsal"]), _NEGATIVE_PROMPT


def _svg_fallback_path(mode: str) -> Path:
    """Write inline SVG to a dated .svg file and return its path."""
    _IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    svg_path = _IMAGE_CACHE_DIR / f"vera_portrait_{today}_{mode}.svg"
    svg_data = base64.b64decode(_SVG_FALLBACK_B64)
    svg_path.write_bytes(svg_data)
    return svg_path


def get_daily_portrait(mode: str | None = None) -> Path:
    """Return the path to today's Vera portrait.

    Return a per-mode cached result or use the shared portrait cascade with
    the local SVG silhouette as its final fallback.

    Parameters
    ----------
    mode:
        Override the gig-awareness mode. If None, auto-detects from heartmusic.db.

    Returns
    -------
    Path
        Absolute path to the portrait file. Never raises.
    """
    _IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if mode is None:
        mode = _get_gig_mode()

    today_path = _today_cache_path(mode)
    if today_path.exists():
        return today_path
    today_svg_path = _today_svg_cache_path(mode)
    if today_svg_path.exists():
        return today_svg_path

    positive_prompt, negative_prompt = _build_prompt(mode)
    save_dir = _IMAGE_CACHE_DIR

    fallback_svg = _svg_fallback_path(mode)
    try:
        module = _load_workspace_cascade()
        if module is None:
            _prune_old_portraits(mode)
            return fallback_svg
        cascade = module.portrait_image_cascade(fallback_svg)
        result = cascade.generate(
            positive_prompt,
            output_dir=save_dir,
            negative_prompt=negative_prompt,
        )
    except Exception:
        _prune_old_portraits(mode)
        return fallback_svg

    result_path = Path(result.path)
    if result_path.suffix.lower() == ".svg":
        _prune_old_portraits(mode)
        return result_path
    if result_path != today_path:
        result_path.replace(today_path)
    if fallback_svg != result_path and fallback_svg.exists():
        fallback_svg.unlink()
    _prune_old_portraits(mode)
    return today_path


def get_portrait_img_tag(max_width: int = 160, mode: str | None = None) -> str:
    """Return an ``<img>`` HTML tag for the Vera portrait.

    Uses a data-URI so the HTML file is self-contained. Falls back to an
    inline SVG data-URI if the portrait is an SVG silhouette.

    Parameters
    ----------
    max_width:
        CSS max-width in pixels. Default: 160.
    mode:
        Override gig-awareness mode. If None, auto-detects from heartmusic.db.
    """
    if mode is None:
        mode = _get_gig_mode()

    portrait_path = get_daily_portrait(mode)
    suffix = portrait_path.suffix.lower()

    mode_labels = {
        "rehearsal": "Rehearsal",
        "pre_show": "Pre-Show",
        "show_night": "Show Night",
    }
    mode_label = mode_labels.get(mode, mode)

    if suffix == ".png":
        mime = "image/png"
        data = base64.b64encode(portrait_path.read_bytes()).decode("ascii")
        src = f"data:{mime};base64,{data}"
    elif suffix == ".svg":
        src = f"data:image/svg+xml;base64,{_SVG_FALLBACK_B64}"
    else:
        src = f"data:image/svg+xml;base64,{_SVG_FALLBACK_B64}"

    return (
        f'<img src="{src}" alt="Vera — Band Manager · {mode_label}" '
        f'style="max-width:{max_width}px; width:{max_width}px; height:{max_width}px; '
        f'object-fit:cover; border-radius:12px; '
        f'border:2px solid rgba(201,169,110,0.45); display:block; margin:0 auto;" '
        f'title="Vera · {mode_label} · {date.today().isoformat()}" />'
    )
