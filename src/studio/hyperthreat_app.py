"""Isolated static launcher for the Hyperthreat Studios templates."""

import os
from pathlib import Path

from flask import Flask, Response, jsonify, send_file

ROOT = Path(__file__).resolve().parents[2]
LOGO_PATH = ROOT / "Brand" / "hyperthreat" / "hyperthreat-logo.png"
MIC_CONFIG_PATH = ROOT / "studio" / "mic_config_template.html"
PATCH_BAY_PATH = ROOT / "studio" / "patch_bay.html"

app = Flask(__name__)

LAUNCHER_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hyperthreat Studios Templates</title>
  <style>
    body { margin: 0; padding: 2rem; font-family: sans-serif; color: #111; background: #f4f1eb; }
    main { max-width: 42rem; margin: 0 auto; }
    header { display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; }
    header img { width: min(100%, 18rem); height: auto; }
    nav { display: grid; gap: 1rem; margin-top: 2rem; }
    a { color: inherit; font-weight: 700; }
    @media (max-width: 30rem) { body { padding: 1rem; } }
  </style>
</head>
<body>
  <main>
    <header>
      <img src="/assets/hyperthreat-logo.png" alt="Hyperthreat Studios logo">
      <h1>Hyperthreat Studios</h1>
    </header>
    <p>Studio configuration templates</p>
    <nav aria-label="Studio templates">
      <a href="/mic-config">Mic Config</a>
      <a href="/patch-bay">Patch Bay</a>
    </nav>
  </main>
</body>
</html>"""


@app.get("/")
def launcher() -> Response:
    """Render the minimal template launcher."""
    return Response(LAUNCHER_HTML, mimetype="text/html")


@app.get("/assets/hyperthreat-logo.png")
def hyperthreat_logo() -> Response:
  """Serve only the dedicated Hyperthreat launcher logo asset."""
  return send_file(LOGO_PATH, mimetype="image/png")


@app.get("/mic-config")
def mic_config() -> Response:
    """Serve the existing Mic Config document without modification."""
    return send_file(MIC_CONFIG_PATH, mimetype="text/html")


@app.get("/patch-bay")
@app.get("/patch_bay.html")
def patch_bay() -> Response:
    """Serve the existing Patch Bay document without modification."""
    return send_file(PATCH_BAY_PATH, mimetype="text/html")


@app.get("/health")
def health() -> Response:
    """Return the readiness response used by Fly.io health checks."""
    return jsonify({"status": "ok", "ready": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))