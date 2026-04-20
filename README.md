# ❤Music

Tyler James Drake's music project management system — solo artist, CopperCreek band, and album production hub.

## What This Is

A structured project to organize, track, and drive Tyler's music career:

- **Solo artist** — Tyler James Drake, producing the *Bloom* album at Hyperthreat Studios
- **Band** — CopperCreek
- **Catalog** — Masters, roughs, lyrics, guitar work, AI-generated recordings
- **Production tracking** — Album status, track progress, mixing/mastering pipeline
- **Performance** — Gig management, setlists, practice logging
- **Distribution** — Release planning across streaming platforms

## Key Paths

| Resource | Path |
|----------|------|
| **Project Root** | `f:\executedcode\❤Music\` |
| **Database** | `src/data/heartmusic.db` |
| **Python Executable** | `C:\G\python.exe` |
| **Artist Profile** | `ARTIST_PROFILE.json` |

## Source File Locations (Read-Only — Do Not Delete)

| Content | Path |
|---------|------|
| Masters | `f:\Masters\` |
| Rockstar backup | `G:\TylerJamesDrake\rockstar\` |
| Recordings | `f:\executedcode\recordings\` |
| Lyrics | `f:\executedcode\lyrics\` |
| Guitar | `f:\executedcode\Guitar\` |
| Bands (CopperCreek) | `f:\executedcode\bands\` |
| Sheet Music | `C:\Users\tyler\Documents` |

## Quick Start

```python
from utils.init_db import get_connection
conn = get_connection()
```

```
# Initialize DB
C:\G\python.exe src/utils/init_db.py

# Run catalog index (scan all source locations)
C:\G\python.exe tools/catalog_index.py
```

## DB Schema

| Table | Purpose |
|-------|---------|
| `artist_profiles` | Tyler solo + CopperCreek band |
| `albums` | Bloom, EP, etc. with status |
| `tracks` | Per-song metadata (key, BPM, status) |
| `recordings` | File paths to masters/roughs with quality rating |
| `lyrics` | Lyric content or file refs per track |
| `gigs` | Past/upcoming performances |
| `practice_log` | Practice sessions |
| `gear` | Instruments and equipment |
| `collaborators` | Producers, bandmates, engineers |
| `budget` | Studio costs, gear, distribution |
| `releases` | Platform links and release dates |
| `catalog_index` | Flat index of all source files by path |
