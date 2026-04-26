import sys, json
from pathlib import Path
sys.path.insert(0, str(Path('catalog/setlists').resolve()))
sys.path.insert(0, 'src')
from export_catalog import build_sheet_music_index, sheet_music_for

sm = build_sheet_music_index()

# Load the active setlist export to get song list
setlist_path = Path('catalog/setlists/setlist_active_export.json')
data = json.loads(setlist_path.read_text(encoding='utf-8'))
songs = data.get('songs', [])

missing = []
has_sm = []
for s in songs:
    files = sheet_music_for(s['title'], sm)
    if files:
        has_sm.append(s['title'])
    else:
        missing.append({'title': s['title'], 'artist': s.get('artist',''), 'key': s.get('key','')})

print(f"HAVE sheet music ({len(has_sm)}):")
for t in has_sm:
    print(f"  ✓ {t}")
print()
print(f"MISSING sheet music ({len(missing)}):")
for m in missing:
    key = f" [{m['key']}]" if m['key'] and m['key'] != '?' else ''
    print(f"  ✗ {m['title']} — {m['artist']}{key}")
