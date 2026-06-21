import re
from pathlib import Path
b64path = Path(r"F:\❤Music\Brand\hyperthreat\hyperthreat-logo.png.b64.txt")
htmlpath = Path(r"F:\❤Music\studio\mic_config_template.html")
if not b64path.exists():
    print('B64 file missing:', b64path)
    raise SystemExit(1)
text_b64 = b64path.read_text(encoding='utf-8').strip()
html = htmlpath.read_text(encoding='utf-8')
# Replace the img with id ht-logo
new_img = f'<img id="ht-logo" src="{text_b64}" alt="Hyperthreat Studios">'
html, n = re.subn(r'<img[^>]*id=["\']ht-logo["\'][^>]*>', new_img, html, count=1)
print('Replaced img tag:', n)
# Remove the loader function block
html, m = re.subn(r"// Attempt to load[\s\S]*?\}\)\(\);", "// Logo inlined; loader removed.", html, count=1)
print('Removed loader block:', m)
htmlpath.write_text(html, encoding='utf-8')
print('WROTE', htmlpath)
