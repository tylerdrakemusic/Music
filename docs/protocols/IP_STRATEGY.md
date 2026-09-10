# ❤Music — Intellectual Property & Rights Strategy

**Owner:** Tyler James Drake  
**Created:** 2026-04-19  
**Status:** DRAFT — Tyler review required  

---

## 1. Copyright (All Rights Reserved — Default)

Tyler owns copyright on all original compositions (lyrics + melody) and sound recordings
produced at Hyperthreat Studios as **work of authorship** under U.S. Copyright Act (17 U.S.C.).

### Registration
| Action | Cost | Priority | Status |
|--------|------|----------|--------|
| Register compositions with US Copyright Office (copyright.gov) | $65/single, $85/group | HIGH | ❌ Not started |
| Register sound recordings with US Copyright Office | $65/single, $85/group | HIGH | ❌ Not started |
| Add `©` + year + "Tyler James Drake" to all release metadata | Free | IMMEDIATE | ❌ Not started |

**Why register?** Registration is required before filing infringement lawsuits and enables
statutory damages ($150K/infringement) + attorney's fees. Group registration of up to 10
unpublished works is cost-effective.

### Copyright Notice Format
```
© 2026 Tyler James Drake. All rights reserved.
℗ 2026 Tyler James Drake (sound recording copyright)
```
- `©` = composition (lyrics + music) copyright
- `℗` = phonogram/sound recording copyright

### Metadata Embedding
Every distributed master file MUST contain:
- ID3v2 tag `TCOP` (copyright): `© 2026 Tyler James Drake`
- ID3v2 tag `TPUB` (publisher): `Tyler James Drake` (or publishing entity if established)
- ISRC code (from DistroKid)
- ISWC code (from ASCAP, once registered)

---

## 2. Copyleft / Creative Commons — SELECTIVE USE

**Default stance: All Rights Reserved.** Copyleft (CC licenses) only for strategic releases.

| License | Use Case | Tracks |
|---------|----------|--------|
| All Rights Reserved | All commercial releases (Bloom, EP, singles) | Default |
| CC BY-NC-SA 4.0 | Promotional/demo tracks, CopperCreek covers for exposure | Case-by-case |
| CC BY 4.0 | Stems/samples shared for remix community (Audius remixable) | Future consideration |

**Rule:** Never CC-license a track that will be commercially distributed through DistroKid.
CC and commercial distribution create legal confusion.

