# HX Edit Reference Data (Line 6 HX Stomp)

Committed snapshot of Line 6 HX Edit's model catalog, copied from a local
HX Edit install for offline, git-tracked reference by the `❤music-guitar-tech`
persona-matching and preset-generation tooling (`src/guitar_tech/hlx_catalog.py`).

## Origin

Copied once from the local HX Edit application's model data directory. This
is static reference data describing every stompbox/amp/cab model available
on the Helix platform (symbolic IDs, default parameter values, parameter
ranges, per-model device compatibility). It does not change per-preset and
is safe to snapshot.

## Contents

| File | Category |
|---|---|
| `amp.models` | Amp models |
| `cab.models` | Cab models |
| `cabmicirs.models` | Cab + mic IR combinations |
| `cabmicirswithpan.models` | Cab + mic IR combinations with stereo pan |
| `compressor.models` | Compressor/dynamics models |
| `delay.models` | Delay models |
| `distortion.models` | Drive/distortion/fuzz models |
| `eq.models` | EQ models |
| `filter.models` | Filter models |
| `fixed.models` | Fixed/utility blocks |
| `gate.models` | Noise gate models |
| `io.models` | I/O and routing primitives (input/output/split/join) |
| `modulation.models` | Modulation models (chorus, phaser, flanger, vibe, etc.) |
| `pitch-synth.models` | Pitch/synth models |
| `preamp.models` | Preamp models |
| `reverb.models` | Reverb models |
| `sendreturn.models` | Send/return blocks |
| `volumepan.models` | Volume/pan blocks |
| `wah.models` | Wah models |
| `HX_ModelCatalog.json` | Consolidated top-level model catalog index |
| `default_preset_hxs.hlx` | A stock factory preset used as a structural reference for the `.hlx` JSON skeleton (top-level keys, dsp0 shape, snapshot shape) |

## Usage

`src/guitar_tech/hlx_catalog.py` loads these files (cached per-process) to:
- Look up a model's declared default parameter values (`default_params`)
- Check per-model device compatibility, e.g. HX Stomp (`model_supports_device`)
- Load the preset skeleton shape (`load_skeleton`)
- List all available categories / search for a model across categories
  (`list_categories`, `find_model_category`)

`src/guitar_tech/hlx_generator.py` sources every numeric parameter value in
a generated preset from these files' declared `default` values — no
hand-picked values. This keeps every generated `.hlx` preset traceable back
to real Helix model data.

## Maintenance

Do not hand-edit these files — they are a reference-data snapshot, not
config. If Line 6 ships new models, re-copy from a current HX Edit install
and re-run the `guitar_tech` test suite (`pytest tests/test_hlx_catalog.py
tests/test_hlx_generator.py tests/test_hlx_validator.py`) to confirm
nothing broke.
