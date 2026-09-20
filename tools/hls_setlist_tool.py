"""
Build/inspect Line 6 HX Stomp .hls setlist files.

An .hls file is a JSON wrapper around zlib-compressed JSON:
  {
    "compression": {"crc32": <int>, "decompressed_size": <int>, "type": "zlib"},
    "encoded_data": "<base64 of zlib.compress(inner_json_utf8)>",
    "encoding": "Base64",
    "meta": {"application": "HX Edit", ..., "name": "<setlist name>"},
    "schema": "L6Setlist",
    "version": 2
  }

The decompressed inner JSON is:
  {"meta": {"name": "<setlist name>"}, "presets": [<preset "data">, ...]}

Each entry in "presets" is exactly the "data" object of a standalone .hlx
file (device, device_version, meta, tone) -- no outer .hlx wrapper
("meta"/"schema"/"version" at the .hlx top level are NOT part of the
preset entry here).

Usage:
    # Inspect an .hls file
    python hls_setlist_tool.py inspect "Baseline HX Stomp.hls"

    # Replace slots in a template .hls with .hlx presets and write a new .hls
    python hls_setlist_tool.py build --template "Baseline HX Stomp.hls" \\
        --slot 0="Stop_Draggin_My_Heart_Around.hlx" \\
        --slot 1="What_You_Need_INXS.hlx" \\
        --name "My Setlist" \\
        --output "My Setlist.hls"
"""
from __future__ import annotations

import argparse
import base64
import json
import zlib
from pathlib import Path


def decode_hls(path: Path) -> dict:
    """Decode an .hls file into its inner {"meta": ..., "presets": [...]} dict."""
    outer = json.loads(path.read_text(encoding="utf-8"))
    raw = base64.b64decode(outer["encoded_data"])
    inflated = zlib.decompress(raw)
    comp = outer["compression"]
    if len(inflated) != comp["decompressed_size"]:
        raise ValueError("decompressed_size mismatch: file may be corrupt")
    if zlib.crc32(inflated) != comp["crc32"]:
        raise ValueError("crc32 mismatch: file may be corrupt")
    return json.loads(inflated)


def encode_hls(inner: dict, *, outer_meta: dict) -> dict:
    """Encode an inner {"meta": ..., "presets": [...]} dict into .hls wrapper form."""
    inner_bytes = json.dumps(inner, indent=1, separators=(",", " : ")).encode("utf-8")
    compressed = zlib.compress(inner_bytes)
    return {
        "compression": {
            "crc32": zlib.crc32(inner_bytes),
            "decompressed_size": len(inner_bytes),
            "type": "zlib",
        },
        "encoded_data": base64.b64encode(compressed).decode("ascii"),
        "encoding": "Base64",
        "meta": outer_meta,
        "schema": "L6Setlist",
        "version": 2,
    }


def load_hlx_preset_data(path: Path) -> dict:
    """Load a standalone .hlx file and return just its preset "data" object."""
    hlx = json.loads(path.read_text(encoding="utf-8"))
    return hlx["data"]


def build_setlist(
    template_path: Path,
    slot_map: dict[int, Path],
    output_path: Path,
    setlist_name: str,
) -> None:
    inner = decode_hls(template_path)
    presets = inner["presets"]
    for slot, hlx_path in slot_map.items():
        if slot < 0 or slot >= len(presets):
            raise IndexError(
                f"slot {slot} out of range (template has {len(presets)} slots)"
            )
        presets[slot] = load_hlx_preset_data(hlx_path)
    inner["meta"]["name"] = setlist_name

    template_outer = json.loads(template_path.read_text(encoding="utf-8"))
    outer_meta = dict(template_outer["meta"])
    outer_meta["name"] = setlist_name

    result = encode_hls(inner, outer_meta=outer_meta)
    output_path.write_text(
        json.dumps(result, indent=1, separators=(",", " : ")), encoding="utf-8"
    )


def _parse_slot_arg(value: str) -> tuple[int, Path]:
    slot_str, _, hlx_str = value.partition("=")
    return int(slot_str), Path(hlx_str)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_p = sub.add_parser("inspect", help="Print preset names/count in an .hls")
    inspect_p.add_argument("hls_path", type=Path)

    build_p = sub.add_parser("build", help="Replace slots in a template .hls")
    build_p.add_argument("--template", type=Path, required=True)
    build_p.add_argument("--output", type=Path, required=True)
    build_p.add_argument("--name", required=True)
    build_p.add_argument(
        "--slot",
        action="append",
        required=True,
        type=_parse_slot_arg,
        metavar="INDEX=path/to/preset.hlx",
        help="Repeatable. Slot index (0-based) to replace with an .hlx preset.",
    )

    args = parser.parse_args()

    if args.command == "inspect":
        inner = decode_hls(args.hls_path)
        presets = inner["presets"]
        print(f"setlist name: {inner['meta'].get('name')}")
        print(f"preset count: {len(presets)}")
        for i, p in enumerate(presets):
            name = p.get("meta", {}).get("name", "?")
            if name != "New Preset":
                print(f"  [{i}] {name}")
    elif args.command == "build":
        slot_map = dict(args.slot)
        build_setlist(args.template, slot_map, args.output, args.name)
        print(f"wrote {args.output} ({len(slot_map)} slot(s) replaced)")


if __name__ == "__main__":
    main()
