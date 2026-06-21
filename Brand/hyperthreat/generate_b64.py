import base64
from pathlib import Path
p = Path(r"F:\❤Music\Brand\hyperthreat")
files = ["hyperthreat-logo.png", "hyperthreat-logo-print.png"]
for name in files:
    src = p / name
    if not src.exists():
        print(f"MISSING: {src}")
        continue
    data = src.read_bytes()
    b = base64.b64encode(data).decode('ascii')
    out = p / (name + ".b64.txt")
    out.write_text("data:image/png;base64," + b, encoding='ascii')
    print(f"WROTE: {out}")
