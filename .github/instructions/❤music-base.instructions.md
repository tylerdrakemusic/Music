---
applyTo: ".github/agents/❤music-*.agent.md"
---

# ❤Music Base Agent Instructions

Shared context, conventions, and rules for all `❤music-*` agents. Every ❤Music agent inherits these. Agent-specific details override where noted.

---

## Context Bootstrap (All Agents)

Before doing any work, load context in this order:
1. `f:\❤Music\AGENT_STARTUP.md` — current project state, recent migrations, active tasks
2. `f:\❤Music\ARTIST_PROFILE.json` — Tyler's artist profile, all source locations, album definitions, track lists

---

## Artist Profile

**Tyler James Drake** — solo artist + lead of CopperCreek
- Bloom album: in progress at Hyperthreat Studios
- EP: released (Marigold, Get Out, What I Do)
- Python executable: `C:\G\python.exe`

---

## Database Access

```python
from utils.init_db import get_connection
conn = get_connection()
# OR direct:
import sqlite3
conn = sqlite3.connect("f:/❤Music/src/data/heartmusic.db")
```

**Python executable:** `C:\G\python.exe`  
**Run from project root:** `f:\❤Music\`

### Database Rules
- **ALWAYS use parameterized queries** — no f-string SQL
- **NEVER modify schema** without explicit approval
- **NEVER delete records** — flag issues, let Tyler decide
- **NEVER drop tables** without confirmation

### Worktree-Aware DB Access (tools/*.py scripts)
Any `tools/*.py` script that touches `heartmusic.db` directly (not via a test
fixture) MUST be worktree-aware. Git worktrees under `.worktrees/<branch>/`
have their own empty `data/` dir, so `init_db.DB_PATH`'s default resolution
finds no DB there and the script fails with "heartmusic.db not found."

Use the shared helper instead of re-implementing path-walking per script:

```python
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))
import utils.init_db as _init_db_module  # noqa: E402

_init_db_module.use_worktree_aware_db_path(_ROOT)

from utils.init_db import get_connection  # noqa: E402
```

`use_worktree_aware_db_path()` walks up from `_ROOT` looking for
`src/data/heartmusic.db` and repoints `DB_PATH` at the main project's live DB
when found; it's a no-op when already running from the main tree.

---

## Catalog Source Locations (Read-Only External Sources)

| Name | Path |
|---|---|
| Masters (F:) | `f:\Masters\` |
| Rockstar backup (G:) | `G:\TylerJamesDrake\rockstar\` |
| Roughs (E:) | `E:\Roughs\` |
| Recordings | `f:\recordings\` |
| Lyrics source | `f:\lyrics\` |
| Guitar source | `f:\Guitar\` |
| Bands | `f:\bands\` |

**Do NOT move, delete, or rename source files from external locations. Reference or copy into catalog only.**

---

## Catalog (Local Source of Truth)

| Content | Path |
|---|---|
| Bloom masters | `catalog/masters/Bloom/` |
| EP masters | `catalog/ep/` |
| Roughs | `catalog/roughs/<album>/<song>/` |
| Sheet music — originals | `catalog/sheet_music/originals/` |
| Sheet music — covers | `catalog/sheet_music/covers/` |
| Sheet music — templates (JSON) | `catalog/sheet_music/templates/` |
| Sheet music — generated (DOCX) | `catalog/sheet_music/generated/` |
| Lyrics data | `catalog/lyrics/` |
| Music training configs | `catalog/music_training/` |
| Video projects | `catalog/video_projects/` |

---

## Output Routing

| Content Type | Location |
|---|---|
| Research notes | `research/<domain>/` as markdown |
| Production notes | `docs/protocols/` |
| Session journal | `docs/journal/YYYY-MM-DD.md` |
| Artist/album/track data | SQLite DB (`heartmusic.db`) — NOT loose JSON |
| Tyler action items | `TODO_TYLER.md` |
| Agent task queue | `TODO_AI.md` |
| Studio metadata | `src/data/studio_master/` |

---

## Tools Prefix Convention

| Prefix | Category |
|---|---|
| `@` | Creative / performance tools (`@music_training.py`, `@group_rhymes.py`, `@make_chord_sheet.py`) |
| `~` | Migration / maintenance tools (`~catalog_index.py`, `~migrate_*.py`) |

---

## Agent Delegation

Discover available agents by scanning `../../.github/agents\❤music-*.agent.md`. Read `description` frontmatter for capabilities.

### Known specialists
| Agent | Domain |
|---|---|
| `❤music-catalog` | File indexing, dedup, track linking, DB imports |
| `❤music-production` | Bloom album tracking, track status, studio sessions |
| `❤music-performance` | Gigs, practice log, CopperCreek, setlists |
| `❤music-guitar-tech` | Guitar-legend persona matching, HX Stomp `.hlx` preset generation/validation, `guitar_tone_profiles` |
| `⊕workspace-hygiene` | File cleanup, TODO archiving, DB housekeeping, agent audit |
| `❤music-orchestrator` | Top-level coordinator for multi-domain tasks |

---

## Flask App / Portal Registration (MANDATORY for every new Flask app)

When any ❤Music agent creates a new Flask app (any `src/**/*.py` served on a localhost port), ALL FOUR of the following steps are **required** before the work is considered done. Missing any step means the server won't auto-start when Tyler opens the portal.

### Checklist
1. **`❤Music/dashboard.json`** — add an entry with `"type": "flask_app"`, `"cli"`, `"url"`, `"port"`, and `"priority"`.
2. **`⊕Workspace/tools/start_<name>.ps1`** — create a PowerShell launcher script:
   ```powershell
   $env:PYTHONPATH = "f:\❤Music\src"
   & "C:\G\python.exe" "f:\❤Music\src\<path>\<app>.py" --port <PORT>
   ```
3. **`⊕Workspace/tools/portal_servers.json`** — add an entry:
   ```json
   {
     "name": "<Display Name>",
     "port": <PORT>,
     "project": "❤Music",
     "cmd": "powershell.exe -NoProfile -WindowStyle Minimized -ExecutionPolicy Bypass -File f:\\⊕Workspace\\tools\\start_<name>.ps1",
     "enabled": true
   }
   ```
4. **`⊕Workspace/reports/portal.html`** — add the port to the `SERVERS` JS array near the bottom of the file:
   ```js
   const SERVERS = [...existing..., {"port": <PORT>, "name": "<Display Name>"}];
   ```

Steps 2–4 are in the **⊕Workspace** repo and must be committed on the corresponding `feature/workspace/...` branch. Coordinate with `⊕workspace-doer` if you don't have write access to that repo's branch.

**The Flask app itself must accept a `--port` CLI argument:**
```python
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, default=<PORT>)
args = parser.parse_args()
app.run(host="0.0.0.0", port=args.port)
```

---

## Core Operating Rules

1. **DO NOT move or delete external source files** (Masters, Rockstar, Roughs on E:/F:/G: drives)
2. **DO NOT fabricate metadata** — if a track's BPM/key is unknown, mark as null in DB
3. **DO NOT execute destructive operations** without confirmation
4. **PREFER editing existing files** over creating new ones
5. **PREFER DB storage** over loose JSON/CSV for structured music data
6. **ALWAYS use UTF-8 encoding** — `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")` in all tools
7. **ALWAYS add Tyler action items to `TODO_TYLER.md`** — don't assume he'll see chat
8. **ALWAYS run from project root** `f:\❤Music\` so relative paths resolve correctly

---

## Reference
- ❤Music project root: `f:\❤Music\`
- DB path: `f:\❤Music\src\data\heartmusic.db`
- ARTIST_PROFILE: `f:\❤Music\ARTIST_PROFILE.json`
