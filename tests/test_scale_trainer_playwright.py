"""Playwright regression test for FR-20260808-scale-trainer-flyio-deploy.

Reproduces + guards against the production bug found on the live Fly.io deploy
(ENABLE_EXERCISE_CARDS=false, ENABLE_SCALE_LOG=false): a top-level
`document.getElementById('catalog-list').addEventListener(...)` statement threw
`TypeError: Cannot read properties of null (reading 'addEventListener')` because
`catalog-list` only exists inside the exercise-cards tab panel. Being a
synchronous top-level statement (not inside a function), the throw halted every
later statement in the same <script> tag -- including the `initScales()` IIFE --
so the fretboard never rendered and clicking the Scales tab threw
`ReferenceError: switchTab is not defined`.

Requires pytest-playwright (already installed) and PLAYWRIGHT_ENABLED=1 to run
(see tests/conftest.py's pytest_collection_modifyitems). Starts a real Flask dev
server on a free port in a background thread -- same live-server pattern as
test_band_mgmt_http_file_serve.py's `live_server` fixture -- with
ENABLE_EXERCISE_CARDS=false / ENABLE_SCALE_LOG=false (the exact flag combination
from the live bug report), then drives it with Playwright (same browser/page
fixture pattern as test_band_mgmt_playwright.py) and the flag-reload pattern
from test_scale_trainer_feature_flags.py's `_app_with_flags`.

Run: $env:PLAYWRIGHT_ENABLED="1"; C:\\G\\python.exe -m pytest tests/test_scale_trainer_playwright.py -v
"""
from __future__ import annotations

import importlib
import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import training.musician_training_ui as ui  # noqa: E402

pytestmark = pytest.mark.playwright

_FLAG_VARS = ("ENABLE_EXERCISE_CARDS", "ENABLE_SCALE_LOG")


def _find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(port: int, retries: int = 30) -> bool:
    for _ in range(retries):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
            return True
        except Exception:
            time.sleep(0.2)
    return False


@pytest.fixture(scope="module")
def live_server():
    """Reload musician_training_ui with both feature flags disabled (the exact
    scenario from the live Fly.io bug report) and serve it for real over HTTP in
    a background thread, so Playwright observes genuine page-load/console
    behavior instead of Flask's mocked test_client().
    """
    saved = {k: os.environ.get(k) for k in _FLAG_VARS}
    os.environ["ENABLE_EXERCISE_CARDS"] = "false"
    os.environ["ENABLE_SCALE_LOG"] = "false"
    importlib.reload(ui)

    port = _find_free_port()
    thread = threading.Thread(
        target=lambda: ui.app.run(host="127.0.0.1", port=port, use_reloader=False, threaded=True, debug=False),
        daemon=True,
    )
    thread.start()

    started = _wait_for_server(port)

    yield {"port": port, "started": started}

    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    importlib.reload(ui)


@pytest.fixture(scope="module")
def browser():
    """Launch a Chromium browser for the test module."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture()
def page_with_console_errors(browser):
    """A fresh page per test, wired to collect console `error` messages and
    uncaught page errors (e.g. the top-level TypeError this FR fixes)."""
    page = browser.new_page()
    errors: list[str] = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    yield page, errors
    page.close()


def test_no_console_errors_on_load_with_exercise_cards_disabled(live_server, page_with_console_errors):
    """Regression test for the catalog-list null-deref (FR-20260808).

    Before the fix: loading '/' with ENABLE_EXERCISE_CARDS=false threw
    `TypeError: Cannot read properties of null (reading 'addEventListener')`
    synchronously during page load.
    """
    if not live_server["started"]:
        pytest.skip("Local Flask server did not start in time")
    page, errors = page_with_console_errors

    page.goto(f"http://127.0.0.1:{live_server['port']}/")
    page.wait_for_load_state("networkidle")

    assert errors == [], f"Console/page errors on load: {errors}"


def test_fretboard_renders_after_clicking_scales_tab(live_server, page_with_console_errors):
    """Regression test for the fretboard staying stuck on 'Loading fretboard...'.

    Before the fix: the top-level TypeError halted every later statement in the
    <script> tag, so the `initScales()` IIFE never ran and `window.switchTab`
    was never defined -- clicking the (always-present) Scales tab button threw
    `ReferenceError: switchTab is not defined` and the fretboard never rendered.
    """
    if not live_server["started"]:
        pytest.skip("Local Flask server did not start in time")
    page, errors = page_with_console_errors

    page.goto(f"http://127.0.0.1:{live_server['port']}/")
    page.click("#tab-btn-scales")
    page.wait_for_function(
        "() => !document.getElementById('fretboard-svg').textContent.includes('Loading fretboard')"
    )

    fretboard_html = page.eval_on_selector("#fretboard-svg", "el => el.innerHTML")
    assert "Loading fretboard" not in fretboard_html
    assert "<circle" in fretboard_html, "Expected fretboard note dots to be drawn"

    assert errors == [], f"Console/page errors after interaction: {errors}"


def test_scales_populate_on_initial_load_without_clicking_tab(live_server, page_with_console_errors):
    """Regression test for the init-load bug (FR-20260808, 2nd live bug).

    ENABLE_EXERCISE_CARDS=false pre-renders the Scales tab as active
    server-side (Jinja conditional CSS class), but nothing ever called the
    `switchTab('scales')` JS function on page load -- so `loadScalePositions`
    never fired, the Position <select> stayed empty, and the fretboard stayed
    stuck on "Loading fretboard..." forever. This test does NOT click the
    Scales tab button (unlike test_fretboard_renders_after_clicking_scales_tab
    above) -- it only loads '/' and waits, to reproduce the exact production
    report: zero /api/scale-positions requests fire on page load.
    """
    if not live_server["started"]:
        pytest.skip("Local Flask server did not start in time")
    page, errors = page_with_console_errors

    page.goto(f"http://127.0.0.1:{live_server['port']}/")
    page.wait_for_function(
        "() => document.getElementById('scale-position').options.length > 0"
    )

    fretboard_html = page.eval_on_selector("#fretboard-svg", "el => el.innerHTML")
    assert "Loading fretboard" not in fretboard_html

    option_count = page.eval_on_selector("#scale-position", "el => el.options.length")
    assert option_count > 0, "Position <select> should be populated on initial load"

    assert errors == [], f"Console/page errors on load: {errors}"
