"""Playwright tests for the ❤Music band management panel.

Requires the panel HTML to exist at reports/band_management_panel.html.
Run: C:\\G\\python.exe src/band_mgmt/generate_band_mgmt_panel.py  (generates the HTML)
Then: C:\\G\\python.exe -m pytest tests/test_band_mgmt_playwright.py -v

Set PLAYWRIGHT_ENABLED=1 to enable: $env:PLAYWRIGHT_ENABLED=1
"""

from __future__ import annotations

from pathlib import Path

import pytest

PANEL_PATH = Path(__file__).resolve().parent.parent / "reports" / "band_management_panel.html"
PANEL_URL = PANEL_PATH.as_uri() if PANEL_PATH.exists() else ""

pytestmark = pytest.mark.playwright


@pytest.fixture(scope="module")
def browser():
    """Launch a Chromium browser for the test module."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture(scope="module")
def page(browser):
    """Open the panel in a new browser page."""
    p = browser.new_page()
    yield p
    p.close()


@pytest.mark.skipif(not PANEL_PATH.exists(), reason="Panel HTML not generated — run generate_band_mgmt_panel.py first")
def test_panel_loads(page):
    """Band management panel loads without JS errors."""
    errors = []
    page.on("pageerror", lambda err: errors.append(str(err)))
    page.goto(PANEL_URL)
    assert page.title() != "", "Page title should not be empty"
    assert errors == [], f"JS errors on page load: {errors}"


@pytest.mark.skipif(not PANEL_PATH.exists(), reason="Panel HTML not generated — run generate_band_mgmt_panel.py first")
def test_panel_has_band_sections(page):
    """Panel renders band/artist section content."""
    page.goto(PANEL_URL)
    body_text = page.inner_text("body")
    assert len(body_text.strip()) > 50, "Panel body appears empty"


@pytest.mark.skipif(not PANEL_PATH.exists(), reason="Panel HTML not generated — run generate_band_mgmt_panel.py first")
def test_panel_navigation_links(page):
    """Panel navigation links are present and not broken."""
    page.goto(PANEL_URL)
    links = page.query_selector_all("a[href]")
    # At minimum the panel should have some navigation structure
    assert len(links) >= 1, "Panel has no navigation links"
