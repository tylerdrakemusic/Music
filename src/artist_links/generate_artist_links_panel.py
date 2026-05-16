"""Generate the Artist Links Pill Panel HTML.

Reads studio_master/linkTyler.json and emits reports/artist_links_panel.html —
a self-contained dark panel showing all artist platform profile links as
clickable pills, grouped by Social Media · Distribution Platforms · Payment.

Stub/placeholder URLs (containing template tokens like yourartistid) are
rendered as muted disabled pills so Tyler can see which platforms still need
real IDs filled in.

Usage:
    C:\\G\\python.exe src/artist_links/generate_artist_links_panel.py
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LINKS_JSON   = PROJECT_ROOT / "studio_master" / "linkTyler.json"
OUTPUT_HTML  = PROJECT_ROOT / "reports" / "artist_links_panel.html"
OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Stub / placeholder detection
# ---------------------------------------------------------------------------

_STUB_PATTERNS = re.compile(
    r"yourartistid|yourtrackid|yourprofile2|yoursong|yourband|example\.com",
    re.IGNORECASE,
)

def _is_stub(url: str) -> bool:
    return bool(_STUB_PATTERNS.search(url))

def _is_url(value: str) -> bool:
    """Return True if the value looks like a navigable URL (not an embed iframe)."""
    v = value.strip()
    return v.startswith("http://") or v.startswith("https://") or v.startswith("spotify:")

# ---------------------------------------------------------------------------
# Platform display metadata
# ---------------------------------------------------------------------------

_PLATFORM_META: dict[str, tuple[str, str]] = {
    # Social
    "facebook":          ("📘", "#1877f2"),
    "instagram":         ("📸", "#e1306c"),
    "tiktok":            ("🎵", "#010101"),
    "whatsapp":          ("💬", "#25d366"),
    "x":                 ("𝕏",  "#000000"),
    # Payment
    "venmo":             ("💙", "#3d95ce"),
    "paypal":            ("💳", "#003087"),
    # Distribution
    "amazon_music":      ("🎵", "#00a8e0"),
    "apple_music":       ("🍎", "#fc3c44"),
    "itunes":            ("🍎", "#fc3c44"),
    "audius":            ("🔊", "#7e1bcc"),
    "bandcamp":          ("🎸", "#1da0c3"),
    "boomplay":          ("🎧", "#f04124"),
    "deezer":            ("🎶", "#ef5466"),
    "distrokid":         ("📦", "#4a90e2"),
    "pandora":           ("📻", "#3668ff"),
    "soundcloud":        ("🌊", "#ff5500"),
    "spotify":           ("🟢", "#1db954"),
    "tidal":             ("🌊", "#000000"),
    "youtube_music":     ("▶️", "#ff0000"),
    "anghami":           ("🎵", "#7f00ff"),
    "claro_musica":      ("🎵", "#e63c2f"),
    "flo":               ("🎵", "#ff7300"),
    "iheartradio":       ("❤️", "#cc0000"),
    "joox":              ("🎵", "#00b050"),
    "kuack_media":       ("🎵", "#888888"),
    "medianet":          ("🎵", "#888888"),
    "netease":           ("🎵", "#cc0000"),
    "qobuz":             ("🎵", "#4a90d9"),
    "saavn":             ("🎵", "#2bc5b4"),
    "tencent":           ("🎵", "#0abf53"),
    "instagram_facebook":("📸", "#e1306c"),
    "adaptr":            ("🎵", "#888888"),
}

def _platform_meta(name: str) -> tuple[str, str]:
    return _PLATFORM_META.get(name.lower().replace(" ", "_"), ("🔗", "#555555"))

# ---------------------------------------------------------------------------
# Build pill data
# ---------------------------------------------------------------------------

def _pill(label: str, url: str) -> dict:
    stub = _is_stub(url)
    icon, color = _platform_meta(label)
    return {"label": label, "url": url, "stub": stub, "icon": icon, "color": color}

def _clean_label(raw: str) -> str:
    return raw.replace("_", " ").title()

def build_sections(data: dict) -> list[dict]:
    sections = []

    # --- Social Media ---
    pills: list[dict] = []
    for platform, urls in data.get("social_media", {}).items():
        for url in urls:
            if _is_url(url):
                pills.append(_pill(platform, url))
    if pills:
        sections.append({"title": "Social Media", "pills": pills})

    # --- Payment ---
    pills = []
    for platform, urls in data.get("payment", {}).items():
        for url in urls:
            if _is_url(url):
                pills.append(_pill(platform, url))
    if pills:
        sections.append({"title": "Payment", "pills": pills})

    # --- Distribution Platforms ---
    pills = []
    for platform, platform_data in data.get("distribution_platforms", {}).items():
        if not isinstance(platform_data, dict):
            continue
        artist_links = platform_data.get("artist_links", [])
        for url in artist_links:
            if _is_url(url):
                pills.append(_pill(_clean_label(platform), url))
    if pills:
        sections.append({"title": "Distribution Platforms", "pills": pills})

    return sections

# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

def _pill_html(p: dict) -> str:
    icon  = html.escape(p["icon"])
    label = html.escape(p["label"])
    color = html.escape(p["color"])
    url   = html.escape(p["url"])

    if p["stub"]:
        return (
            f'<span class="pill pill-stub" title="Placeholder URL — real ID not yet filled in">'
            f'{icon} {label}</span>'
        )

    return (
        f'<a class="pill" href="{url}" target="_blank" rel="noopener noreferrer" '
        f'style="--pill-color:{color};">'
        f'{icon} {label}</a>'
    )

def render_html(sections: list[dict], generated_at: str) -> str:
    sections_html = ""
    for sec in sections:
        pills_html = "\n          ".join(_pill_html(p) for p in sec["pills"])
        stub_count = sum(1 for p in sec["pills"] if p["stub"])
        stub_note  = (
            f'<span class="stub-note">({stub_count} placeholder{"s" if stub_count != 1 else ""} — '
            f'fill in real IDs in studio_master/linkTyler.json)</span>'
            if stub_count else ""
        )
        sections_html += f"""
      <section class="link-section">
        <h2>{html.escape(sec['title'])} {stub_note}</h2>
        <div class="pills">
          {pills_html}
        </div>
      </section>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>❤ Artist Links</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0d0d0d;
      color: #e0e0e0;
      padding: 24px;
      min-height: 100vh;
    }}
    header {{
      display: flex;
      align-items: baseline;
      gap: 12px;
      margin-bottom: 28px;
      border-bottom: 1px solid #2a2a2a;
      padding-bottom: 16px;
    }}
    header h1 {{ font-size: 1.5rem; font-weight: 700; }}
    header .generated {{ font-size: 0.75rem; color: #555; margin-left: auto; }}
    .link-section {{ margin-bottom: 28px; }}
    .link-section h2 {{
      font-size: 0.85rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #888;
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .stub-note {{ font-size: 0.7rem; font-weight: 400; text-transform: none; color: #555; }}
    .pills {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 6px 14px;
      border-radius: 9999px;
      font-size: 0.82rem;
      font-weight: 500;
      text-decoration: none;
      color: #fff;
      background: var(--pill-color, #333);
      opacity: 0.9;
      border: 1px solid rgba(255,255,255,0.08);
      transition: opacity 0.15s, transform 0.1s;
      white-space: nowrap;
    }}
    .pill:hover {{
      opacity: 1;
      transform: translateY(-1px);
    }}
    .pill-stub {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 6px 14px;
      border-radius: 9999px;
      font-size: 0.82rem;
      font-weight: 500;
      color: #555;
      background: #1a1a1a;
      border: 1px dashed #333;
      white-space: nowrap;
      cursor: not-allowed;
    }}
    footer {{
      margin-top: 40px;
      font-size: 0.7rem;
      color: #3a3a3a;
      text-align: center;
    }}
  </style>
</head>
<body>
  <header>
    <h1>❤ Artist Links</h1>
    <span class="generated">generated {html.escape(generated_at)}</span>
  </header>
  {sections_html}
  <footer>
    Source: studio_master/linkTyler.json &nbsp;·&nbsp; ❤Music &nbsp;·&nbsp; Tyler James Drake
  </footer>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"Reading {LINKS_JSON}")
    try:
        data = json.loads(LINKS_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: linkTyler.json is invalid JSON — {exc}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(f"ERROR: {LINKS_JSON} not found", file=sys.stderr)
        sys.exit(1)

    from datetime import datetime, timezone
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    sections = build_sections(data)
    total_pills = sum(len(s["pills"]) for s in sections)
    stub_total  = sum(sum(1 for p in s["pills"] if p["stub"]) for s in sections)
    live_total  = total_pills - stub_total

    html_out = render_html(sections, generated_at)
    OUTPUT_HTML.write_text(html_out, encoding="utf-8")

    print(f"Written → {OUTPUT_HTML}")
    print(f"  Sections : {len(sections)}")
    print(f"  Pills    : {total_pills} total ({live_total} live, {stub_total} stub/placeholder)")

if __name__ == "__main__":
    main()
