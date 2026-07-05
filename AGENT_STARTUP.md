# ⚡ AGENT STARTUP DIRECTIVE — ❤Music

**READ THIS FIRST.** Context bootstrap for any AI agent picking up work on the ❤Music project.

---

## 1. Gather Context

```
1. Read this file completely
2. Read TODO_AI.md for current agentic task queue
3. Read TODO_TYLER.md for pending human actions and blockers
4. Read ARTIST_PROFILE.json for current artist state
5. Read README.md for architecture context if needed
```

## 2. Project Location & Key Paths

| Resource | Path |
|----------|------|
| **Project Root** | `f:\❤Music\` |
| **Workspace Root** | `f:\` |
| **SQLite Database** | `src/data/heartmusic.db` |
| **Python Executable** | `C:\G\python.exe` |
| **Music Dashboard** | `src/analysis/music_dashboard.py` |
| **TJD Radio Service** | `src/radio/tjd_radio.py` |
| **Agent Definitions** | `f:\.github\agents\❤music-*.agent.md` |
| **Artist Profile** | `f:\❤Music\ARTIST_PROFILE.json` |

### ❤Music Agents

| Agent | Purpose |
|-------|---------|
| **❤music-orchestrator** | Top-level coordinator. Default entry point for complex tasks. |
| **❤music-catalog** | File indexing, duplicate detection, track linking, lyrics import |
| **❤music-production** | Album production tracking — Bloom, track status, mixing pipeline |
| **❤music-performance** | Gig logging, practice tracking, CopperCreek band management |
| **❤music-signatures** | Binary signature analysis — audio file forensics, hash/entropy extraction, Suno/Pro Tools provenance, release_signatures table |
| **❤music-guitar-tech** | Guitar-legend persona matching, HX Stomp `.hlx` preset generation/validation, `guitar_tone_profiles` |
| **⊕workspace-hygiene** | Unified workspace hygiene — archiving completed tasks, pruning stale files, DB hygiene, agent infrastructure audit |

## 3. Artist Summary

- **Solo Artist:** Tyler James Drake
- **Band:** CopperCreek
- **Active Album:** *Bloom* at Hyperthreat Studios (in progress)
- **Links:** `f:\linkTyler.json`

### Source File Locations (READ ONLY — do not move/delete)

| Content | Path |
|---------|------|
| Masters | `f:\Masters\` — Album 1, EP, Ben's Lullaby, Bloom Album, EP Singles |
| Rockstar backup | `G:\TylerJamesDrake\rockstar\` (subset of Masters) |
| Recordings | `f:\recordings\` |
| Lyrics (raw ideas) | `f:\lyrics\` |
| **Transcendent songs** | `f:\❤Music\docs\transcendent\` — hooks that arrived whole in a flash; elevated tier above raw lyrics |
| Guitar | `f:\Guitar\` |
| Bands / CopperCreek | `f:\bands\copperCreek\` |
| Sheet Music | `C:\Users\tyler\Documents` |

## 4. Data Architecture

**heartmusic.db is the system of truth for all music metadata.**

```python
from utils.init_db import get_connection
conn = get_connection()
```

### Schema

| Table | Purpose |
|-------|---------|
| `artist_profiles` | Tyler (solo) + CopperCreek |
| `albums` | Bloom, EP, etc. with production status |
| `tracks` | Song metadata — key, BPM, status |
| `recordings` | File paths to masters/roughs with quality ratings |
| `lyrics` | Content or file refs per track |
| `gigs` | Past/upcoming performances |
| `practice_log` | Practice sessions |
| `gear` | Instruments and equipment |
| `collaborators` | Producers, bandmates, engineers |
| `budget` | Studio time, gear, distribution costs |
| `releases` | Platform links and release dates |
| `catalog_index` | Flat index of all source files — category, path, size |

## 5. Workflow Rules

- Research notes → `research/<domain>/`
- Python source → `src/` with `__init__.py`
- Data → SQLite DB only, no loose JSON
- Production docs → `docs/protocols/`
- Journal entries → `docs/journal/YYYY-MM-DD.md`
- **Transcendent song visions** → `docs/transcendent/<working-title>.md` — complete hook flashes, captured verbatim, not to be over-edited
- **Never move or delete source music files** — catalog by reference in `catalog_index`
- Add Tyler blockers to `TODO_TYLER.md`

## 6. Current Phase

**Phase 1: Catalog Consolidation**
- ✅ Project scaffold created
- ✅ SQLite DB initialized (11 tables)
- ✅ Agent definitions live (`❤music-orchestrator`, `❤music-catalog`, `❤music-production`, `❤music-performance`)
- ✅ Run `tools/catalog_index.py` to index all source locations — 12,473 files indexed (2026-04-17)
- ✅ Import Bloom track list — all 7 tracks verified in `tracks` table, master WAVs linked from `G:\TylerJamesDrake\rockstar\Bloom Album` (2026-04-17)
- ⬜ Import CopperCreek metadata
- ⬜ Deduplicate Masters vs rockstar backup

## 7. Pick Up & Go

Check `TODO_AI.md` for the highest priority incomplete task and begin work.

## 8. Dashboard + Radio Startup

Use this when you need the full operational surface (tracks, release ops, and live radio) available in one session.

```powershell
Set-Location "f:\❤Music"

