#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUT_DIR="${PROJECT_ROOT}/output/radio_phase_alpha"
PID_FILE="${OUT_DIR}/liquidsoap.pid"

if [[ -f "${PID_FILE}" ]]; then
  pid="$(cat "${PID_FILE}")"
  if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
    echo "[phase-alpha] Stopping Liquidsoap PID ${pid}"
    kill "${pid}" || true
  fi
  rm -f "${PID_FILE}"
fi

echo "[phase-alpha] Stopping Icecast2"
sudo service icecast2 stop || true

echo "[phase-alpha] Stopped"
