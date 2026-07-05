"""HX Stomp .hlx preset generator (FR-20260705-guitar-tech-persona-agent).

Builds a complete, HX-Edit-loadable preset dict for a song's assigned guitar
persona. Persona identity comes entirely from MODEL SELECTION (which amp,
drive pedal, modulation, reverb, or delay block is used) -- every numeric
parameter is taken verbatim from that model's own declared catalog default,
never hand-tuned. This keeps every value traceable to a real, verifiable
source (the committed catalog/helix_reference/ snapshot) and leaves final
knob-tuning to Tyler, matching the `status='proposed'` review workflow.

Structural fidelity is grounded in a full read of a real, current-format
preset (HelixFiles/Rhiannon_Fleetwood_Mac.hlx) rather than the older
default_preset_hxs.hlx skeleton, which is missing the outer
`data.tone.variax` section and the top-level `meta{original,pbn,premium}`
wrapper that current HX Edit builds require.

`@type` per block role was derived empirically from real preset files
(not from the catalog's own unrelated "category" field):
  - amp                  -> 3   (Rhiannon: HD2_AmpUSDoubleNrm; Barracuda_Heart: HD2_AmpCaliRectifire)
  - reverb / delay        -> 7   (Rhiannon: HD2_ReverbPlate, HD2_DelaySimpleDelay; Barracuda_Heart: HD2_ReverbPlate)
  - drive / compressor /
    modulation / utility  -> 0   (Rhiannon: HD2_CompressorDeluxeComp, HD2_Chorus70sChorus;
                                   Change The World.hlx: HD2_DistKinkyBoost, HD2_CompressorDeluxeComp)

Footswitch assignment and per-snapshot tonal variation are explicitly OUT of
scope for the generator (all 3 snapshots are identical, all blocks enabled) --
these are left as manual Tyler TODOs, matching the existing HelixFiles/TODO.md
convention for other presets.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from guitar_tech.hlx_catalog import HX_STOMP_DEVICE_ID, default_params, get_model
from guitar_tech.persona_rubric import EVH, HENDRIX, MAYER, PRINCE, SRV, PersonaMatch

APP_VERSION = 57671680
BUILD_SHA = "v3.70-10-ge773a6f"
DEVICE_VERSION = 57737216
DEFAULT_TEMPO = 120.0

ROLE_TYPE = {
    "drive": 0,
    "compressor": 0,
    "modulation": 0,
    "amp": 3,
    "reverb": 7,
    "delay": 7,
}


@dataclass(frozen=True)
class BlockSpec:
    role: str
    category: str
    symbolic_id: str


RECIPES: dict[str, list[BlockSpec]] = {
    SRV: [
        BlockSpec("compressor", "compressor", "HD2_CompressorRedSqueeze"),
        BlockSpec("amp", "amp", "HD2_AmpCaliTexasCh1"),
        BlockSpec("reverb", "reverb", "HD2_Reverb63Spring"),
    ],
    HENDRIX: [
        BlockSpec("drive", "distortion", "HD2_DistArbitratorFuzz"),
        BlockSpec("amp", "amp", "HD2_AmpBritPlexiJump"),
        BlockSpec("modulation", "modulation", "HD2_PhaserUbiquitousVibe"),
        BlockSpec("reverb", "reverb", "HD2_Reverb63Spring"),
    ],
    PRINCE: [
        BlockSpec("compressor", "compressor", "HD2_CompressorDeluxeComp"),
        BlockSpec("amp", "amp", "HD2_AmpPlacaterClean"),
        BlockSpec("modulation", "modulation", "HD2_PhaserScriptModPhase"),
    ],
    EVH: [
        BlockSpec("amp", "amp", "HD2_AmpBritPlexiNrm"),
        BlockSpec("delay", "delay", "HD2_DelaySimpleDelay"),
    ],
    MAYER: [
        BlockSpec("amp", "amp", "HD2_AmpTweedBluesBrt"),
        BlockSpec("reverb", "reverb", "HD2_Reverb63Spring"),
    ],
}


def _build_block(spec: BlockSpec, position: int) -> dict[str, Any]:
    model = get_model(spec.category, spec.symbolic_id)
    block: dict[str, Any] = {
        "@enabled": True,
        "@model": spec.symbolic_id,
        "@path": 0,
        "@position": position,
        "@no_snapshot_bypass": False,
        "@type": ROLE_TYPE[spec.role],
    }
    block.update(default_params(model))
    if spec.role == "amp":
        block["@cab"] = "cab0"
    return block


def _build_cab(amp_model: dict[str, Any]) -> dict[str, Any]:
    cab_id = amp_model["ircablink"]
    cab_model = get_model("cabmicirs", cab_id)
    cab: dict[str, Any] = {"@enabled": True, "@model": cab_id}
    cab.update(default_params(cab_model))
    return cab


def _build_routing(join_position: int) -> dict[str, Any]:
    return {
        "inputA": {
            "@input": 1,
            "@model": "HelixStomp_AppDSPFlowInput",
            "decay": 0.5,
            "noiseGate": False,
            "threshold": -48.0,
        },
        "inputB": {
            "@input": 0,
            "@model": "HelixStomp_AppDSPFlowInput",
            "decay": 0.5,
            "noiseGate": False,
            "threshold": -48.0,
        },
        "join": {
            "@enabled": True,
            "@model": "HD2_AppDSPFlowJoin",
            "@no_snapshot_bypass": False,
            "@position": join_position,
            "A Level": 0.0,
            "A Pan": 0.5,
            "B Level": 0.0,
            "B Pan": 0.5,
            "B Polarity": False,
            "Level": 0.0,
        },
        "outputA": {
            "@model": "HelixStomp_AppDSPFlowOutputMain",
            "@output": 1,
            "gain": 1.0,
            "pan": 0.5,
        },
        "outputB": {
            "@model": "HelixStomp_AppDSPFlowOutputSend",
            "@output": 0,
            "Type": True,
            "gain": 1.0,
            "pan": 0.5,
        },
        "split": {
            "@enabled": True,
            "@model": "HD2_AppDSPFlowSplitY",
            "@no_snapshot_bypass": False,
            "@position": 0,
            "BalanceA": 0.5,
            "BalanceB": 0.5,
            "bypass": False,
        },
    }


def _build_global(tempo: float) -> dict[str, Any]:
    return {
        "@DtSelect": 2,
        "@PowercabMode": 0,
        "@PowercabSelect": 2,
        "@PowercabVoicing": 0,
        "@current_snapshot": 0,
        "@cursor_dsp": 0,
        "@cursor_group": "block0",
        "@cursor_path": 0,
        "@cursor_position": 1,
        "@guitarinputZ": 0,
        "@guitarpad": 0,
        "@model": "@global_params",
        "@pedalstate": 2,
        "@tempo": tempo,
        "@topology0": "A",
        "@topology1": 0,
    }


def _build_snapshot(name: str, block_count: int, tempo: float, custom: bool) -> dict[str, Any]:
    return {
        "@custom_name": custom,
        "@ledcolor": 0,
        "@name": name,
        "@pedalstate": 0,
        "@tempo": tempo,
        "@valid": True,
        "blocks": {"dsp0": {f"block{i}": True for i in range(block_count)}},
    }


def _build_variax() -> dict[str, Any]:
    return {
        "@variax_customtuning": True,
        "@variax_lockctrls": 0,
        "@variax_magmode": False,
        "@variax_model": 0,
        "@variax_str1tuning": 0,
        "@variax_str2tuning": 0,
        "@variax_str3tuning": 0,
        "@variax_str4tuning": 0,
        "@variax_str5tuning": 0,
        "@variax_str6tuning": 0,
        "@variax_toneknob": -0.1,
        "@variax_volumeknob": -0.1,
    }


def generate_preset(
    *,
    title: str,
    artist: str,
    bpm: float | None,
    persona_match: PersonaMatch,
    preset_name: str | None = None,
) -> dict[str, Any]:
    """Generate a complete HX Stomp preset dict for a song's assigned persona.

    The primary (first-listed) persona in `persona_match.personas` selects
    the gear recipe -- a blended match (e.g. SRV + Albert King + B.B. King)
    still only drives one signal chain, since a single HX Stomp DSP path
    can only host one amp. The blend is preserved in `persona_match.label`
    / `.rationale` for the DB record and human review, not the gear chain.
    """
    primary = persona_match.personas[0]
    if primary not in RECIPES:
        raise KeyError(f"No .hlx gear recipe defined for primary persona {primary!r}")
    recipe = RECIPES[primary]

    dsp0: dict[str, Any] = {}
    amp_model: dict[str, Any] | None = None
    for i, spec in enumerate(recipe):
        dsp0[f"block{i}"] = _build_block(spec, i)
        if spec.role == "amp":
            amp_model = get_model(spec.category, spec.symbolic_id)

    assert amp_model is not None, "every recipe must include exactly one amp block"
    dsp0["cab0"] = _build_cab(amp_model)
    dsp0.update(_build_routing(join_position=len(recipe)))

    tempo = float(bpm) if bpm else DEFAULT_TEMPO
    block_count = len(recipe)
    snapshot_names = ["Full Tone", "Snapshot 2", "Snapshot 3"]
    snapshots = {
        f"snapshot{idx}": _build_snapshot(name, block_count, tempo, custom=(idx == 0))
        for idx, name in enumerate(snapshot_names)
    }

    name = preset_name or f"{title} - {persona_match.label} (Proposed)"

    return {
        "data": {
            "device": HX_STOMP_DEVICE_ID,
            "device_version": DEVICE_VERSION,
            "meta": {
                "application": "HX Edit",
                "appversion": APP_VERSION,
                "build_sha": BUILD_SHA,
                "modifieddate": int(time.time()),
                "name": name,
            },
            "tone": {
                "dsp0": dsp0,
                "dsp1": {},
                "footswitch": {"dsp0": {}},
                "global": _build_global(tempo),
                **snapshots,
                "variax": _build_variax(),
            },
        },
        "meta": {"original": 0, "pbn": 0, "premium": 0},
        "schema": "L6Preset",
        "version": 6,
    }
