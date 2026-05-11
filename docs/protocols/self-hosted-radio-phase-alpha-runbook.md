# Self-Hosted Radio Phase alpha Runbook (WSL2)

This runbook implements Phase alpha from IP_STRATEGY.md Section 7 using Icecast 2 + Liquidsoap in WSL2.

## Scope
- WSL2 Ubuntu runtime
- Tyler-owned catalog only (`catalog/masters`, `catalog/ep`)
- Single mount stream: `/stream`
- Browser playback validation page
- Metadata verification through Icecast status endpoint
- Local panel default backend: Icecast (`src/radio/tjd_radio.py --backend icecast`)
- Catalog policy for local panel source snapshot: Muzic primary, Tyler-owned roots fallback

## 1. Setup (one-time per environment)
From WSL in the ❤Music project root:

```bash
bash tools/radio_phase_alpha_wsl_setup.sh
```

From Windows PowerShell:

```powershell
./tools/radio_phase_alpha_setup.ps1
```

Then edit passwords:
- `/etc/icecast2/icecast.xml`
- `output/radio_phase_alpha/tjd_radio_phase_alpha.liq`

Use matching source password values in both files.

## 2. Start

```bash
bash tools/radio_phase_alpha_wsl_start.sh
```

Windows wrapper:

```powershell
./tools/radio_phase_alpha_start.ps1
```

Expected:
- Stream is reachable at `http://localhost:8000/stream`
- Status JSON is reachable at `http://localhost:8000/status-json.xsl`

## 3. Playback check
Open:
- `reports/tjd_radio_phase_alpha_player.html`

Click play and confirm audio is live.

## 4. Metadata check (Now Playing)

```bash
bash tools/radio_phase_alpha_wsl_verify.sh
```

Windows wrapper:

```powershell
./tools/radio_phase_alpha_verify.ps1
```

Pass criteria:
- `title` is non-empty
- script exits successfully

## 5. Stability proof (2+ hours)
Run this while the stream is live:

```bash
bash tools/radio_phase_alpha_wsl_stability.sh
```

Store logs:
- `output/radio_phase_alpha/liquidsoap.log`
- `output/radio_phase_alpha/stability_monitor_*.log`
- `/var/log/icecast2/access.log`
- `/var/log/icecast2/error.log`

## 6. Stop

```bash
bash tools/radio_phase_alpha_wsl_stop.sh
```

Windows wrapper:

```powershell
./tools/radio_phase_alpha_stop.ps1
```

## 7. Local panel integration (Icecast-first)

Start the local panel with Icecast as the default backend:

```powershell
C:\G\python.exe src/radio/tjd_radio.py --backend icecast --port 8100
```

Optional explicit fallback mode (legacy local broadcaster):

```powershell
C:\G\python.exe src/radio/tjd_radio.py --backend local --port 8100
```

Icecast-default expected behavior:
- `http://localhost:8100/stream` redirects to active Icecast mount
- `http://localhost:8100/api/now_playing` proxies from Icecast status JSON and normalizes artist/title
- `http://localhost:8100/api/playlist` reflects the panel's source snapshot (Muzic primary + Tyler fallback)

Public interfacing note:
- Icecast is only internet-public if host/network exposure is explicitly configured.
- Localhost-only operation keeps stream local to the machine.

## Notes
- This phase intentionally excludes quantum integration (Phase beta+).
- If `liquidsoap` exits immediately, check password mismatch or missing catalog files.
- Regenerate assets any time catalog content changes:

```bash
python3 tools/radio_phase_alpha_poc.py
```
