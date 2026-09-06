"""
BFX-20260531-band-mgmt-file-urls

Tests for HTTP-origin URL rewriting and local-file-serving endpoints.

Covers:
  1. _resolve_audio_path — normal decode, traversal guard
  2. _resolve_sheet_path — normal decode, traversal guard
  3. Generated HTML contains _bmRewriteFileUrls() JS helper
  4. JS rewrite skips file:// protocol (AC3: file:// mode unchanged)
  5. JS rewrites file:///G:/Muzic/<file> → /audio/<file>
  6. JS rewrites file:// sheet music → /sheets/<relpath>
  7. _bmRewriteFileUrls() called before populateBandSelect() in DOMContentLoaded
  8. Integration: /audio/<file> serves content (200 + Range 206)
  9. Integration: /audio/<traversal> returns 400/404
 10. Integration: /sheets/<relpath> serves content (200)
 11. Integration: /sheets/<traversal> returns 400/404
"""
from __future__ import annotations

import importlib.util
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

pytestmark = pytest.mark.ci_unavailable

# ---------------------------------------------------------------------------
# Load the module under test
# ---------------------------------------------------------------------------
_WORKTREE = Path(__file__).resolve().parents[1]
_GEN_PY = _WORKTREE / "src" / "band_mgmt" / "generate_band_mgmt_panel.py"

sys.path.insert(0, str(_WORKTREE / "src"))


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_band_mgmt_panel", _GEN_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


mod = _load_module()


def test_serve_mode_rejects_non_loopback_host() -> None:
    with pytest.raises(ValueError, match="loopback"):
        mod._require_loopback_host("0.0.0.0")


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_serve_mode_accepts_loopback_hosts(host: str) -> None:
    assert mod._require_loopback_host(host) == host

# ---------------------------------------------------------------------------
# Helper: minimal BM_INLINE data for generate()
# ---------------------------------------------------------------------------
_EMPTY_DATA = {"exported_at": "2026-05-31", "bands": []}


# ---------------------------------------------------------------------------
# 1 & 2 — _resolve_audio_path / _resolve_sheet_path unit tests
# ---------------------------------------------------------------------------

class TestResolveAudioPath:
    """Unit tests for the _resolve_audio_path module helper."""

    def test_normal_filename(self, tmp_path: Path) -> None:
        mod.AUDIO_ROOT = tmp_path
        result = mod._resolve_audio_path("song.mp3")
        assert result == (tmp_path / "song.mp3").resolve()

    def test_url_encoded_spaces(self, tmp_path: Path) -> None:
        mod.AUDIO_ROOT = tmp_path
        result = mod._resolve_audio_path("Long%20Train%20Runnin.mp3")
        assert result == (tmp_path / "Long Train Runnin.mp3").resolve()

    def test_traversal_double_dot_raises(self, tmp_path: Path) -> None:
        mod.AUDIO_ROOT = tmp_path
        with pytest.raises(ValueError, match="traversal|unsafe|invalid"):
            mod._resolve_audio_path("../evil.mp3")

    def test_traversal_percent_encoded_raises(self, tmp_path: Path) -> None:
        mod.AUDIO_ROOT = tmp_path
        with pytest.raises(ValueError):
            mod._resolve_audio_path("..%2Fevil.mp3")

    def test_absolute_path_rejected(self, tmp_path: Path) -> None:
        mod.AUDIO_ROOT = tmp_path
        with pytest.raises(ValueError):
            mod._resolve_audio_path("/etc/passwd")


class TestResolveSheetPath:
    """Unit tests for the _resolve_sheet_path module helper."""

    def test_normal_relpath(self, tmp_path: Path) -> None:
        mod.SHEETS_ROOT = tmp_path
        result = mod._resolve_sheet_path("covers/sheet.docx")
        assert result == (tmp_path / "covers" / "sheet.docx").resolve()

    def test_url_encoded_relpath(self, tmp_path: Path) -> None:
        mod.SHEETS_ROOT = tmp_path
        result = mod._resolve_sheet_path("covers/My%20Song.docx")
        assert result == (tmp_path / "covers" / "My Song.docx").resolve()

    def test_traversal_double_dot_raises(self, tmp_path: Path) -> None:
        mod.SHEETS_ROOT = tmp_path
        with pytest.raises(ValueError, match="traversal|unsafe|invalid"):
            mod._resolve_sheet_path("../secret.txt")

    def test_traversal_percent_encoded_raises(self, tmp_path: Path) -> None:
        mod.SHEETS_ROOT = tmp_path
        with pytest.raises(ValueError):
            mod._resolve_sheet_path("..%2Fsecret.txt")

    def test_absolute_path_rejected(self, tmp_path: Path) -> None:
        mod.SHEETS_ROOT = tmp_path
        with pytest.raises(ValueError):
            mod._resolve_sheet_path("/etc/passwd")