# Terminal 1: start the live station
C:\G\python.exe src/radio/tjd_radio.py --port 8100 --bitrate 192 --crossfade 2 --bumper-dir catalog/bumpers --bumper-every 3

# Terminal 2: start the dashboard
C:\G\python.exe src/analysis/music_dashboard.py --port 5050 --no-open
```

Integration notes:
- The dashboard Radio tab consumes `http://localhost:8100/api/now_playing` and `http://localhost:8100/api/playlist` via proxy routes.
- If the radio process is down, the Radio tab shows offline status but the rest of the dashboard still works.

## 9. Google Drive Integration (FR-20260530-gdrive-integration)

### GDRIVE_SA_KEY Environment Variable

**What it is:**
`GDRIVE_SA_KEY` is a Windows System environment variable containing the
**base64-encoded** contents of a Google service account JSON key file.  The
integration in `⊕Workspace/src/integrations/gdrive/` reads this variable at
runtime to authenticate against the Google Drive API.  It is **never written
to disk** and must **never appear in any committed file**.

**How to create:**

1. In the Google Cloud Console, create a service account with Drive read-only
   access and download its JSON key file (e.g. `gdrive-sa-key.json`).

2. In PowerShell, base64-encode the file:
   ```powershell
   $b64 = [System.Convert]::ToBase64String(
       [System.IO.File]::ReadAllBytes("C:\path\to\gdrive-sa-key.json")
   )
   $b64  # copy this value
   ```

3. Set it as a **Windows System** environment variable (not user-level, not
   .env file):
   ```powershell
   # Run as Administrator:
   [System.Environment]::SetEnvironmentVariable(
       "GDRIVE_SA_KEY", $b64, "Machine"
   )
   ```
   Restart any open terminals after setting.

4. Verify:
   ```powershell
   $env:GDRIVE_SA_KEY.Substring(0, 20)  # should show first 20 chars of base64
   ```

**Security rules:**
- ❌ NEVER commit the raw `.json` key file to any repository
- ❌ NEVER commit the decoded JSON or the base64 string to any file
- ❌ NEVER put `GDRIVE_SA_KEY` in `.env` files that are committed
- ✅ Set it as a Windows System environment variable only
- ✅ The `.gitignore` must list `*.json` and `gdrive-sa-key*` patterns

**Using the integration:**
```python
from integrations.gdrive import GDriveClient

client = GDriveClient()  # reads GDRIVE_SA_KEY from env at construction
pdf_files = client.list_files(mime_types=["application/pdf"])
```

**Running the ingest scripts:**
```powershell
# 1. Create the sheet_music table (idempotent)
$env:PYTHONUTF8="1"
cd "f:\❤Music"
C:\G\python.exe src/scripts/migrate_sheet_music_table.py

# 2. Backfill local catalog/sheet_music/ files
C:\G\python.exe src/scripts/backfill_local_sheet_music.py

# 3. Ingest metadata from Google Drive (requires GDRIVE_SA_KEY)
C:\G\python.exe src/scripts/ingest_sheet_music_gdrive.py
```

