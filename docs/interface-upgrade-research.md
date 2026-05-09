# Audio Interface Upgrade Research — Dual Monitor Setup

**Date:** 2026-05-09  
**Status:** CLOSED — Decision locked. See chosen path below.  
**Context:** Evaluate interface upgrades (or alternatives) to support guitar input, mic input, Yamaha HS8 active monitors, and JBL 2600 passive speakers (via power amp).

---

## ✅ Chosen Path (Locked 2026-05-09)

**Option A selected:** Monitor controller (Mackie Big Knob Passive) + power amp (Crown XLS 1002).  
Interface upgrade deferred — the Scarlett 2i2 already covers guitar Hi-Z and mic XLR. No gap there.  
Full chain and wiring in `docs/studio-wiring-jbl2600.md`.

**Future open:** If simultaneous dual-monitor output or more inputs are needed later, revisit Options B/C below (Scarlett 4i4 or MOTU M4).

---

---

## Current Setup Analysis

| Device | Role | Limitation |
|--------|------|------------|
| Focusrite Scarlett 2i2 | Interface | **Only 2 line outputs** — can only drive one speaker pair at a time |
| Yamaha HS8 | Active monitors | Accepts balanced TRS 1/4" or XLR — works fine with any interface |
| JBL 2600 | Passive PA | Needs power amp + interface output — requires 2 additional outputs |

### What the 2i2 Already Handles Fine
- **Guitar input:** Input 1 has switchable Hi-Z (instrument) — plug straight in
- **Mic input:** Both inputs are XLR/TRS combo with phantom power
- **Yamaha HS8:** Outputs 1+2 TRS → HS8s — works perfectly today

### The Actual Gap
**The 2i2 has only 2 line outputs.** To run BOTH speaker pairs simultaneously you need 4 line outputs:
- Outputs 1+2 → Yamaha HS8 (active, direct TRS)
- Outputs 3+4 → Power Amp → JBL 2600 (passive)

---

## Option A: Monitor Controller / A/B Switch (Cheapest — No Interface Change)

Instead of upgrading the interface, add an A/B monitor selector box between the 2i2 and both speaker pairs. You'd switch between HS8s and JBL 2600s (via power amp) from the controller.

| Device | Price | Notes |
|--------|-------|-------|
| **Mackie Big Knob Passive** | ~$99 | A/B/C monitor switching, master volume, passive — no coloration. Best value. |
| **SM Pro Audio M-Patch 2** | ~$80 | Simple passive A/B, attenuation, mono/mute — minimal and clean |
| **Samson C-Control** | ~$89 | A/B/C + talkback, headphone out, compact |

**Wiring with monitor controller:**
```
Scarlett 2i2 (outputs 1+2)
        │
        ▼
  Monitor Controller
    ├── Output A → Yamaha HS8 (TRS 1/4")
    └── Output B → Power Amp → JBL 2600 (Speakon)
```

**Verdict:** Best bang-for-buck. Keeps the 2i2 (already covers guitar + mic), adds speaker switching for ~$80–99. No latency or quality tradeoff. Buy this first before any interface upgrade.

---

## Option B: Interface Upgrade to 4-Output Model

Upgrade the Scarlett 2i2 to an interface with 4+ line outputs. Both speaker pairs run simultaneously — DAW selects which outputs get signal.

### Shortlist (4+ line outputs, guitar Hi-Z + mic XLR)

| Interface | Outputs | Inputs | Guitar Hi-Z | Price | Notes |
|-----------|---------|--------|-------------|-------|-------|
| **Focusrite Scarlett 4i4 (4th gen)** | 4× TRS | 2× combo | Yes (both switchable) | ~$249 | Natural 2i2 upgrade. Adds MIDI I/O. Same preamp quality. |
| **MOTU M4** | 4× TRS | 2× combo | Yes | ~$249 | Exceptional converters for the price. Best audio quality in this tier. USB-C. |
| **Universal Audio Volt 476** | 4× TRS | 4× (2 combo + 2 line) | Yes | ~$399 | Built-in "vintage" preamp mode. Includes UAD Spark plugin bundle. Overkill for this use case. |
| **Focusrite Scarlett 18i8 (3rd gen)** | 8× TRS | 4× combo + ADAT | Yes (inputs 1+2) | ~$449 | Significant headroom for future expansion. More inputs than you'd need now. |
| **PreSonus Studio 1824c** | 8× TRS | 8× combo + ADAT | Yes | ~$449 | Studio-grade, good preamps, supports Thunderbolt. Future-proof. |

### Yamaha HS8 Input Spec (your monitors)
The HS8 accepts **balanced TRS 1/4"** or **XLR** — either output type from any interface above works fine. Run balanced TRS for best noise rejection.

### JBL 2600 via Power Amp
Any of the above interfaces' additional line outputs feed a power amp the same way — balanced TRS → amp input → Speakon → JBL 2600. See `studio-wiring-jbl2600.md` for full chain.

---

## Option C: Interface + Monitor Controller (Best Long-Term)

Upgrade to a 4-output interface AND add a monitor controller. This gives you:
- Simultaneous outputs to both pairs (no switching needed)
- Proper master volume control
- Headphone monitoring separate from speakers

Recommended combo: **Focusrite Scarlett 4i4** (~$249) + **Mackie Big Knob Passive** (~$99) = ~$348 total.

---

## Recommendation Summary

| Scenario | Best Option | Est. Cost |
|----------|------------|-----------|
| Minimum spend, just want to use JBL 2600s sometimes | Mackie Big Knob Passive + power amp (Crown XLS 1002) | ~$398 |
| Natural interface upgrade, keep flexibility | Scarlett 4i4 + power amp | ~$548 |
| Best audio quality upgrade | MOTU M4 + power amp | ~$548 |
| Future-proof full studio | Scarlett 18i8 + monitor controller + power amp | ~$847 |

**Priority order:**
1. **Power amp first** (required — JBL 2600s can't run without it)
2. **Monitor controller** (cheapest way to switch between speaker pairs — $80–99)
3. **Interface upgrade** only if you need more simultaneous inputs (e.g. recording band with multiple mics at once)

The 2i2 is not the bottleneck for guitar or mic — it already handles both fine. The real gap is outputs and speaker switching.

---

## Cable Summary for Full Dual-Monitor Setup

| Cable | Qty | Purpose | Est. Cost |
|-------|-----|---------|-----------|
| TRS 1/4" to XLR male, balanced | 2 | 2i2/new interface → power amp input | ~$20 |
| TRS 1/4" to TRS 1/4", balanced | 2 | Interface → Yamaha HS8 (already have?) | ~$15 |
| Speakon NL4 to Speakon NL4 | 2 | Power amp → JBL 2600 | ~$25 |
| TRS 1/4" to TRS 1/4", balanced | 2 | Interface out → monitor controller in | ~$15 |