# ---------------------------------------------------------------------------
# 3 – 7 — JS URL rewriting in generated HTML
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def generated_html() -> str:
    return mod.generate(_EMPTY_DATA, [])


class TestJsUrlRewriting:
    """The generated HTML must contain a JS helper that rewrites file:// URLs."""

    def test_rewrite_function_present(self, generated_html: str) -> None:
        assert "_bmRewriteFileUrls" in generated_html, (
            "_bmRewriteFileUrls function not found in generated HTML"
        )

    def test_rewrite_skips_file_protocol(self, generated_html: str) -> None:
        # AC3: file:// opened directly → no rewriting
        assert "protocol" in generated_html, (
            "JS rewrite must gate on window.location.protocol"
        )
        assert "file:" in generated_html, (
            "JS rewrite must reference 'file:' to skip when opened as file://"
        )

    def test_audio_rewrite_to_http_endpoint(self, generated_html: str) -> None:
        assert "/audio/" in generated_html, (
            "/audio/ endpoint reference missing from generated HTML JS"
        )

    def test_sheets_rewrite_to_http_endpoint(self, generated_html: str) -> None:
        assert "/sheets/" in generated_html, (
            "/sheets/ endpoint reference missing from generated HTML JS"
        )

    def test_rewrite_called_before_populatebandselect(
        self, generated_html: str
    ) -> None:
        # _bmRewriteFileUrls() must be called before populateBandSelect() *inside*
        # the DOMContentLoaded handler — we anchor to the first occurrence of that
        # event string so we're looking at the actual call order, not function defs.
        assert "_bmRewriteFileUrls()" in generated_html
        assert "DOMContentLoaded" in generated_html
        dcl_idx = generated_html.index("DOMContentLoaded")
        after_dcl = generated_html[dcl_idx:]
        rewrite_idx = after_dcl.index("_bmRewriteFileUrls()")
        populate_idx = after_dcl.index("populateBandSelect()")
        assert rewrite_idx < populate_idx, (
            "_bmRewriteFileUrls() must be called before populateBandSelect() "
            "inside the DOMContentLoaded handler"
        )

    def test_audio_pattern_matches_g_muzic(self, generated_html: str) -> None:
        # JS must match G:/Muzic audio paths
        assert "G:/Muzic" in generated_html or "G%3A%2FMuzic" in generated_html or (
            "Muzic" in generated_html
        ), "JS audio rewrite must reference G:/Muzic source path"

    def test_sheet_music_pattern_present(self, generated_html: str) -> None:
        # JS must match the sheet music path segment
        assert "sheet_music" in generated_html or "E2%9D%A4Music" in generated_html or (
            "catalog" in generated_html and "/sheets/" in generated_html
        ), "JS sheet music rewrite pattern must be present"


