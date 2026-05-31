"""One-time fixup: move 'Is It Real' from covers → originals (BFX-20260531-gdrive-fixup)."""
import sys
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.init_db import get_connection

src = Path(r"f:\❤Music\catalog\sheet_music\covers\Is It real.docx")
dst = Path(r"f:\❤Music\catalog\sheet_music\originals\Is It real.docx")

if src.exists():
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    print(f"Moved: {src.name}  covers/ -> originals/")
elif dst.exists():
    print(f"Already in originals/ (file OK)")
else:
    print(f"WARNING: file not found at either location")

conn = get_connection()
conn.execute(
    "UPDATE sheet_music SET category='originals', local_path='catalog/sheet_music/originals/Is It real.docx' "
    "WHERE name='Is It real.docx' AND source='gdrive'"
)
conn.commit()
row = conn.execute(
    "SELECT id, name, category, local_path FROM sheet_music WHERE name='Is It real.docx'"
).fetchone()
print(f"DB row: {dict(row)}")
conn.close()
