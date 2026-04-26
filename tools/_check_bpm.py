"""Check which setlist songs are missing BPM and read their docx files for tempo markings."""
import json, re, sys, zipfile
from pathlib import Path

sys.path.insert(0, str(Path('catalog/setlists').resolve()))
sys.path.insert(0, 'src')
from export_catalog import BM_START, BM_END, PORTAL_PATH, SHEET_MUSIC

portal = PORTAL_PATH.read_text(encoding='utf-8')
start_idx = portal.find(BM_START)
end_idx   = portal.find(BM_END)
block = portal[start_idx + len(BM_START): end_idx].strip()
json_str = re.sub(r"^\s*const BM_INLINE\s*=\s*", "", block).rstrip(";").strip()
data = json.loads(json_str)

cc = next(b for b in data['bands'] if b['name'] == 'Copper Creek')
songs = cc['setlist']['songs']

missing_bpm = [s for s in songs if not s.get('bpm')]
print(f"Missing BPM: {len(missing_bpm)} songs\n")

def extract_text_from_docx(path: Path) -> str:
    """Extract plain text from a .docx file."""
    try:
        with zipfile.ZipFile(path) as z:
            with z.open('word/document.xml') as f:
                xml = f.read().decode('utf-8', errors='replace')
        # Strip XML tags
        return re.sub(r'<[^>]+>', ' ', xml)
    except Exception as e:
        return f"ERROR: {e}"

BPM_PATTERN = re.compile(
    r'(?:bpm|tempo|♩\s*=|♩=|q\s*=|mm\s*=|beats?\s*per\s*min[^0-9]*)'
    r'[^\d]*(\d{2,3})',
    re.IGNORECASE
)

for song in missing_bpm:
    title = song['title']
    sm_files = song.get('sheet_music', [])
    found_bpm = None
    for uri in sm_files:
        # Convert file:/// URI to path
        path_str = uri.replace('file:///', '').replace('%20', ' ').replace('%26', '&').replace('%28', '(').replace('%29', ')')
        p = Path(path_str)
        if p.suffix.lower() == '.docx' and p.exists():
            text = extract_text_from_docx(p)
            m = BPM_PATTERN.search(text)
            if m:
                found_bpm = int(m.group(1))
                break
    print(f"  {title}: ", end='')
    if found_bpm:
        print(f"FOUND in sheet music → {found_bpm} BPM")
    else:
        print(f"not in sheet music — needs web lookup")