### Open Source Code
The repo itself (`f:\executedcode\❤Music\`) contains tools, not music. Tools can be
licensed separately (MIT/Apache-2.0) if Tyler wants to share `sig_analyzer.py` or
dashboard code. Music files in `catalog/` and `f:\Masters\` are **never** open-sourced.

---

## 3. ASCAP — Performance Rights Organization (PRO)

### What ASCAP Does
ASCAP collects **performance royalties** when your music is:
- Played on radio (terrestrial, satellite, internet)
- Streamed on Spotify, Apple Music, Pandora, etc.
- Performed live at venues
- Used in TV, film, commercials

### Registration
| Action | Cost | Priority | Status |
|--------|------|----------|--------|
| Join ASCAP as **songwriter** | $50 one-time | HIGH | ❌ Not started |
| Join ASCAP as **publisher** (self-publish) | $50 one-time | MEDIUM | ❌ Not started |
| Register each composition (title, writers, splits) | Free | HIGH (per release) | ❌ Not started |

**Tyler action required:** Go to ascap.com → "Join ASCAP" → Select Writer membership.
After joining, register every original composition. This generates an **ISWC** (International
Standard Musical Work Code) — the composition-level identifier (distinct from ISRC which
is recording-level).

### ASCAP vs BMI vs SESAC
- **ASCAP** — open membership, $50 one-time, songwriter-friendly, good for indie
- **BMI** — free for songwriters, $250 for publishers, equally good
- **SESAC** — invite-only, not applicable

**Recommendation:** ASCAP or BMI. Pick one. You **cannot** be a member of both for the
same works. ASCAP is the recommendation here due to simplicity and one-time fee.

### CopperCreek Splits
If CopperCreek songs have co-writers, register splits in ASCAP. Default: equal split
unless agreed otherwise. Document in `heartmusic.db` → `collaborators` table.

---

## 4. ISRC — International Standard Recording Code

### Current Strategy
ISRCs are auto-assigned by **DistroKid** at upload time. No separate registrant prefix needed.

### Audius ISRC Support ✅
Audius **natively supports ISRC** in their track metadata. From the SDK:
```
CreateTrackRequestBody:
  isrc: string  // International Standard Recording Code (Optional)
  iswc: string  // International Standard Musical Work Code (Optional)
  copyrightLine: CopyrightLine  // Copyright line (Optional)
  producerCopyrightLine: ProducerCopyrightLine  // Producer copyright line (Optional)
```

**Workflow:** After DistroKid assigns ISRC → store in `tracks` table → include when
uploading to Audius via SDK.

### Audius Additional Metadata
Audius also supports DDEX standard fields:
- `rightsController` — DdexRightsController (name, roles, rights share)
- `resourceContributors` — DdexResourceContributor[] (name, roles, sequence)
- `noAiUse` — boolean flag to prohibit AI training use
- `territoryCodes` — country-level distribution control
- `license` — license type string

**Recommendation:** Set `noAiUse: true` for all human-master tracks from Hyperthreat.
Set copyright line: `© 2026 Tyler James Drake`.

---

## 5. Distribution Channels — Full Matrix

### DistroKid-Handled (Automatic)
DistroKid distributes to **150+ platforms** including:

| Platform | Type | ISRC | Notes |
|----------|------|------|-------|
| Spotify | Streaming | Auto (DK) | Primary revenue. Claim via Spotify for Artists |
| Apple Music | Streaming | Auto (DK) | Also iTunes Store for purchases |
| Amazon Music | Streaming | Auto (DK) | + Alexa voice requests |
| YouTube Music | Streaming | Auto (DK) | + Content ID for video claims |
| **Pandora** | Streaming/Radio | Auto (DK) | ✅ **Included in DistroKid** |
| **iHeartRadio** | Streaming/Radio | Auto (DK) | ✅ **Included in DistroKid** |
| Tidal | Streaming | Auto (DK) | Hi-fi audience |
| Deezer | Streaming | Auto (DK) | International reach |
| TikTok / Instagram | Social | Auto (DK) | Short-form viral potential |
| Facebook / IG Stories | Social | Auto (DK) | Sound Collection |

### Direct Upload Required
| Platform | Type | ISRC Support | Automation Plan |
|----------|------|-------------|-----------------|
| **Bandcamp** | Direct sales | Manual entry | Playwright (Phase B) |
| **Audius** | Decentralized streaming | ✅ Native ISRC field | SDK automation (Phase B) |

### Not Yet in Pipeline
| Platform | Type | How to Get On | Priority |
|----------|------|---------------|----------|
| **Classical radio stations** | Terrestrial radio | Direct submission to program directors; radio promoter service | LOW — Tyler's genre is rock/blues/folk, not classical |
| **College radio (CMJ)** | Terrestrial radio | Submit to college stations; services like Yangaroo, PromotionDept | MEDIUM — good for indie exposure |
| **SiriusXM** | Satellite radio | DistroKid may deliver; also direct artist submission portal | MEDIUM |
| **SoundCloud** | Streaming | Direct upload | LOW — Audius serves same niche |

---

## 6. Pandora & iHeartRadio — Details

### Pandora
- **Delivery:** DistroKid handles delivery automatically. Pandora is in the default store list.
- **Royalties:** Pandora pays per-stream. Rate varies (~$0.003-0.007/stream).
- **AMP (Artist Marketing Platform):** Claim your Pandora artist profile at amp.pandora.com
  to access analytics, promote tracks to listeners, and create artist messages.
- **Radio algorithm:** Pandora's Music Genome Project creates "stations" from your track's
  audio characteristics. Genre-correct metadata improves algorithmic placement.

### iHeartRadio
- **Delivery:** DistroKid handles delivery automatically. iHeartRadio is in the default store list.
- **Royalties:** Per-stream through iHeartRadio digital. Terrestrial iHeart FM stations
  pay through ASCAP/BMI (another reason to register).
- **Artist Radio:** iHeartRadio creates algorithmic stations similar to Pandora.
- **Terrestrial play:** Getting on actual iHeart FM stations requires radio promotion
  (playlist pitching to program directors). This is a separate effort from digital distribution.

### Classical Radio Stations
Tyler's genre (rock/blues/folk/alternative) doesn't naturally fit classical stations.
If the intent is radio in general:
- **College radio** is the best indie entry point
- **NPR / public radio** for folk/alternative crossover
- **Local Colorado stations** — KBCO (Boulder), KTCL, CPR Music

---

## 8. Suno AI Copyright — Special Handling

### The Problem
U.S. Copyright Office has stated that purely AI-generated works **cannot be copyrighted**
(no human authorship). However, works with **sufficient human creative input** (selecting,
arranging, curating AI output) may qualify for partial copyright.

### Tyler's Workflow
1. Tyler writes lyrics + melody → **human authorship (copyrightable)**
2. Suno generates a master/arrangement → **AI output (uncertain copyright)**
3. Human master at Hyperthreat: Tyler + engineer mix/master → **human authorship (copyrightable)**

### Strategy
| Master Type | Copyright Status | Recommendation |
|-------------|-----------------|----------------|
| Hyperthreat (human) | Full copyright (composition + recording) | Register with USCO |
| Suno AI master | Uncertain — composition copyrightable, AI recording may not be | Document human input |
| Suno AI + human edits | Likely copyrightable if human edits are substantial | Document edits |

### Documentation Protocol
For every Suno-generated track:
1. Save the Suno prompt/input (proves human creative direction)
2. Save the original Suno output
3. Document any human edits/selection (which of N generations was chosen, why)
4. Store provenance chain in `release_signatures` table (`source_platform = 'suno'`)

This creates an evidence trail supporting human authorship claims.

---

## 9. Database Schema Updates Needed

### `tracks` table additions
| Column | Type | Purpose |
|--------|------|---------|
| `isrc` | TEXT | ISRC code from DistroKid |
| `iswc` | TEXT | ISWC code from ASCAP |
| `copyright_year` | INTEGER | Year of copyright |
| `copyright_holder` | TEXT | Default: "Tyler James Drake" |
| `license_type` | TEXT | "all_rights_reserved" / "cc-by-nc-sa-4.0" / etc. |
| `ascap_work_id` | TEXT | ASCAP work registration ID |
| `pro_registered` | INTEGER | 0/1 — registered with PRO |

### `releases` table additions
| Column | Type | Purpose |
|--------|------|---------|
| `pandora_confirmed` | INTEGER | Verified on Pandora |
| `iheart_confirmed` | INTEGER | Verified on iHeartRadio |
| `soundexchange_id` | TEXT | SoundExchange registration ID |

---

## 10. Action Items

### Tyler Must Do (added to TODO_TYLER.md)
- [ ] **Register with ASCAP** — ascap.com, $50 one-time, songwriter membership
- [ ] **Register compositions** — After ASCAP membership, register Marigold, Get Out, What I Do
- [ ] **US Copyright Office** — Register EP (Marigold, Get Out, What I Do) as group, $85
- [ ] **Decide on Suno subscription tier** — Pro ($10/mo) or Premier ($30/mo) for commercial rights
- [ ] **Claim Pandora AMP profile** — amp.pandora.com
- [ ] **Claim iHeartRadio artist profile** — artists.iheart.com

### Agent Will Do
- [ ] Add ISRC/ISWC/copyright columns to `tracks` table (migration)
- [ ] Add Pandora/iHeart confirmation columns to `releases` table (migration)
- [ ] Embed copyright metadata in all master files (ID3 tags)
- [ ] Build Audius upload script with ISRC + copyright fields
- [ ] Update SongDLC post-Bloom release ops pipeline with copyright and rights-completion gates
