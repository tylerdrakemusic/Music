"""One-time DB migration: sync gig_inventory to match Tyler's confirmed list."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from utils.init_db import get_connection
import sqlcipher3

conn = get_connection()

# Remove items Tyler cut from the list (idempotent)
conn.execute("DELETE FROM gig_inventory WHERE item IN ('Music Stand','Sheet Music','Lights')")
# Remove duplicate Wireless entry (bare — keep the one with the curly quote, id=12)
conn.execute("DELETE FROM gig_inventory WHERE item = 'Wireless 1/4' AND id != 12")

# Insert new items by name (no-op if already present)
new_items = [
    ("iPad",             "Accessories", 7),
    ("Extension Chord",  "Accessories", 9),
    ("Cooling Fan",      "Accessories", 11),
]
existing = {r[0] for r in conn.execute("SELECT item FROM gig_inventory").fetchall()}
for item, category, sort_order in new_items:
    if item not in existing:
        conn.execute(
            "INSERT INTO gig_inventory (item, category, sort_order) VALUES (?,?,?)",
            (item, category, sort_order),
        )

conn.commit()

conn.row_factory = sqlcipher3.dbapi2.Row
rows = conn.execute(
    "SELECT id, item, category, sort_order FROM gig_inventory ORDER BY sort_order"
).fetchall()
print(f"gig_inventory — {len(rows)} rows:")
for r in rows:
    print(f"  {dict(r)}")

conn.close()
