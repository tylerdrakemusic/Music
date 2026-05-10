#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUT_DIR="${PROJECT_ROOT}/output/radio_phase_alpha"

samples=120
interval_seconds=60

while [[ $# -gt 0 ]]; do
  case "$1" in
    --samples)
      samples="$2"
      shift 2
      ;;
    --interval-seconds)
      interval_seconds="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

timestamp="$(date +%Y%m%dT%H%M%S)"
log_path="${OUT_DIR}/stability_monitor_${timestamp}.log"

: > "${log_path}"

for _ in $(seq 1 "${samples}"); do
  status_json="$(curl -fsS "http://127.0.0.1:8000/status-json.xsl")"
  sample_time="$(date -Iseconds)"

  python3 - <<'PY' "${status_json}" "${sample_time}" >> "${log_path}"
import json
import sys

payload = json.loads(sys.argv[1])
sample_time = sys.argv[2]
source = payload.get("icestats", {}).get("source")
if isinstance(source, list):
    source = source[0] if source else {}
if not source:
    raise SystemExit("No active source found in Icecast status JSON")

print(
    f"{sample_time} listeners={source.get('listeners', 0)} "
    f"title={source.get('title', '')} artist={source.get('artist', '')}"
)
PY

  sleep "${interval_seconds}"
done

echo "Stability monitor complete: ${log_path}"