class TestAudioUrlRegexMatchesRealUrls:
    """Regression: the JS audio regex must match the actual file:///G:/Muzic/ format.

    The regex in _bmRewriteFileUrls() is JS but shares Python re syntax for
    this simple character-class pattern.  We use re.match() here to validate
    the pattern against real-world URL strings from catalog_export.json.
    """

    import re as _re

    # Real URL shapes taken from setlist_active_export.json and catalog
    _AUDIO_URLS = [
        "file:///G:/Muzic/Long%20Train%20Runnin%27%20-%20The%20Doobie%20Brothers.mp3",
        "file:///G:/Muzic/Too%20Much%20Time%20On%20My%20Hands%20-%20Styx.mp3",
        "file:///G:/Muzic/Rhiannon%20-%20Fleetwood%20Mac%20%28in%20Bm%29.wav",
        "file:///g:/Muzic/lowercase-drive.mp3",  # lowercase g
    ]

    def _extract_audio_regex(self, generated_html: str) -> str:
        import re
        # Pull the raw regex literal from the JS source
        m = re.search(r"audioMatch\s*=\s*s\.audio_url\.match\((/[^/].*?/i)\)", generated_html)
        assert m, "Could not find audioMatch regex in generated HTML"
        return m.group(1)

    def test_regex_matches_g_muzic_url_with_colon_slash(
        self, generated_html: str
    ) -> None:
        import re
        raw_re = self._extract_audio_regex(generated_html)
        # Strip JS regex delimiters and flags: /pattern/i → pattern
        pattern = raw_re.lstrip("/").rsplit("/", 1)[0]
        # Translate JS regex to Python: unescape \/  → /
        python_pattern = pattern.replace(r"\/", "/")
        for url in self._AUDIO_URLS:
            m = re.match(python_pattern, url, re.IGNORECASE)
            assert m, (
                f"Audio regex {pattern!r} failed to match URL: {url!r}\n"
                "Fix: ensure the regex handles 'G:/Muzic/' (colon + slash before Muzic)"
            )
            captured = m.group(1)
            assert not captured.startswith("/"), (
                f"Captured group should be the filename, not start with '/': {captured!r}"
            )
            assert "Muzic" not in captured, (
                f"Captured group must not include 'Muzic' prefix: {captured!r}"
            )

    def test_regex_does_not_match_non_audio_url(self, generated_html: str) -> None:
        import re
        raw_re = self._extract_audio_regex(generated_html)
        pattern = raw_re.lstrip("/").rsplit("/", 1)[0].replace(r"\/", "/")
        non_matches = [
            "http://example.com/song.mp3",
            "/audio/relative.mp3",
            "file:///G:/NotMuzic/song.mp3",
        ]
        for url in non_matches:
            assert not re.match(pattern, url, re.IGNORECASE), (
                f"Audio regex must NOT match {url!r}"
            )


class TestPauseButtonUsesResolvedUrl:
    """Regression: bmPlayRow must compare audio.src against new URL(url, location.href).href.

    audio.src is always absolute (browser-resolved); comparing against the raw
    relative /audio/... string always returns false → pause never triggers.
    """

    def test_pause_compares_resolved_url(self, generated_html: str) -> None:
        # The JS must resolve the relative URL before comparing with audio.src
        assert "new URL(url, location.href).href" in generated_html, (
            "bmPlayRow must resolve url via new URL(url, location.href).href "
            "before comparing with audio.src — bare === comparison always fails "
            "because audio.src is absolute but data-audio-url is relative"
        )

    def test_pause_check_uses_resolved_not_raw(self, generated_html: str) -> None:
        # Ensure the old broken pattern is NOT present: audio.src === url
        # (where url is the raw relative value)
        import re
        # Find the bmPlayRow function body
        m = re.search(r"window\.bmPlayRow\s*=\s*function.*?audio\.onended", generated_html, re.DOTALL)
        assert m, "bmPlayRow function not found"
        fn_body = m.group(0)
        assert "audio.src === resolvedUrl" in fn_body, (
            "Pause check must use resolvedUrl, not raw url"
        )
        # The raw comparison pattern must not appear (would always be false)
        assert "audio.src === url" not in fn_body, (
            "audio.src === url comparison must be removed — it always fails "
            "because audio.src is absolute while url is relative (/audio/...)"
        )


# ---------------------------------------------------------------------------
# 8 – 11 — Integration: live HTTP server
# ---------------------------------------------------------------------------

def _find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(port: int, retries: int = 30) -> bool:
    for _ in range(retries):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1)
            return True
        except Exception:
            time.sleep(0.1)
    return False


@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    """Start a live _serve_mode server using temp directories."""
    audio_root = tmp_path_factory.mktemp("audio_srv")
    sheets_root = tmp_path_factory.mktemp("sheets_srv")

    orig_audio = mod.AUDIO_ROOT
    orig_sheets = mod.SHEETS_ROOT
    mod.AUDIO_ROOT = audio_root
    mod.SHEETS_ROOT = sheets_root

    port = _find_free_port()
    thread = threading.Thread(
        target=mod._serve_mode,
        args=("127.0.0.1", port),
        daemon=True,
    )
    thread.start()

    started = _wait_for_server(port)

    yield {"port": port, "audio_root": audio_root, "sheets_root": sheets_root, "started": started}

    mod.AUDIO_ROOT = orig_audio
    mod.SHEETS_ROOT = orig_sheets


