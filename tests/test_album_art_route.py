"""
Tests for the /art album-art route in musician_training_ui.

Covers:
  1. Real audio file with embedded art  -> 200 + image bytes
  2. Real audio file with no art        -> 204
  3. Corrupt / unreadable file          -> 204  (no crash)
  4. Path traversal attempt             -> 403
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import training.musician_training_ui as ui_mod
from training.musician_training_ui import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tiny_jpeg() -> bytes:
    return bytes([
        0xFF,0xD8,0xFF,0xE0,0x00,0x10,0x4A,0x46,0x49,0x46,0x00,0x01,
        0x01,0x00,0x00,0x01,0x00,0x01,0x00,0x00,0xFF,0xDB,0x00,0x43,
        0x00,0x08,0x06,0x06,0x07,0x06,0x05,0x08,0x07,0x07,0x07,0x09,
        0x09,0x08,0x0A,0x0C,0x14,0x0D,0x0C,0x0B,0x0B,0x0C,0x19,0x12,
        0x13,0x0F,0x14,0x1D,0x1A,0x1F,0x1E,0x1D,0x1A,0x1C,0x1C,0x20,
        0x24,0x2E,0x27,0x20,0x22,0x2C,0x23,0x1C,0x1C,0x28,0x37,0x29,
        0x2C,0x30,0x31,0x34,0x34,0x34,0x1F,0x27,0x39,0x3D,0x38,0x32,
        0x3C,0x2E,0x33,0x34,0x32,0xFF,0xC0,0x00,0x0B,0x08,0x00,0x01,
        0x00,0x01,0x01,0x01,0x11,0x00,0xFF,0xC4,0x00,0x1F,0x00,0x00,
        0x01,0x05,0x01,0x01,0x01,0x01,0x01,0x01,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x01,0x02,0x03,0x04,0x05,0x06,0x07,0x08,
        0x09,0x0A,0x0B,0xFF,0xDA,0x00,0x08,0x01,0x01,0x00,0x00,0x3F,
        0x00,0xFB,0xD7,0xFF,0xD9,
    ])


def _make_apic_mock(jpeg: bytes) -> MagicMock:
    apic = MagicMock()
    apic.data = jpeg
    apic.mime = "image/jpeg"
    tags = MagicMock()
    tags.keys.return_value = ["APIC:Cover"]
    tags.__getitem__ = MagicMock(return_value=apic)
    tags.get.return_value = None
    audio = MagicMock()
    audio.tags = tags
    audio.pictures = []
    return audio


def _make_no_art_mock() -> MagicMock:
    tags = MagicMock()
    tags.keys.return_value = ["TIT2", "TPE1"]
    tags.get.return_value = None
    audio = MagicMock()
    audio.tags = tags
    audio.pictures = []
    return audio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_mod, "_ART_ALLOWED_ROOTS", (tmp_path.resolve(),))
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c, tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAlbumArtRoute:

    def test_art_with_embedded_art_returns_200(self, client):
        """/art on a file with APIC tag -> 200 + image bytes."""
        c, tmp = client
        jpeg = _tiny_jpeg()
        audio_file = tmp / "track.mp3"
        audio_file.write_bytes(b"placeholder")
        with patch("mutagen.File", return_value=_make_apic_mock(jpeg)):
            resp = c.get(f"/art?path={audio_file}")
        assert resp.status_code == 200
        assert resp.data == jpeg
        assert resp.content_type.startswith("image/")

    def test_art_no_embedded_art_returns_204(self, client):
        """/art on a file with no art -> 204."""
        c, tmp = client
        audio_file = tmp / "no_art.mp3"
        audio_file.write_bytes(b"placeholder")
        with patch("mutagen.File", return_value=_make_no_art_mock()):
            resp = c.get(f"/art?path={audio_file}")
        assert resp.status_code == 204

    def test_art_corrupt_file_returns_204(self, client):
        """/art when mutagen raises -> 204, no crash."""
        c, tmp = client
        audio_file = tmp / "corrupt.mp3"
        audio_file.write_bytes(b"JUNK")
        with patch("mutagen.File", side_effect=Exception("corrupt")):
            resp = c.get(f"/art?path={audio_file}")
        assert resp.status_code == 204

    def test_art_path_traversal_returns_403(self, client):
        """/art with path traversal -> 403."""
        c, _ = client
        resp = c.get("/art?path=../../etc/passwd")
        assert resp.status_code == 403

    def test_art_empty_path_returns_204(self, client):
        """/art with no path param -> 204."""
        c, _ = client
        resp = c.get("/art")
        assert resp.status_code == 204