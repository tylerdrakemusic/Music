#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUT_DIR="${PROJECT_ROOT}/output/radio_phase_alpha"

export DEBIAN_FRONTEND=noninteractive

echo "[phase-alpha] Installing Icecast2 + Liquidsoap + ffmpeg"
sudo apt-get update
sudo apt-get install -y icecast2 liquidsoap ffmpeg curl python3

echo "[phase-alpha] Generating playlist/config assets"
python3 "${PROJECT_ROOT}/tools/radio_phase_alpha_poc.py" --project-root "${PROJECT_ROOT}" --output-dir "${OUT_DIR}"

echo "[phase-alpha] Installing Icecast config"
sudo cp "${OUT_DIR}/icecast_phase_alpha.xml" /etc/icecast2/icecast.xml

echo "[phase-alpha] Setup complete"
echo "Next: edit passwords in /etc/icecast2/icecast.xml and ${OUT_DIR}/tjd_radio_phase_alpha.liq"
echo "Then run: ${PROJECT_ROOT}/tools/radio_phase_alpha_wsl_start.sh"
