# SongDLC — Post-Bloom Release Operations Pipeline

**Owner:** Tyler James Drake  
**Status:** ACTIVE — Tyler decisions recorded 2026-04-19  
**Created:** 2026-04-19  
**Scope:** Operating the release pipeline after the Bloom album is out in the world

---

## Purpose

This is **not** the songwriting-to-release pipeline for Bloom itself.

This document defines the operating pipeline **after Bloom album release**:
- verify distribution health
- maintain metadata and signatures
- push follow-on content and platform presence
- monitor audience signals
- feed what is learned into the next release cycle

The assumption is that Bloom is already released, masters already exist, and the work now is
release operations, verification, amplification, and lifecycle management.

---

## Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│  STAGE 0         STAGE 1         STAGE 2         STAGE 3        STAGE 4   STAGE 5  │
│  RELEASED   →   VERIFY      →   ENRICH      →   AMPLIFY     →  MONITOR  → REFINE   │
│  BASELINE       PRESENCE        METADATA         CHANNELS        SIGNALS    & LOOP   │
│  (1 day)        (1-7 days)      (1-3 days)       (1-2 weeks)     (ongoing) (ongoing)│
└─────────────────────────────────────────────────────────────────────────────────────┘
         │               │               │               │              │         │
     release row     store live      ISRC/links      radio/social    analytics   next move
     signatures      confirmed       completed       push live       reviewed    decided
