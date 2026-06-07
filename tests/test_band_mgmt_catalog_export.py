from __future__ import annotations

from pathlib import Path

import pytest

PANEL_PATH = Path(__file__).resolve().parent.parent / "reports" / "band_management_panel.html"

@pytest.mark.skipif(not PANEL_PATH.exists(), reason="Panel HTML not generated")
def test_catalog_export_button_is_present():
    html = PANEL_PATH.read_text(encoding="utf-8")
    assert 'id="bm-export-html-btn"' in html
    assert 'bmExportCatalogHtml()' in html
    assert 'Export Catalog' in html
    assert 'sortTableBy(' in html
    assert 'songs in catalog' in html
