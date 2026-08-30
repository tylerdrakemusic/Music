"""❤Music test configuration."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC = _REPO_ROOT / "src"
_CI_ITEMS = {}
_CI_SKIPS = []
_CI_DESELECTED = []
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
    _CI_ITEMS.clear()
    _CI_ITEMS.update({item.nodeid: item for item in items})
    _CI_SKIPS.clear()
    _CI_DESELECTED.clear()
    if os.getenv("PLAYWRIGHT_ENABLED") != "1":
        skip = pytest.mark.skip(reason="Set PLAYWRIGHT_ENABLED=1 to run Playwright tests")
        for item in items:
            if item.get_closest_marker("playwright"):
                item.add_marker(skip)


def pytest_runtest_logreport(report):
    """Collect skip reasons so CI cannot silently lose runnable coverage."""
    if not report.skipped:
        return

    item = _CI_ITEMS.get(report.nodeid)
    if item is None:
        return
    reason = str(report.longrepr[2]) if isinstance(report.longrepr, tuple) else str(report.longrepr)
    _CI_SKIPS.append((report.nodeid, reason, item.get_closest_marker("ci_unavailable") is not None))


def pytest_deselected(items):
    """Collect deselected node IDs so CI cannot silently lose coverage."""
    _CI_DESELECTED.extend(item.nodeid for item in items)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Report classified skips and fail CI for any unclassified skip."""
    skips = _CI_SKIPS
    deselected = _CI_DESELECTED
    if not skips and not deselected:
        return

    terminalreporter.write_sep("=", "CI skip policy")
    terminalreporter.write_line(f"Total skips: {len(skips)}")
    for nodeid, reason, classified in skips:
        label = "classified unavailable infrastructure" if classified else "UNCLASSIFIED"
        terminalreporter.write_line(f"{label}: {nodeid} ({reason})")
    terminalreporter.write_line(f"Total deselected: {len(deselected)}")
    if any(not classified for _, _, classified in skips):
        terminalreporter.write_line("Unclassified skips are not allowed in CI.")
        config._ci_skip_policy_failed = True


def pytest_sessionfinish(session, exitstatus):
    """Turn unclassified skips into a blocking CI result."""
    if getattr(session.config, "_ci_skip_policy_failed", False):
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