```

---

## Stage 0: RELEASED BASELINE (same day)

**Gate:** Bloom is officially released and the canonical release record exists.

| Step | Action | Artifact | Owner |
|------|--------|----------|-------|
| 0.1 | Confirm Bloom release row exists in `releases` table | release_id | Agent |
| 0.2 | Confirm canonical masters in `f:\Masters\Bloom Album\` and catalog mirrors | file inventory | Agent |
| 0.3 | Confirm signature rows exist for release masters | `release_signatures` rows | Agent |
| 0.4 | Mark operational start date for post-release tracking | release ops timestamp | Agent |
| 0.5 | Freeze baseline metadata snapshot | metadata export/checklist | Agent |

**Exit criteria:** One authoritative baseline exists for Bloom across DB, files, and signatures.

---

## Stage 1: VERIFY PRESENCE (1-7 days)

**Gate:** Bloom must be provably live where Tyler expects it to be live.

| Platform | Verification Method | Status Field |
|----------|---------------------|--------------|
| Spotify | Artist page / Web API | `releases.spotify_confirmed` |
| Apple Music | Artist page / search | `releases.apple_confirmed` |
| Amazon Music | Artist page / search | `releases.amazon_confirmed` |
| YouTube Music | Search / official topic page | `releases.youtube_confirmed` |
| Deezer | Search / artist page | `releases.deezer_confirmed` |
| Pandora | AMP / search | `releases.pandora_confirmed` |
| iHeartRadio | Artist page / search | `releases.iheart_confirmed` |
| Bandcamp | Direct page check if used | `releases.bandcamp_confirmed` |
| Audius | Direct profile / API if used | `releases.audius_confirmed` |

| Step | Action | Artifact | Owner |
|------|--------|----------|-------|
| 1.1 | Verify DistroKid status for Bloom release | distrokid status note | Tyler/Agent |
| 1.2 | Confirm platform presence one platform at a time | confirmation flags | Agent |
| 1.3 | Capture platform URLs in DB | `platform_urls` or release fields | Agent |
| 1.4 | Flag missing or delayed platforms | exception list | Agent |
| 1.5 | Report gaps to Tyler | operational summary | Agent |

**Exit criteria:** Bloom is confirmed live, or the unresolved gaps are explicitly tracked.

---

## Stage 2: ENRICH METADATA (1-3 days)

**Gate:** Release exists publicly, but metadata must be completed to Tyler's standard.

| Step | Action | Artifact | Owner |
|------|--------|----------|-------|
| 2.1 | Store ISRCs returned by DistroKid | `tracks.isrc` | Agent |
| 2.2 | Add ISWC / PRO data once available | `tracks.iswc`, `ascap_work_id` | Tyler/Agent |
| 2.3 | Add copyright fields (`©`, `℗`, holder, year, license) | track metadata | Agent |
| 2.4 | Ensure Bloom art, credits, and release notes are consistent | metadata checklist | Tyler/Agent |
| 2.5 | Confirm no-AI / provenance distinctions for human vs AI assets | release notes / flags | Agent |
| 2.6 | Regenerate signature-backed metadata report | report artifact | Agent |

**Exit criteria:** Bloom metadata is complete enough that downstream channels can reuse it without guesswork.

---

## Stage 3: AMPLIFY CHANNELS (1-2 weeks)

**Gate:** Bloom is live and described correctly. Now the release has to be pushed.

| Step | Action | Artifact | Owner |
|------|--------|----------|-------|
| 3.1 | Update official links / link hub | updated links | Tyler/Agent |
| 3.2 | Claim or refresh artist surfaces (Pandora AMP, iHeart, Spotify for Artists) | claimed profiles | Tyler |
| 3.3 | Publish Bloom into self-hosted radio rotation | radio playlist update | Agent |
| 3.4 | Prepare Bandcamp and Audius direct-release versions if desired | uploads or backlog | Tyler/Agent |
| 3.5 | Push social / press / mailing list assets | campaign assets | Tyler |
| 3.6 | Tag standout tracks for playlist pitching or video follow-up | opportunity list | Tyler/Agent |

**Exit criteria:** Bloom is not just live; it is actively represented across Tyler-owned and third-party channels.

---

## Stage 4: MONITOR SIGNALS (ongoing)

**Gate:** Post-release performance needs to be observed, not guessed.

| Signal | Source | Why It Matters |
|--------|--------|----------------|
| Platform availability | Stores / artist dashboards | Detect broken or missing release presence |
| Listener counts | TJD Radio / platform dashboards | Identify traction and listener behavior |
| Track preference | Repeat plays, favorites, saves | Find strongest Bloom songs |
| Provenance integrity | Signature checks / file watch | Detect drift or tampering |
| Rights progress | ASCAP / copyright / metadata | Close legal and royalty gaps |

| Step | Action | Artifact | Owner |
|------|--------|----------|-------|
| 4.1 | Re-check key platforms at fixed intervals | verification log | Agent |
| 4.2 | Monitor self-hosted radio usage and now-playing history | radio ops summary | Agent |
| 4.3 | Review platform analytics as they arrive | performance notes | Tyler/Agent |
| 4.4 | Re-run signature/integrity checks if masters change | updated signatures | Agent |
| 4.5 | Identify which Bloom tracks merit videos, lyric clips, or live focus | follow-up list | Tyler |

**Exit criteria:** Bloom has a living operational picture, not a one-time launch snapshot.

---

## Stage 5: REFINE AND LOOP (ongoing)

**Gate:** What Bloom teaches should directly shape the next release cycle.

| Step | Action | Artifact | Owner |
|------|--------|----------|-------|
| 5.1 | Record post-release lessons | retrospective note | Agent |
| 5.2 | Update release playbooks, metadata rules, and automation gaps | revised docs / TODOs | Agent |
| 5.3 | Identify best-performing Bloom tracks for sustained push | priority shortlist | Tyler/Agent |
| 5.4 | Feed lessons into next single / EP / album workflow | next-cycle checklist | Tyler/Agent |
| 5.5 | Decide whether Bloom enters catalog-maintenance mode or active campaign mode | operating decision | Tyler |

**Exit criteria:** Bloom informs the next move instead of becoming a dead archive.

---

## Operational Guardrails

| Check | Tool / Method | Failure Action |
|-------|---------------|----------------|
| Canonical master integrity | `sig_analyzer.py` / DB comparison | HALT metadata or re-upload work until resolved |
| Platform presence drift | manual/API verification | Open issue and recheck stores |
| Missing rights metadata | release checklist | Fill gaps before secondary distribution push |
| Broken owned links | link audit | Update immediately |
| Radio asset mismatch | playlist vs signed masters | Replace with canonical master |

**Rule:** Post-release operations never override the canonical master or release metadata silently. Any fix must be traceable.

---

## Bloom-Specific Notes

- Bloom is the first release this pipeline is written around.
- **Platform priority:** Broad completeness across all major stores is the primary Stage 1 goal — verify all platforms before shifting to focused promotion.
- **TJD Radio:** Full Bloom catalog enters permanent rotation immediately after release (not just selected tracks).
- **Bandcamp:** Primary post-release expansion target, not a secondary option. Treated the same as mainstream DSP confirmation.
- **Second-wave track selection:** TBD — deferred until platform analytics and listener data are available. Agent should surface candidate tracks once signal data arrives (Stage 4).
- Quantum signatures remain relevant post-release for integrity, provenance, and auditability.

---

## Agent Responsibilities

| Agent | Stages | Role |
|-------|--------|------|
| **❤music-orchestrator** | All | Coordinates Bloom post-release operations |
| **❤music-catalog** | 0, 4 | Canonical file tracking, catalog health |
| **❤music-production** | 2, 5 | Metadata, credits, release learnings |
| **❤music-signatures** | 0, 2, 4 | Integrity verification and provenance maintenance |
| **❤music-performance** | 3, 4 | Track live/playback opportunities if relevant |
| **⊕workspace-ci** | 2, 5 | Tooling, automation, repo hygiene |

---

## Implementation Phases

### Phase A: Bloom Release Ops Baseline
- [ ] Confirm Bloom release row and all platform status fields
- [ ] Add missing release verification columns / URLs if absent
- [ ] Build a Bloom post-release checklist view
- [ ] Capture canonical metadata snapshot

### Phase B: Automation
- [ ] Platform verification automation for Bloom store presence
- [ ] Radio rotation integration for Bloom release blocks
- [ ] Metadata completeness validator for released tracks
- [ ] Integrity drift checks for canonical masters

### Phase C: Dashboard Integration
- [ ] Add a Bloom release-ops dashboard view
- [ ] Show platform confirmation status and direct links
- [ ] Show radio exposure / now-playing history for Bloom tracks

---

## Open Questions for Tyler

1. After Bloom release, is the priority broad platform completeness or focused promotion on a few channels first?  
   **→ Broad platform completeness first. Confirm presence across all major stores before concentrating promotional push.**

2. Should Bloom go immediately into permanent TJD Radio rotation, or only selected tracks?  
   **→ Yes — full Bloom catalog into permanent TJD Radio rotation immediately after release.**

3. Is Bandcamp part of the post-Bloom operating plan, or should it stay secondary?  
   **→ Yes — Bandcamp is a primary target in the post-Bloom expansion plan.**

4. Which Bloom tracks deserve the strongest second-wave push after release?  
   **→ TBD — to be decided once platform analytics and listener data are in.**