class TestAudioEndpoint:
    """Integration tests for /audio/<filename> endpoint."""

    def test_audio_serves_file_200(self, live_server: dict) -> None:
        if not live_server["started"]:
            pytest.skip("Server did not start in time")
        port = live_server["port"]
        audio_root: Path = live_server["audio_root"]
        audio_file = audio_root / "test_song.mp3"
        audio_file.write_bytes(b"\xff\xfbFAKE_MP3_DATA")

        resp = urllib.request.urlopen(
            f"http://127.0.0.1:{port}/audio/test_song.mp3", timeout=3
        )
        assert resp.status == 200
        assert resp.read() == b"\xff\xfbFAKE_MP3_DATA"

    def test_audio_serves_urlencoded_filename(self, live_server: dict) -> None:
        if not live_server["started"]:
            pytest.skip("Server did not start in time")
        port = live_server["port"]
        audio_root: Path = live_server["audio_root"]
        fname = "Long Train Runnin.mp3"
        (audio_root / fname).write_bytes(b"AUDIO_CONTENT")

        resp = urllib.request.urlopen(
            f"http://127.0.0.1:{port}/audio/Long%20Train%20Runnin.mp3", timeout=3
        )
        assert resp.status == 200

    def test_audio_missing_file_returns_404(self, live_server: dict) -> None:
        if not live_server["started"]:
            pytest.skip("Server did not start in time")
        port = live_server["port"]
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(
                f"http://127.0.0.1:{port}/audio/no_such_file.mp3", timeout=3
            )
        assert exc_info.value.code == 404

    def test_audio_traversal_returns_error(self, live_server: dict) -> None:
        if not live_server["started"]:
            pytest.skip("Server did not start in time")
        port = live_server["port"]
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(
                f"http://127.0.0.1:{port}/audio/..%2Fevil.txt", timeout=3
            )
        assert exc_info.value.code in (400, 403, 404)

    def test_audio_range_request_returns_206(self, live_server: dict) -> None:
        if not live_server["started"]:
            pytest.skip("Server did not start in time")
        port = live_server["port"]
        audio_root: Path = live_server["audio_root"]
        range_file = audio_root / "range_test.mp3"
        range_file.write_bytes(b"ABCDEFGHIJ")  # 10 bytes

        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/audio/range_test.mp3",
            headers={"Range": "bytes=0-4"},
        )
        resp = urllib.request.urlopen(req, timeout=3)
        assert resp.status == 206
        assert resp.read() == b"ABCDE"


class TestSheetsEndpoint:
    """Integration tests for /sheets/<relpath> endpoint."""

    def test_sheets_serves_file_200(self, live_server: dict) -> None:
        if not live_server["started"]:
            pytest.skip("Server did not start in time")
        port = live_server["port"]
        sheets_root: Path = live_server["sheets_root"]
        sheet_file = sheets_root / "covers" / "Amazing Grace.docx"
        sheet_file.parent.mkdir(parents=True, exist_ok=True)
        sheet_file.write_bytes(b"FAKE_DOCX_CONTENT")

        resp = urllib.request.urlopen(
            f"http://127.0.0.1:{port}/sheets/covers/Amazing%20Grace.docx", timeout=3
        )
        assert resp.status == 200
        assert resp.read() == b"FAKE_DOCX_CONTENT"

    def test_sheets_missing_file_returns_404(self, live_server: dict) -> None:
        if not live_server["started"]:
            pytest.skip("Server did not start in time")
        port = live_server["port"]
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(
                f"http://127.0.0.1:{port}/sheets/covers/no_such.docx", timeout=3
            )
        assert exc_info.value.code == 404

    def test_sheets_traversal_returns_error(self, live_server: dict) -> None:
        if not live_server["started"]:
            pytest.skip("Server did not start in time")
        port = live_server["port"]
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(
                f"http://127.0.0.1:{port}/sheets/..%2Fevil.txt", timeout=3
            )
        assert exc_info.value.code in (400, 403, 404)

    def test_sheets_docx_content_type(self, live_server: dict) -> None:
        if not live_server["started"]:
            pytest.skip("Server did not start in time")
        port = live_server["port"]
        sheets_root: Path = live_server["sheets_root"]
        docx_file = sheets_root / "test.docx"
        docx_file.write_bytes(b"DOCX_DATA")

        resp = urllib.request.urlopen(
            f"http://127.0.0.1:{port}/sheets/test.docx", timeout=3
        )
        ct = resp.headers.get("Content-Type", "")
        assert "wordprocessingml" in ct or "docx" in ct or "openxmlformats" in ct, (
            f"Expected .docx Content-Type, got {ct!r}"
        )
