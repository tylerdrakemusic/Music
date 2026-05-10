#!/usr/bin/env bash
set -euo pipefail

status_json="$(curl -fsS "http://127.0.0.1:8000/status-json.xsl")"

python3 - <<'PY' "${status_json}"
import json
import sys

payload = json.loads(sys.argv[1])
source = payload.get("icestats", {}).get("source")
if isinstance(source, list):
    source = source[0] if source else {}
if not source:
    raise SystemExit("No active source found in Icecast status JSON")

title = source.get("title") or ""
artist = source.get("artist") or ""
listeners = source.get("listeners", 0)

print(f"listeners={listeners}")
print(f"title={title}")
print(f"artist={artist}")

if not title:
    raise SystemExit("Now-playing title metadata is empty")
PY

echo "Phase alpha verification passed"
