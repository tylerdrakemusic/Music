# ❤Music — AI Agent TODO

**Workflow:** Pick the top uncompleted task, mark it `[IN PROGRESS]`, execute, mark `[DONE]`, log in `docs/journal/`.

**Archive:** Completed tasks → `docs/archive/completed_tasks.md` (see file for full list)

---

## Infrastructure (Cross-Project — tracked in ⊕Workspace/TODO_AI.md)

- [ ] **MCP server analysis + install** — Playwright MCP is the highest-priority for ❤Music: replaces Edge headless subprocess in `tools/print_doc.py`, enables Spotify/DistroKid web automation. SQLite MCP would allow direct DB queries without Python scripts. Full candidate list and install decisions tracked in `⊕Workspace/TODO_AI.md`.

---

## Phase 1: Foundation & Catalog Consolidation

- [ ] Identify duplicate recordings across `f:\Masters`, `G:\TylerJamesDrake\rockstar`, and `f:\❤Music\recordings`
- [ ] Import existing lyrics files from `f:\❤Music\lyrics` into the `lyrics` table with file path refs
- [ ] Import CopperCreek metadata from `f:\❤Music\bands\copperCreek` into `artist_profiles` and related tables
- [ ] Parse `linkTyler.json` and populate the solo artist profile links in `artist_profiles`
- [ ] Review AI-generated recordings in `f:\❤Music\recordings` — flag quality per file
- [ ] Research building a Spotify Web API MCP server for VS Code — evaluate scope, auth (OAuth PKCE), useful endpoints (track metadata, streaming analytics for EP releases, playlist management), and whether to house in ❤Music or as a standalone tool

## Phase 2: Production Tracking (Bloom Album)

- [ ] Link master/rough files to each track in `recordings` table
- [ ] Build production status dashboard (`src/analysis/album_dashboard.py`)
- [ ] Design mixing/mastering checklist per track in `docs/protocols/`

## Phase 3: Distribution & Release

- [ ] Research distribution platforms (DistroKid, TuneCore, CD Baby) — cost/feature comparison
- [ ] Build release tracking in `releases` table
- [ ] Define metadata standard for all tracks (ISRC, credits, artwork)

## Phase 3.5: IP & Rights Infrastructure

- [ ] **DB migration** — Add `isrc`, `iswc`, `copyright_year`, `copyright_holder`, `license_type`, `ascap_work_id`, `pro_registered` columns to `tracks` table
- [ ] **DB migration** — Add `pandora_confirmed`, `iheart_confirmed`, `soundexchange_id` columns to `releases` table
- [ ] **Copyright metadata embedding** — Script to write `©`/`℗` tags into master file ID3v2 metadata
- [ ] **Audius upload script** — Use `@audius/sdk` with ISRC, ISWC, copyrightLine, `noAiUse: true` for human masters
- [ ] **SongDLC post-Bloom ops update** — Add copyright/rights completion gate inside the post-release metadata enrichment workflow
- [ ] **Self-hosted radio POC** — Icecast 2 + Liquidsoap on Windows/WSL, streaming Tyler's catalog (Phase α per IP_STRATEGY.md §7)
- [ ] **Quantum adapter for Icecast 2** — Consume entropy/proof artifacts from `⟨ψ⟩Quantum` for station-ID rotation, playlist variation, and broadcast proof (Phase β/γ per IP_STRATEGY.md §7)

## Tyler's Desires (Backlog — Soak Time)

*Lyrics integration with setlist optimizer — completed 2026-04-17 (archived)*

## Phase 4: Practice & Performance

- [ ] Build gig tracker CLI (`tools/log_gig.py`)
- [ ] Build practice session logger (`tools/log_practice.py`)
- [ ] Analyze practice consistency from `practice_log` table

---

## Architecture Decisions

| Decision | Date | Rationale |
|----------|------|-----------|
| Own SQLite DB (`heartmusic.db`) | 2026-04-06 | Music data is separate domain from health — clean separation |
| Catalog by reference, not migration | 2026-04-06 | Tyler requested no deletion/migration of source files — catalog_index stores paths |
| f:\❤Music\ | 2026-04-06 | Stays inside the tracked git repo at f:\ |
