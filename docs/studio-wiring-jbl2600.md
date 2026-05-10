# Studio Wiring: JBL 2600 Passive PA Speakers

**Status:** Decision Locked — 2026-05-09  
**Gear ID in heartmusic.db:** 27

---

## 📦 Procurement Log

| Item | Order # | Vendor | Date | Status | Notes |
|------|---------|--------|------|--------|-------|
| Mackie Big Knob Passive | MAC10881259 | shop.mackie.com | 2026-05-10 12:29 AM EST | Ordered | Monitor controller (A/B switching) |
| Crown XLS 1002 | — | — | — | Pending | Power amplifier for JBL 2600 |
| Speaker wire + connectors | — | — | — | Pending | Standard 14 AWG OFC, binding posts to spring clips |
| TRS cables (Scarlett → Big Knob) | — | — | — | Pending | 1/4" TRS, 3–10 ft |  

---

## ✅ Final Decision — Locked 2026-05-09

| Component | Model | Est. Price | Purpose |
|-----------|-------|-----------|---------|
| **Power Amp** | Crown XLS 1002 | ~$299 | Drives JBL 2600 (passive, 350W × 2 @ 8Ω) |
| **Monitor Controller** | Mackie Big Knob Passive | ~$99 | A/B/C speaker switching — Scarlett 2i2 → HS8 or JBL 2600 |

**Total to go live:** ~$398 + cables (~$45) = **~$443**

**Signal chain (locked):**
```
Scarlett 2i2 (Outputs 1+2, balanced TRS)
        │
        ▼
  Mackie Big Knob Passive (monitor controller)
    ├── Output A (balanced TRS) → Yamaha HS8 × 2  (active, existing monitors)
    └── Output B (balanced TRS) → Crown XLS 1002 (power amp)
                                        └── Speakon NL4 → JBL 2600 × 2  (passive PA)
```

**See `docs/studio-wiring-decision.mmd` for the full Mermaid diagram.**

**Interface upgrade deferred:** The Scarlett 2i2 handles guitar (Hi-Z input 1) and mic (XLR phantom power) — no upgrade needed for current use. Option B/C (4i4 or MOTU M4) remains open for future expansion if simultaneous multi-output or more inputs are needed. See `docs/interface-upgrade-research.md`.

**Budget entry:** Log in `heartmusic.db` budget table at time of purchase.

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
┌─────────────────────┐       TRS or XLR        ┌──────────────────────┐       Speakon or 1/4"      ┌───────────────┐
│   Focusrite         │  ─────────────────────►  │   Power Amplifier    │  ─────────────────────►   │  JBL 2600     │
│   Scarlett 2i2      │  (balanced line level)    │   (see options below)│  (speaker level signal)    │  (passive)    │
│   Output L (TRS)    │                           │   Input: XLR or TRS  │                            │  Input: Speakon│
│   Output R (TRS)    │  ─────────────────────►  │   Output: Speakon    │  ─────────────────────►   │  or 1/4" TRS  │
└─────────────────────┘                           └──────────────────────┘                            └───────────────┘
```

**Cable 1 (Interface → Amp input):**  
TRS 1/4" to XLR male — balanced, professional audio. ~$10–20 per cable.  
OR TRS to TRS if the amp accepts TRS inputs.

**Cable 2 (Amp output → Speaker):**  
Speakon NL4 to Speakon NL4 — industry standard, locking, safe.  
OR 1/4" TS to 1/4" TS — legacy, works but not locking.  
**Never use XLR for speaker-level — wrong impedance and signal type.**

---

## Recommended Power Amplifiers

All three options are well-matched for the JBL 2600 (300W/8Ω program).

| Amp | Power (8Ω/ch) | Price | Notes |
|-----|--------------|-------|-------|
| **Crown XLS 1002** | 350W × 2 | ~$299 | Industry standard, lightweight, reliable. Balanced XLR inputs. Best choice. |
| **QSC GX3** | 300W × 2 | ~$350–400 (used) | Studio-grade, clean, excellent for monitoring. Balanced XLR inputs. |
| **Behringer iNuke NU1000** | 500W × 2 | ~$150 | Budget-friendly, higher risk of coloration. Good for PA use, not critical monitoring. |

**Recommendation:** Crown XLS 1002 — proven reliability, perfect wattage match, available new.

---

## Stereo vs. Mono Considerations

- The Scarlett 2i2 has **2 line outputs** (L + R) — run one cable to each amp channel for stereo use.
- If using the JBL 2600s as **PA reinforcement** (mono), bridge the amp channels (see your amp's manual) for ~700W mono into the speaker. Do not exceed the speaker's 600W peak.

---

## Next Steps (Purchasing Decision — Tyler's Call)

1. ✅ **Mackie Big Knob Passive** — ORDERED (MAC10881259, 2026-05-10)
2. **Priority:** Power amplifier (Crown XLS 1002, ~$299 new)
3. **Cables needed:**
   - 2× TRS 1/4" male (Scarlett out) to TRS 1/4" male (Big Knob in), 3–10 ft (~$15 total)
   - 2× 14 AWG OFC speaker wire (Crown binding posts to JBL spring clips), short runs (~$20 total)
4. **Optional:** Rack case if mounting amp + interface together

**Total remaining cost:** ~$319 (Crown + cables)

---

## References

- JBL 2600 Product Page / Spec Sheet: [JBL Professional](https://jblpro.com)
- Crown XLS Series: [Crown Audio](https://crownaudio.com)
- Focusrite Scarlett 2i2 Manual: 2 balanced TRS line outputs, max +14 dBu, 2Ω minimum load (line-level)
