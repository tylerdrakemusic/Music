# Studio Wiring: JBL 2600 Passive PA Speakers

**Status:** Revised — 2026-05-17 (Denon AVR-1000 inherited, Crown/Mackie plans dropped)  
**Gear ID in heartmusic.db:** 27

---

## 📦 Procurement Log

| Item | Order # | Vendor | Date | Status | Notes |
|------|---------|--------|------|--------|-------|
| Mackie Big Knob Passive | MAC10881259 | shop.mackie.com | 2026-05-10 | ❌ Cancelled (vendor) | Replaced by Denon AVR-1000 |
| Crown XLS 1002 | — | — | — | 🚫 Dropped | Denon AVR-1000 provides amplification |
| Denon AVR-1000 | — | Inherited | 2026-05-17 | ✅ In hand | AV receiver — powers JBL 2600 + Sterling center |
| Sterling center speaker | — | Inherited | 2026-05-17 | ✅ In hand | Passive, standard speaker wire |
| Speaker wire (JBLs + Sterling) | — | TBD | — | Pending | 14 AWG OFC, spring clips / binding posts |
| TRS → RCA cable (Scarlett → Denon) | — | TBD | — | Pending | 1/4" TRS to dual RCA, ~6 ft |

---

## ✅ Revised Signal Chain — 2026-05-17

The Mackie Big Knob and Crown XLS 1002 plan is **superseded** by the inherited Denon AVR-1000, which provides both amplification and volume control at zero cost.

| Component | Source | Cost | Purpose |
|-----------|--------|------|---------| 
| Focusrite Scarlett 2i2 | Owned | — | Interface, guitar/mic input, feeds HS8s directly |
| Yamaha HS8 × 2 | Owned | — | Active studio monitors, direct from Scarlett |
| **Denon AVR-1000** | **Inherited** | **$0** | AV receiver — powers passive speakers, volume knob |
| **JBL 2600 × 2** | **Inherited** | **$0** | Passive PA — Denon Front L/R outputs |
| **Sterling center speaker** | **Inherited** | **$0** | Passive center — Denon Center output |

**Total to go live:** ~$25–35 (one cable + speaker wire)

**Signal chain — confirmed from unit inspection (2026-05-17):**
```
Scarlett 2i2
  ├── REAR Out 1 (1/4" TRS) → Yamaha HS8 L  ← always connected, studio monitoring
  ├── REAR Out 2 (1/4" TRS) → Yamaha HS8 R  ← always connected, studio monitoring
  └── FRONT Headphone Out (1/4" TRS stereo) → [1/4" TRS → dual RCA cable] → Denon AVR-1000 CD input
                                                  ├── Front L → JBL 2600 (L)  [speaker wire → spring clips]
                                                  ├── Front R → JBL 2600 (R)  [speaker wire → spring clips]
                                                  └── Center  → Sterling center  [speaker wire]
```

**Why the headphone output is the key:**
The Scarlett 2i2 only has 2 rear line outputs (Out 1 and Out 2). Using the **front-panel headphone output** as the Denon feed means both paths can run simultaneously — HS8s from rear outputs, Denon/JBLs from headphone out. No Y-splitter, no monitor controller, no mode switching required.

**Volume controls:**
- HS8s: Scarlett main monitor knob (rear panel or front knob controls rear outputs)
- Denon/JBLs: Scarlett headphone knob + Denon master volume knob

**Denon input notes (confirmed from unit — 2026-05-17):**
- Input connectors: **standard RCA (phono/cinch)** — the circular connectors with center pin
- Available inputs: PHONO, CD, DAT/TAPE, VDP/DBS, VCR
- **Use: CD or DAT/TAPE** — these are flat line-level inputs
- **⚠ Do NOT use PHONO** — the PHONO input has a built-in RIAA equalization preamp for turntables; it will add bass boost and treble cut to anything you plug into it
- Impedance spec on speaker outputs: **6–16 Ω** (JBL 2600 at 8Ω is perfectly within range)

**See `docs/studio-wiring-decision.mmd` for the full Mermaid diagram.**

**One cable to buy (~$12–15):**
- 1× **1/4" TRS male to dual RCA male**, ~6 ft — "stereo headphone to RCA" adapter cable  
  (Scarlett front HP out → Denon CD input L/R)
