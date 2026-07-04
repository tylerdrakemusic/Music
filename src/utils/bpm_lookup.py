"""GetSongBPM API client for automated BPM lookup.
FR-20260703-music-bpm-autolookup

Queries https://api.getsongbpm.com for a song's tempo by title + artist,
replacing Tyler's manual BPM entry in the ❤music-chord-sheets workflow.

Security: the API key is read exclusively from the `GETSONGBPM_API_KEY`
environment variable at call time. It is never hardcoded, logged, or written
to any file (see f:\\⊕Workspace\\.github\\instructions\\db-api-keys.instructions.md).

On any failure or no-match (missing key, HTTP error, timeout, malformed
response, empty result set, missing tempo field) this module returns `None`
rather than raising, so callers can gracefully fall back to manual entry.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import requests

API_BASE_URL = "https://api.getsongbpm.com/search/"
DEFAULT_TIMEOUT = 10.0


@dataclass
class BpmResult:
    """A successful automated BPM match."""

    bpm: float
    title: str
    artist: str
    source: str = "getsongbpm"


def lookup_bpm(title: str, artist: str, timeout: float = DEFAULT_TIMEOUT) -> Optional[BpmResult]:
    """Look up a song's BPM via the GetSongBPM API.

    Returns a `BpmResult` on a confident match, or `None` on any failure or
    no-match condition (missing API key, HTTP error, timeout, malformed
    response, empty results, or a result with no tempo field). Never raises.
    """
    api_key = os.environ.get("GETSONGBPM_API_KEY")
    if not api_key:
        return None

    params = {
        "api_key": api_key,
        "type": "both",
        "lookup": f"song:{title} artist:{artist}",
    }

    try:
        response = requests.get(API_BASE_URL, params=params, timeout=timeout)
    except requests.RequestException:
        return None

    if response.status_code != 200:
        return None

    try:
        data = response.json()
    except ValueError:
        return None

    results = data.get("search") if isinstance(data, dict) else None
    if not results:
        return None

    match = results[0]
    tempo = match.get("tempo")
    if tempo is None:
        return None

    try:
        bpm_value = float(tempo)
    except (TypeError, ValueError):
        return None

    return BpmResult(bpm=bpm_value, title=match.get("title", title), artist=artist)
