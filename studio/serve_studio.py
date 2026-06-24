#!/usr/bin/env python3
"""Local autosave server for the HyperThreat Studios HTML tools.

A page opened by double-clicking (a ``file://`` page) cannot write back to its
own file — browsers forbid it. When the studio tools are opened *through this
server* instead (``http://127.0.0.1:<port>/patch_bay.html``) they can POST their
self-contained HTML to ``/__save`` and this server writes it straight back to the
file on disk. The operator never clicks save and no work is lost.

Design notes
------------
* Localhost only (binds 127.0.0.1) — never exposed to the network.
* Only an allowlist of known files may be overwritten (no arbitrary writes).
* Writes are atomic (temp file + ``os.replace``).
* Zero third-party dependencies (Python standard library only).

Usage
-----
    C:\\G\\python.exe serve_studio.py            # serve this folder on port 8755
    C:\\G\\python.exe serve_studio.py 9000       # custom port

Then open, e.g., http://127.0.0.1:8755/patch_bay.html and just work — edits
auto-save back to studio/patch_bay.html.
"""
from __future__ import annotations

import os
import sys
import tempfile
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

STUDIO_DIR = os.path.dirname(os.path.abspath(__file__))

# Only these files may be overwritten by the save endpoint.
SAVABLE = {"patch_bay.html", "mic_config_template.html"}

# Reject anything larger than this (a self-contained page is a few hundred KB).
MAX_BYTES = 5 * 1024 * 1024


class StudioHandler(SimpleHTTPRequestHandler):
    """Serves the studio folder and accepts POST /__save writes."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STUDIO_DIR, **kwargs)

    def log_message(self, fmt, *args):
        sys.stderr.write("[studio] " + (fmt % args) + "\n")

    def end_headers(self):
        # Never cache the served HTML, so a reload always shows the latest
        # auto-saved version of the file.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/__save":
            self.send_error(404, "Not found")
            return

        name = (parse_qs(parsed.query).get("file") or [""])[0]
        if name not in SAVABLE:
            self.send_error(403, "File not savable")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BYTES:
            self.send_error(413, "Bad payload size")
            return

        body = self.rfile.read(length)
        # Cheap sanity check: must look like an HTML document.
        if b"<html" not in body[:2000].lower():
            self.send_error(400, "Not an HTML document")
            return

        target = os.path.join(STUDIO_DIR, name)
        # Defence in depth: the resolved path must stay directly inside STUDIO_DIR.
        if os.path.dirname(os.path.abspath(target)) != STUDIO_DIR:
            self.send_error(403, "Path not allowed")
            return

        if not self._write_file(target, body):
            # Keep the HTTP reason phrase ASCII-only — paths may contain
            # non-latin-1 characters (e.g. the project sigils).
            self.send_error(500, "Write failed")
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    @staticmethod
    def _write_file(target, body):
        """Write *body* to *target*, atomically when the OS allows it.

        Prefers a temp file + ``os.replace`` (atomic), but Windows refuses the
        rename when the target is held open by another process (e.g. an editor),
        so fall back to an in-place write.
        """
        directory = os.path.dirname(target)
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(body)
            os.replace(tmp, target)
            return True
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            sys.stderr.write("[studio] atomic replace blocked; writing in place\n")
            try:
                with open(target, "wb") as handle:
                    handle.write(body)
                return True
            except OSError:
                sys.stderr.write("[studio] in-place write failed\n")
                return False


def main() -> None:
    port = 8755
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"[studio] ignoring invalid port '{sys.argv[1]}', using {port}")

    httpd = HTTPServer(("127.0.0.1", port), StudioHandler)
    base = f"http://127.0.0.1:{port}/"
    print(f"[studio] serving {STUDIO_DIR}")
    print(f"[studio] open:  {base}patch_bay.html")
    print(f"[studio] open:  {base}mic_config_template.html")
    print("[studio] autosave active — edits POST back to the file. Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[studio] stopped.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
