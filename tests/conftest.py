"""❤Music test configuration."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC = _REPO_ROOT / "src"
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _is_repo_module(module: object) -> bool:
    """Return True when a loaded module comes from the repository src path."""
    file_path = getattr(module, "__file__", None)
    if file_path is not None:
        return Path(file_path).resolve().is_relative_to(_SRC.resolve())
    module_path = getattr(module, "__path__", None)
    if module_path is not None:
        return any(Path(p).resolve().is_relative_to(_SRC.resolve()) for p in module_path)
    return False


for _module_name in (
    "training",
    "training.musician_training_ui",
    "training.scale_data",
    "training.scale_tts",
    "training.practice_stats",
):
    if _module_name in sys.modules:
        module = sys.modules[_module_name]
        if not _is_repo_module(module):
            del sys.modules[_module_name]


def pytest_collection_modifyitems(config, items):
    """Skip playwright-marked tests unless PLAYWRIGHT_ENABLED=1 is set."""
    if os.getenv("PLAYWRIGHT_ENABLED") != "1":
        skip = pytest.mark.skip(reason="Set PLAYWRIGHT_ENABLED=1 to run Playwright tests")
        for item in items:
            if item.get_closest_marker("playwright"):
                item.add_marker(skip)
