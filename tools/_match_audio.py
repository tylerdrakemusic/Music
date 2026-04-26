"""
Match setlist songs missing audio against G:\\Muzic flat file listing.
Outputs SQL UPDATE statements to populate catalog_songs.source_file.
No DB connection needed — reads portal BM_INLINE and scans G:\\Muzic.
"""
import json, re, sys, unicodedata
from pathlib import Path

sys.path.insert(0, str(Path('catalog/setlists').resolve()))
sys.path.insert(0, 'src')
from export_catalog import BM_START, BM_END, PORTAL_PATH

# ── Load current portal data ──────────────────────────────────────────────────
portal = PORTAL_PATH.read_text(encoding='utf-8')
start_idx = portal.find(BM_START)
end_idx   = portal.find(BM_END)
block = portal[start_idx + len(BM_START): end_idx].strip()
json_str = re.sub(r"^\s*const BM_INLINE\s*=\s*", "", block).rstrip(";").strip()
data = json.loads(json_str)

# ── Index G:\Muzic ────────────────────────────────────────────────────────────
MUZIC = Path(r"G:\Muzic")
audio_files = {}
for f in MUZIC.iterdir():
    if f.suffix.lower() in ('.mp3', '.wav', '.flac', '.m4a') and f.is_file():
        audio_files[f.name] = f.name  # key = filename, val = filename (relative)

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return "".join(c for c in s.lower() if c.isalnum() or c.isspace()).strip()

# Build normalized index of G:\Muzic: norm(title + artist) -> filename
audio_norm = {}
for fname in audio_files:
    stem = Path(fname).stem  # e.g. "Long Train Runnin' - The Doobie Brothers"
    if ' - ' in stem:
        parts = stem.split(' - ', 1)
        title_part = parts[0].strip()
        # strip key/step suffixes like (+2 steps), (in Bm), (Live), (Clean Master) etc
        title_clean = re.sub(r'\s*\([^)]*\)\s*$', '', title_part).strip()
        key = _norm(title_clean)
    else:
        key = _norm(stem)
    audio_norm.setdefault(key, []).append(fname)

# ── Check each setlist song ───────────────────────────────────────────────────
cc = next(b for b in data['bands'] if b['name'] == 'Copper Creek')
setlist_songs = cc['setlist']['songs']

print("Songs with audio match:")
matched = []
unmatched = []
for song in setlist_songs:
    has_audio = bool(song.get('audio_url'))
    title_key = _norm(song['title'])
    candidates = audio_norm.get(title_key, [])
    # prefer plain .mp3 over step-transposed/live variants
    best = next((f for f in candidates if not re.search(r'\([+-][\d.]', f) and f.endswith('.mp3')), None)
    if best is None:
        best = next((f for f in candidates if f.endswith('.mp3')), candidates[0] if candidates else None)

    if not has_audio and best:
        matched.append({'title': song['title'], 'id': song.get('id'), 'file': best})
    elif not has_audio and not best:
        unmatched.append(song['title'])

print(f"\nMissing audio + FOUND in G:\\Muzic ({len(matched)}):")
for m in matched:
    print(f"  ✓ {m['title']}")
    print(f"    → {m['file']}")

print(f"\nMissing audio + NOT FOUND ({len(unmatched)}):")
for t in unmatched:
    print(f"  ✗ {t}")

print(f"\nAlready has audio ({sum(1 for s in setlist_songs if s.get('audio_url'))}):")

# ── Generate SQL ──────────────────────────────────────────────────────────────
if matched:
    print("\n-- SQL to run (requires HEARTMUSIC_DB_KEY):")
    print("-- cd f:\\❤Music && C:\\G\\python.exe tools\\update_audio_sources.py")
    print()
    for m in matched:
        if m['id']:
            print(f"UPDATE catalog_songs SET source_file = '{m['file']}' WHERE id = {m['id']};")
        else:
            print(f"-- (no id) UPDATE catalog_songs SET source_file = '{m['file']}' WHERE title = '{m['title']}';")
