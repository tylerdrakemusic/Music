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

## 7. Self-Hosted Radio Station — Quantum Integration for Icecast 2

### Vision
The self-hosted station should standardize on **Icecast 2 as the broadcast core** and treat
quantum capabilities as an upstream integration layer, not as a replacement for the radio
stack. The goal is a 24/7 Tyler-owned station where playlist automation, station-ID rotation,
proof/signature generation, and stream secrets can consume entropy or signed artifacts from
`⟨ψ⟩Quantum`, while the actual audio delivery remains conventional and reliable.

### Scope Boundary
- **❤Music owns broadcast behavior**: playlists, station IDs, metadata, listener UX, rights rules.
- **⟨ψ⟩Quantum owns quantum services**: entropy generation, signed tokens/artifacts, cache fills,
  and any IBM Quantum or QRNG integration.
- **Integration contract**: ❤Music consumes exported quantum outputs through a thin adapter.
  Do not embed quantum hardware/client logic directly inside the Icecast/Liquidsoap layer.

### Architecture
```
┌─────────────────────────────────────────────────────────────────────┐
│                           TJD Radio Station                         │
├──────────────┬──────────────────────┬──────────────┬───────────────┤
│ Playlist /   │ Quantum Integration  │ Icecast 2    │ Web Player /  │
│ Liquidsoap   │ Adapter              │ (broadcast)  │ Dashboard      │
│              │                      │              │               │
│ Crossfade    │ Pull entropy /       │ Serve MP3 /  │ Show now      │
│ Station IDs  │ signed artifacts     │ OGG mount    │ playing,      │
│ Catalog mix  │ from ⟨ψ⟩Quantum      │ metadata     │ listener data │
└──────────────┴──────────────────────┴──────────────┴───────────────┘
        │                    │                    │
        │                    └──── optional QRNG-driven decisions
        │                         (rotation, IDs, proof)
        └──── source audio + policy rules
```

### What Quantum Actually Does Here
Quantum integration should be limited to areas where nondeterminism, attestability, or secret
generation add value:

| Integration Point | Quantum Role | Why It Matters |
|-------------------|--------------|----------------|
| Station ID rotation | Entropy source for bumper/jingle selection | Prevents predictable loops and makes the station feel less scripted |
| Playlist variation | Optional entropy input into weighted rotation | Adds novelty without changing Tyler's curation authority |
| Broadcast proof | Signed/hash artifacts per broadcast window | Gives a verifiable chain for what aired and when |
| Stream/admin secrets | Quantum-generated passwords or keys | Better key material for Icecast admin/source credentials |
| Release/event tie-ins | Quantum-seeded special blocks | Useful for premieres, listening parties, or collectible provenance events |

### Technology Stack
| Component | Tool | License | Notes |
|-----------|------|---------|-------|
| Streaming server | **Icecast 2** | GPL-2.0 | Authoritative broadcast server and mountpoint host |
| Source client/scheduler | **Liquidsoap** | GPL-2.0 | Stable source engine for rotation, crossfade, live inserts |
| Quantum service | **⟨ψ⟩Quantum adapter** | Internal | Supplies entropy, proofs, or signed artifacts through a clean interface |
| Optional AI content | **Suno API** | Commercial | Still allowed for interludes/IDs, but not the architectural centerpiece |
| Hosting | VPS (DigitalOcean $6/mo) or self-hosted | — | ~50 listeners at 128kbps = ~50 Mbps |
| Web player | HTML5 `<audio>` + JS | — | Embed on Tyler's site |
| Metadata | Icecast admin / mount metadata | — | Now playing, history, badges, proof hooks |

### Integration Pattern
1. ❤Music builds the playlist and station policy.
2. A small adapter requests entropy or a signed artifact from `⟨ψ⟩Quantum`.
3. Liquidsoap/Icecast consume the resulting decision or credential.
4. The dashboard surfaces the result as metadata, not as raw quantum internals.

**Rule:** if the radio must keep running when quantum services are offline, the system should
fall back to deterministic local behavior. Quantum is a value-add, not a single point of failure.

### Liquidsoap Example with Quantum-Driven Inputs
```liquidsoap
# TJD Radio — Icecast 2 with quantum-assisted rotation
tyler_originals = playlist("~/music/tyler/originals.m3u")
station_ids = playlist("~/music/jingles/station_ids.m3u")

# A helper outside Liquidsoap can write the next block selection using
# entropy/signals from ⟨ψ⟩Quantum. Liquidsoap just consumes the result.
featured_block = playlist("~/music/runtime/quantum_selected_block.m3u")

radio = rotate(weights=[3, 1, 1], [tyler_originals, station_ids, featured_block])
radio = crossfade(radio)

output.icecast(%mp3(bitrate=192),
  host="localhost", port=8000,
  password="source-password-from-quantum-or-vault",
  mount="/stream",
  radio)
```

### Legal Considerations for Self-Hosted Radio
| Issue | Requirement | Cost |
|-------|-------------|------|
| **Streaming license** | SoundExchange license for internet radio | ~$500/yr minimum |
| **ASCAP license** | Performance license for compositions | ~$400/yr minimum |
| **BMI license** | If playing any BMI-registered works | ~$400/yr minimum |
| **Own music only** | If streaming ONLY Tyler's own music → **no license needed** | Free |
| **Suno AI content** | Per Suno TOS: Pro/Premier subscribers own Output. Commercial use OK on paid tier | Suno subscription |

**Key insight:** If the station plays **only Tyler's original recordings** plus any
Tyler-controlled bumpers/interludes, no performance licenses are needed. If Suno content is
used, it must come from a paid tier with commercial rights and should be treated as a separate
rights-tracked asset class. The moment you play other artists' music, you need SoundExchange
+ PRO licenses.

### Suno Commercial Rights (from TOS, March 2026)
> "If you are a user who has subscribed to the Pro or Premier paid tier of the
> Service, Suno hereby assigns to you all of its right, title and interest in
> and to any Output owned by Suno and generated from Submissions made by you
> through the Service during the term of your paid-tier subscription."

**BUT:** "Suno makes no representation or warranty to you that any copyright will
vest in any Output." — AI-generated content has uncertain copyright status under
current U.S. law (Thaler v. Vidal, Copyright Office guidance 2023-2025).

### Phase Plan
| Phase | Action | Effort | Cost |
|-------|--------|--------|------|
| **α** | Proof-of-concept: Icecast 2 + Liquidsoap streaming Tyler's catalog | 1 weekend | Free |
| **β** | Add quantum adapter for entropy-driven station IDs / playlist variation | 1-2 days | Free if using existing ⟨ψ⟩Quantum cache |
| **γ** | Add signed broadcast proof artifacts + quantum-generated stream credentials | 1 day | Free |
| **δ** | Deploy to VPS + web player/dashboard integration | 1 day | $6/mo |

### Recommendation
For strategy purposes, the correct framing is:

> **Icecast 2 is the radio platform. Quantum is the integration layer.**

That preserves broadcast stability, keeps project boundaries clean, and gives Tyler a distinctive
technical differentiator without creating unnecessary licensing or operations risk.

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
- [ ] POC: Icecast + Liquidsoap self-hosted radio (Phase α)
