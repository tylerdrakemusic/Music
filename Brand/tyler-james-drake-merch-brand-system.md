# Tyler James Drake Merch Brand System

**Catalog:** `TJD-MERCH-TEE-PROMPTS`  
**Version:** 1.0.0  
**Scope:** Phase one, original music-world concepts only; tee prompts are the catalog format

## Brand Anchor

Tyler James Drake is a solo artist who blends rock, blues, and pop. The system
should feel like an authentic live-music artifact: guitar-led, emotionally
direct, and slightly weathered. The existing Brand assets and `ARTIST_PROFILE.json`
support a grounded artist identity, while Hyperthreat Studios is treated as a
recording-studio context, not as a new logo or merchandise mark.

## Themes

- Guitar, amplifier, cable, stage light, jukebox, porch, rooftop, and rehearsal-room details.
- Rebellious performance energy without celebrity imitation or superhero framing.
- Introspection after the set: night skies, city glow, quiet rooms, and earned perseverance.
- Cosmic music symbolism expressed through original abstract motion, constellations, and sound energy.
- Authentic live references that do not copy a venue, band, artist, team, instrument brand, or existing poster.

## Visual Rules

### Palette

Use dark garments and restrained warm accents. The default working palette is
ink black, washed charcoal, midnight blue, faded denim, smoke gray, aged cream,
muted gold, rust, and deep maroon. Start with two or three spot colors, then add
a fourth only when it improves separation. Avoid neon gradients, glossy 3D
rendering, and color fields that require transparent artwork.

### Typography

Use a condensed display face for short titles, a sturdy grotesque or humanist
sans for supporting text, and hand-lettered treatment only for a short approved
phrase. Typography must remain legible at tee scale. Do not imitate a known band
wordmark, tour poster, sports mark, or signature.

### Composition

Choose one primary subject and one supporting environment. Favor bold silhouettes,
asymmetric crop, clear negative space, stage-light diagonals, and a deliberate
focal point. Keep the main subject readable as a one-color shape. A back print
may carry the scene, while a front mark should be simple and secondary.

### Garment Colors

Preferred garments are black, washed charcoal, deep navy, dark forest, faded
denim, and occasionally dark brown. Use an aged cream or muted gray ink for
contrast. Any light garment requires a separate review because the system is
optimized for dark blanks.

### Print Guidance

- Write for opaque, separable artwork with a clear ink count.
- Prefer distressed screen-print texture, halftone, rough linework, and limited ink trapping.
- Avoid tiny text, photorealistic detail, transparent glow, unbounded gradients, and edge detail that disappears on fabric.
- Remove brand labels, readable third-party marks, recognizable signatures, and accidental logos.
- The prompt is not the artwork. Exact dimensions, separations, and production proofs remain future work.

## Naming

Prompt IDs use `TJD-TEE-NNN` and are never reused. Titles should be short,
distinct, and rooted in the scene. A title that is generic, slogan-like, or
likely to collide with an existing merch mark stays `concept_pending` until
Tyler approves a distinct naming lockup. The catalog version changes when a
prompt's meaning or approval state changes.

## Rights Exclusions

Phase one excludes recognizable artists, athletes, teams, logos, protected
characters, and religious or cultural figures unless separately licensed and
documented. It also excludes copied album art, signature instruments, branded
props, celebrity likenesses, and direct imitation of an existing merch design.
When in doubt, replace the reference with a fictional music-world equivalent.
The catalog preserves rejected source entries and their reasons so they are not
silently reintroduced.

## Operator Flow

1. Select a prompt by stable ID and confirm the intended garment/use, palette,
   and print notes.
2. Check provenance against `Brand/t-design prompts.txt`, `Brand/`, and
   `ARTIST_PROFILE.json`. Resolve any generic, duplicate, or rights-risk flags.
3. Present the concept only. Tyler approves, revises, or rejects the concept;
   set `concept_approval_status` accordingly.
4. After concept approval, write the provider/model and prompt version into the
   catalog only when a future provider is selected. No image generation is part
   of this phase.
5. The later exact-image gate is separate: inspect the generated image for
   likeness, marks, typography, composition, exclusions, and print readiness.
   Set `exact_image_approval_status` only after that exact image is reviewed.
6. Keep any later commerce output draft-only until a separate feature request
   covers listing, storefront, pricing, or publishing.

## Acceptance Checks

Before a prompt can leave `concept_pending`, confirm:

- It is an original music-world concept tied to Tyler James Drake's rock, blues,
  or pop identity.
- The title and ID are unique and the provenance is recorded.
- The garment color, intended use, palette, and print treatment are explicit.
- No recognizable artist, athlete, team, logo, protected character, or
  religious or cultural figure is present without a documented license.
- The composition has one clear subject and remains legible as limited-color
  print artwork.
- Concept approval is recorded before any exact-image approval.

No image generation, provider integration, transparent rendering, database
migration, storefront publishing, or commercial listing is included in phase
one. Future commerce remains draft-only.