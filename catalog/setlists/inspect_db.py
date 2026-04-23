import sqlite3
db = r"f:\❤Music\src\data\heartmusic.db"
conn = sqlite3.connect(db)
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
for (name,) in tables:
    cols = conn.execute(f"PRAGMA table_info({name})").fetchall()
    count = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
    print(f"{name} ({count} rows): {[c[1] for c in cols]}")
conn.close()
