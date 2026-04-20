# Completed Tasks Archive — ❤Music

This file archives completed tasks from TODO_AI.md and TODO_TYLER.md for historical reference and hygiene. Move any `[x]` or `[DONE]` items here during hygiene sweeps.

---

## 2026-04-17 Hygiene Sweep

### Phase 1: Foundation & Catalog Consolidation
- [x] Run `tools/catalog_index.py` to scan all source locations and populate the `catalog_index` table in the DB — 6,635 files indexed (2026-04-12)
- [x] Scan and ingest `f:\executedcode\Guitar` contents into `catalog_index` — 40 files (2026-04-12)

### Phase 2: Production Tracking (Bloom Album)
- [x] Define track list for Bloom in DB — title, status, key, BPM per track — 7 confirmed + 11 demos; Bitten/Is It Real key+BPM TBD (2026-04-12)

### Phase 3: Distribution & Release
- [x] Distribution decision — DistroKid. 2 EP singles already released. Account: https://distrokid.com/mymusic/

### Studio / Production
- [x] Provide Bloom track list — 18 tracks discovered from G:\TylerJamesDrake\rockstar\Bloom Album and cataloged in ARTIST_PROFILE.json. ~~Pending~~ Done.
- [x] E: drive — Confirmed: `E:\Masters\Bloom` (7 tracks: Is It Real, Abbey's Song, Same Thing, Bitten, Fly Away, Lighthouse, You Already Know). Added to bloom_sources in ARTIST_PROFILE.json.

---

## 2026-04-17 Hygiene Sweep (Pass 2)

### Phase 1: Foundation & Catalog Consolidation
- [x] Import track list for the Bloom album from `f:\Masters\Bloom Album` into the `tracks` table — all 7 tracks already existed; linked 7 master WAVs from `G:\TylerJamesDrake\rockstar\Bloom Album` (2026-04-17)

---

## 2026-04-18 Hygiene Sweep

### Tyler's Desires (Backlog)
| Task | Date | Notes |
|------|------|-------|
| Lyrics integration with setlist optimizer | 2026-04-17 | Full lyrics, HTML cue cards, auto-extracted themes. `tools/import_lyrics.py` (19 rows, 7 Bloom tracks), `Song` dataclass extended, `export_html()`, theme scoring in `transition_cost()`. Plan: `docs/protocols/lyrics-setlist-integration.md` |

---

(For future sweeps, append new completed items by date.)
