#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUT_DIR="${PROJECT_ROOT}/output/radio_phase_alpha"
LIQ_SCRIPT="${OUT_DIR}/tjd_radio_phase_alpha.liq"
PID_FILE="${OUT_DIR}/liquidsoap.pid"

if [[ ! -f "${LIQ_SCRIPT}" ]]; then
  echo "Missing ${LIQ_SCRIPT}. Run tools/radio_phase_alpha_wsl_setup.sh first."
  exit 1
fi

echo "[phase-alpha] Starting Icecast2"
sudo service icecast2 start

if [[ -f "${PID_FILE}" ]]; then
  old_pid="$(cat "${PID_FILE}")"
  if [[ -n "${old_pid}" ]] && kill -0 "${old_pid}" 2>/dev/null; then
    echo "[phase-alpha] Stopping old Liquidsoap PID ${old_pid}"
    kill "${old_pid}" || true
  fi
fi

echo "[phase-alpha] Starting Liquidsoap"
nohup liquidsoap "${LIQ_SCRIPT}" > "${OUT_DIR}/liquidsoap.log" 2>&1 &
echo $! > "${PID_FILE}"

sleep 2

echo "[phase-alpha] Health check"
curl -fsS "http://127.0.0.1:8000/status-json.xsl" > /dev/null

echo "[phase-alpha] Live"
echo "Stream: http://localhost:8000/stream"
echo "Status: http://localhost:8000/status-json.xsl"
