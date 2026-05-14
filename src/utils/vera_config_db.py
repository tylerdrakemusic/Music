"""Helper for reading and updating Vera's portrait prompts from vera_config.db.

Provides two public functions:
    get_active_prompt(mode)    -> (positive_prompt, negative_prompt | None)
    update_active_prompt(mode) -> None

The DB is created by tools/vera/seed_vera_config.py.  This module is import-safe
even if the DB does not yet exist — callers should catch RuntimeError.

Vera has three gig-aware prompt modes:
    'rehearsal'  — no gig within 14 days
    'pre_show'   — gig within 14 days
    'show_night' — gig is today
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_DB_PATH: Path = Path(__file__).resolve().parent.parent / "data" / "vera_config.db"

_VALID_MODES = ("rehearsal", "pre_show", "show_night")


def _connect() -> sqlite3.Connection:
    """Open a connection to vera_config.db (open/close per call for thread safety)."""
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_active_prompt(mode: str = "rehearsal") -> tuple[str, str | None]:
    """Return (positive_prompt, negative_prompt) for the given gig-awareness mode.

    Parameters
    ----------
    mode:
        One of 'rehearsal', 'pre_show', or 'show_night'.

    Returns
    -------
    tuple[str, str | None]
        (positive_prompt, negative_prompt).  ``negative_prompt`` may be None.

    Raises
    ------
    RuntimeError
        If the DB does not exist or no active row is present for the given mode.
    """
    if mode not in _VALID_MODES:
        mode = "rehearsal"
    if not _DB_PATH.exists():
        raise RuntimeError(
            f"vera_config.db not found at {_DB_PATH}. "
            "Run tools/vera/seed_vera_config.py to initialise."
        )
    with _connect() as conn:
        row = conn.execute(
            "SELECT positive_prompt, negative_prompt "
            "FROM vera_prompts WHERE mode = ? AND is_active = 1 ORDER BY id DESC LIMIT 1",
            (mode,),
        ).fetchone()
    if row is None:
        raise RuntimeError(
            f"No active prompt row found in vera_config.db for mode={mode!r}"
        )
    return str(row["positive_prompt"]), (row["negative_prompt"] or None)


def update_active_prompt(positive_prompt: str, mode: str = "rehearsal") -> None:
    """Update the active row's positive_prompt for the given mode.

    Parameters
    ----------
    positive_prompt:
        The new positive prompt text to store.
    mode:
        One of 'rehearsal', 'pre_show', or 'show_night'.

    Raises
    ------
    RuntimeError
        If the DB does not exist.
    """
    if mode not in _VALID_MODES:
        mode = "rehearsal"
    if not _DB_PATH.exists():
        raise RuntimeError(
            f"vera_config.db not found at {_DB_PATH}. "
            "Run tools/vera/seed_vera_config.py to initialise."
        )
    updated_at = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE vera_prompts SET positive_prompt = ?, updated_at = ? "
            "WHERE mode = ? AND is_active = 1",
            (positive_prompt, updated_at, mode),
        )
        conn.commit()
