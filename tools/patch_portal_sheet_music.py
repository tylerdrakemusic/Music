"""
One-shot: patch portal.html sheet_music arrays using current covers/ filesystem index.
No DB connection needed.
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "catalog" / "setlists"))

from export_catalog import (  # noqa: E402
    BM_END,
    BM_START,
    PORTAL_PATH,
    build_sheet_music_index,
    sheet_music_for,
)

sm_index = build_sheet_music_index()
print(f"Sheet music index: {len(sm_index)} unique titles")

portal = PORTAL_PATH.read_text(encoding="utf-8")
start_idx = portal.find(BM_START)
end_idx = portal.find(BM_END)

block = portal[start_idx + len(BM_START): end_idx].strip()
json_str = re.sub(r"^\s*const BM_INLINE\s*=\s*", "", block).rstrip(";").strip()
data = json.loads(json_str)

updated = 0
for band in data.get("bands", []):
    for song in band["catalog"]["songs"] + band["setlist"]["songs"]:
        sm = sheet_music_for(song["title"], sm_index)
        if sm != song.get("sheet_music", []):
            song["sheet_music"] = sm
            updated += 1

print(f"Updated sheet_music on {updated} songs")

data["exported_at"] = datetime.now(timezone.utc).isoformat()
js_block = f"  const BM_INLINE = {json.dumps(data, ensure_ascii=False)};"
new_portal = (
    portal[: start_idx + len(BM_START)]
    + "\n"
    + js_block
    + "\n  "
    + portal[end_idx:]
)
PORTAL_PATH.write_text(new_portal, encoding="utf-8")
print("portal.html patched")