- Speaker wire, 14 AWG OFC: Denon binding posts → JBL spring clips × 2 + Sterling binding posts

---

---

## JBL 2600 Specs

| Spec | Value |
|------|-------|
| Type | Passive 3-Way PA Speaker |
| Program Power | 300W |
| Peak Power | 600W |
| Impedance | 8Ω |
| Frequency Response | 55Hz – 16kHz |
| Sensitivity | 96 dB SPL (1W/1m) |
| Max SPL | 119 dB |
| Input Connectors | Speakon NL4 + 1/4" TRS |
| Woofer | 12" |
| HF Driver | 1.5" titanium compression driver |
| Horn Coverage | 90° H × 50° V |
| Weight | ~27 kg (60 lb) per cabinet |

---

## Why the Scarlett 2i2 Cannot Drive These Directly

The **Focusrite Scarlett 2i2** outputs are **line-level balanced TRS** signals — roughly +4 dBu / ~1.23V. These are designed to feed **active/powered monitors** (like the Yamaha HS8s, which have built-in 120W amplifiers) or other line-level devices.

The **JBL 2600 is passive** — it has no internal amplifier. It requires a **speaker-level signal**: high current, typically 10–100W of amplified power at 8Ω. Connecting a line-level output directly to a passive speaker produces:
- Extremely low/no audible volume
- Potential damage to the interface output stage over time

**The chain must be:**

```
Scarlett 2i2 (line out) → Power Amplifier → JBL 2600 (passive)
```

---

## Signal Chain Wiring Diagram

```
Scarlett 2i2 Out 1+2 (1/4" TRS)
        │
        ▼ [TRS → dual RCA cable]
Denon AVR-1000 Stereo Input (RCA L/R)
        │
        ├── Front L (speaker wire) → JBL 2600 (L) spring clips
        ├── Front R (speaker wire) → JBL 2600 (R) spring clips
        └── Center  (speaker wire) → Sterling center speaker

Scarlett 2i2 Out 1 → Yamaha HS8 L  (TRS direct, active monitor)
Scarlett 2i2 Out 2 → Yamaha HS8 R  (TRS direct, active monitor)
```

**Cable 1 (Interface → Denon):**
1/4" TRS male to dual RCA male (Y-split stereo), ~6 ft. ~$10–15.

**Cable 2 (Denon → Speakers):**
Standard 14 AWG OFC speaker wire. Denon binding posts → JBL spring clips and Sterling binding posts.

---

## Amplifier Notes (Denon AVR-1000)

The inherited **Denon AVR-1000** is a home AV receiver providing:
- Built-in multi-channel amplification (typically 75–100W × 5 @ 8Ω)
- RCA analog stereo inputs (AUX, CD, etc.)
- Speaker output terminals: Front L/R, Center, Surround L/R
- Master volume knob — replaces Mackie Big Knob controller role
- JBL 2600 (8Ω, 300W program) is well within safe operating range
- Sterling center speaker (passive, 8Ω typical) driven from Center channel

---

## Stereo vs. Mono Considerations

- The Scarlett 2i2 has **2 line outputs** (L + R) — run one cable to each amp channel for stereo use.
- If using the JBL 2600s as **PA reinforcement** (mono), bridge the amp channels (see your amp's manual) for ~700W mono into the speaker. Do not exceed the speaker's 600W peak.

---

## Next Steps (Purchasing Decision — Tyler's Call)

1. ✅ **Denon AVR-1000** — IN HAND (inherited 2026-05-17)
2. ✅ **JBL 2600 × 2** — IN HAND (inherited)
3. ✅ **Sterling center speaker** — IN HAND (inherited)
4. **Cables needed (~$30–40 total):**
   - 1× TRS 1/4" male to dual RCA male, ~6 ft (Scarlett → Denon input)
   - 14 AWG OFC speaker wire (Denon binding posts → JBL spring clips × 2 + Sterling)

**Total remaining cost:** ~$30–40 (cables only)

---

## References

- JBL 2600 Product Page / Spec Sheet: [JBL Professional](https://jblpro.com)
- Crown XLS Series: [Crown Audio](https://crownaudio.com)
- Focusrite Scarlett 2i2 Manual: 2 balanced TRS line outputs, max +14 dBu, 2Ω minimum load (line-level)
