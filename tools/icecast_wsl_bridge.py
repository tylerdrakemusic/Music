#!/usr/bin/env python3
"""Local bridge for WSL-hosted Icecast.

Windows processes in this workspace cannot always reach WSL Icecast directly
on 127.0.0.1:8000 or WSL eth0 IP due host networking policy. This bridge keeps
all browser/panel traffic local on Windows and fetches Icecast data inside WSL.
"""

from __future__ import annotations

import argparse
import subprocess
from flask import Flask, Response


app = Flask(__name__)


def _wsl_curl(url: str, stream: bool = False) -> subprocess.Popen[bytes]:
    cmd = [
        "wsl",
        "-d",
        "Ubuntu",
        "--",
        "bash",
        "-lc",
        f"curl -fsS {'-N ' if stream else ''}{url}",
    ]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


@app.route("/status-json.xsl")
def status_json() -> Response:
    proc = _wsl_curl("http://127.0.0.1:8000/status-json.xsl")
    out, err = proc.communicate(timeout=8)
    if proc.returncode != 0:
        msg = err.decode("utf-8", errors="replace")
        return Response(msg or "bridge status fetch failed", status=502, mimetype="text/plain")
    return Response(out, status=200, mimetype="application/json")


@app.route("/stream")
def stream() -> Response:
    proc = _wsl_curl("http://127.0.0.1:8000/stream", stream=True)

    def generate() -> bytes:
        assert proc.stdout is not None
        try:
            while True:
                chunk = proc.stdout.read(64 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            proc.kill()

    return Response(generate(), mimetype="audio/mpeg")


@app.route("/health")
def health() -> Response:
    return Response(json.dumps({"status": "ok", "ready": True}), status=200, mimetype="application/json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bridge WSL Icecast to local Windows HTTP")
    parser.add_argument("--port", type=int, default=18000)
    args = parser.parse_args()

    app.run(host="127.0.0.1", port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
