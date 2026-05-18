"""Generate the Artist Links Panel HTML.

Reads studio_master/linkTyler.json and emits reports/artist_links_panel.html —
a self-contained dark panel with an accordion layout: one row per platform,
expandable to show named artist profile links (Tyler James Drake / EchoTy).

Sections: Streaming & Distribution · Social Media · Payment
Stub platforms (placeholder IDs) are hidden by default with a reveal toggle.

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
# Constants
# ---------------------------------------------------------------------------

_STUB_PATTERNS = re.compile(
    r"yourartistid|yourtrackid|yourprofile2|yoursong|yourband|example\.com",
    re.IGNORECASE,
)

# Platforms classified as streaming services (vs pure distribution/aggregator)
_STREAMING = {
    "amazon_music", "apple_music", "itunes", "anghami", "audius", "boomplay",
    "claro_musica", "deezer", "flo", "iheartradio", "joox", "kuack_media",
    "medianet", "netease", "pandora", "qobuz", "saavn", "soundcloud", "spotify",
    "tencent", "tidal", "tiktok", "youtube_music", "adaptr", "instagram_facebook",
}

def _si(slug: str, color: str, alt: str) -> str:
    """Return a Simple Icons CDN <img> tag."""
    return (
        f'<img src="https://cdn.simpleicons.org/{slug}/{color}"'
        f' width="18" height="18" alt="{alt}" style="vertical-align:middle;">'
    )

_PLATFORM_META: dict[str, tuple[str, str]] = {
    "facebook":           (_si("facebook",     "1877F2", "Facebook"),       "#1877f2"),
    "instagram":          (_si("instagram",    "E1306C", "Instagram"),      "#e1306c"),
    "instagram_facebook": (_si("instagram",    "E1306C", "Instagram"),      "#e1306c"),
    "tiktok":             (_si("tiktok",       "010101", "TikTok"),         "#010101"),
    "whatsapp":           (_si("whatsapp",     "25D366", "WhatsApp"),       "#25d366"),
    "x":                  (_si("x",            "000000", "X"),              "#1a1a1a"),
    "venmo":              (_si("venmo",        "3D95CE", "Venmo"),          "#3d95ce"),
    "paypal":             (_si("paypal",       "003087", "PayPal"),         "#003087"),
    "amazon_music":       (_si("amazonmusic",  "00A8E0", "Amazon Music"),   "#00a8e0"),
    "apple_music":        (_si("applemusic",   "FC3C44", "Apple Music"),    "#fc3c44"),
    "itunes":             (_si("applemusic",   "FC3C44", "Apple Music"),    "#fc3c44"),
    "audius":             (_si("audius",       "7E1BCC", "Audius"),         "#7e1bcc"),
    "bandcamp":           (_si("bandcamp",     "1DA0C3", "Bandcamp"),       "#1da0c3"),
    "boomplay":           ("🎧", "#f04124"),
    "deezer":             (_si("deezer",       "EF5466", "Deezer"),         "#ef5466"),
    "distrokid":          ("📦", "#4a90e2"),
    "pandora":            (_si("pandora",      "3668FF", "Pandora"),        "#3668ff"),
    "soundcloud":         (_si("soundcloud",   "FF5500", "SoundCloud"),     "#ff5500"),
    "spotify":            (_si("spotify",      "1DB954", "Spotify"),        "#1db954"),
    "tidal":              (_si("tidal",        "2D2D2D", "Tidal"),          "#2d2d2d"),
    "youtube_music":      (_si("youtubemusic", "FF0000", "YouTube Music"),  "#ff0000"),
    "anghami":            (_si("anghami",      "F54033", "Anghami"),        "#f54033"),
    "claro_musica":       ("🎵", "#e63c2f"),
    "flo":                ("🎵", "#ff7300"),
    "iheartradio":        (_si("iheartradio",  "CC0000", "iHeartRadio"),    "#cc0000"),
    "joox":               ("🎵", "#00b050"),
    "kuack_media":        ("🎵", "#666"),
    "medianet":           ("🎵", "#666"),
    "netease":            ("🎵", "#cc0000"),
    "qobuz":              ("🎵", "#4a90d9"),
    "saavn":              ("🎵", "#2bc5b4"),
    "tencent":            ("🎵", "#0abf53"),
    "adaptr":             ("🎵", "#666"),
}

# Known URL fragments to identify artist persona
_TJD_TOKENS = (
    "tylerjamesdrake", "tyler-james-drake", "tyler_james_drake",
    "1747192774", "b0cwyssmtg", "arwjvpjfv22cx6x", "47880609",
    "256748002", "90787115", "ucm1zknvfv34a9qkr0lyojq", "2pcvpdydzk",
    "b0d4kh",  # What I Do amazon ASIN prefix
)
_ECHOTY_TOKENS = (
    "echoty", "1734067005", "b0cwyrdnf9", "arjxtk9pkkmf77v",
    "46217927", "256747992", "86134137", "ucfeh8pygirq590dvrooholm",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_stub(url: str) -> bool:
    return bool(_STUB_PATTERNS.search(url))

def _is_url(value: str) -> bool:
    v = value.strip()
    return v.startswith(("http://", "https://", "spotify:"))

def _platform_meta(key: str) -> tuple[str, str]:
    return _PLATFORM_META.get(key.lower(), ("🔗", "#444"))

def _clean_name(raw: str) -> str:
    replacements = {
        "amazon_music": "Amazon Music",
        "apple_music": "Apple Music",
        "youtube_music": "YouTube Music",
        "iheartradio": "iHeartRadio",
        "soundcloud": "SoundCloud",
        "bandcamp": "Bandcamp",
        "distrokid": "DistroKid",
        "claro_musica": "Claro Música",
        "instagram_facebook": "Instagram/Facebook",
        "netease": "NetEase",
        "kuack_media": "Kuack Media",
        "saavn": "JioSaavn",
    }
    return replacements.get(raw.lower(), raw.replace("_", " ").title())

def _detect_artist(url: str, idx: int) -> str:
    u = url.lower()
    if any(t in u for t in _TJD_TOKENS):
        return "Tyler James Drake"
    if any(t in u for t in _ECHOTY_TOKENS):
        return "EchoTy"
    return "Tyler James Drake" if idx == 0 else "EchoTy" if idx == 1 else f"Profile {idx + 1}"

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

def _build_platform_entry(key: str, raw_urls: list[str]) -> dict | None:
    """Build a platform accordion entry from a list of raw URL strings."""
    links: list[dict] = []
    for i, raw in enumerate(raw_urls):
        if not _is_url(raw):
            continue
        stub = _is_stub(raw)
        artist = _detect_artist(raw, i)
        links.append({"url": raw, "artist": artist, "stub": stub})
    if not links:
        return None
    all_stub = all(lk["stub"] for lk in links)
    icon, color = _platform_meta(key)
    return {
        "key": key,
        "name": _clean_name(key),
        "icon": icon,
        "color": color,
        "links": links,
        "all_stub": all_stub,
    }

def build_sections(data: dict) -> list[dict]:
    sections: list[dict] = []

    # --- Social Media ---
    platforms = []
    for platform, urls in data.get("social_media", {}).items():
        entry = _build_platform_entry(platform, urls)
        if entry:
            platforms.append(entry)
    if platforms:
        sections.append({"title": "Social Media", "platforms": platforms})

    # --- Payment ---
    platforms = []
    for platform, urls in data.get("payment", {}).items():
        entry = _build_platform_entry(platform, urls)
        if entry:
            platforms.append(entry)
    if platforms:
        sections.append({"title": "Payment", "platforms": platforms})

    # --- Streaming & Distribution ---
    platforms = []
    for platform, platform_data in data.get("distribution_platforms", {}).items():
        if not isinstance(platform_data, dict):
            continue
        artist_links = platform_data.get("artist_links", [])
        entry = _build_platform_entry(platform, artist_links)
        if entry:
            platforms.append(entry)
    if platforms:
        sections.append({"title": "Streaming & Distribution", "platforms": platforms})

    return sections

# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

def _link_html(lk: dict) -> str:
    url    = html.escape(lk["url"])
    artist = html.escape(lk["artist"])
    if lk["stub"]:
        return f'<span class="artist-link stub" title="Placeholder — fill in real ID">{artist} <span class="needs-id">needs ID</span></span>'
    return f'<a class="artist-link" href="{url}" target="_blank" rel="noopener noreferrer">{artist} ↗</a>'

def _accordion_html(p: dict) -> str:
    raw_icon = p["icon"]
    icon  = raw_icon if raw_icon.startswith("<img") else html.escape(raw_icon)
    name  = html.escape(p["name"])
    color = html.escape(p["color"])
    links_html = "\n          ".join(_link_html(lk) for lk in p["links"])
    live_count = sum(1 for lk in p["links"] if not lk["stub"])
    stub_cls   = ' class="stub-platform"' if p["all_stub"] else ""
    count_note = f'<span class="link-count">{live_count} profile{"s" if live_count != 1 else ""}</span>' if live_count else '<span class="link-count stub-count">needs setup</span>'
    return f"""    <details{stub_cls}>
      <summary style="--platform-color:{color};">
        <span class="platform-icon">{icon}</span>
        <span class="platform-name">{name}</span>
        {count_note}
      </summary>
      <div class="platform-links">
        {links_html}
      </div>
    </details>"""

def render_html(sections: list[dict], generated_at: str) -> str:
    all_stub_count = sum(
        sum(1 for p in sec["platforms"] if p["all_stub"])
        for sec in sections
    )
    sections_html = ""
    for sec in sections:
        live_platforms = [p for p in sec["platforms"] if not p["all_stub"]]
        stub_platforms = [p for p in sec["platforms"] if p["all_stub"]]

        live_html = "\n".join(_accordion_html(p) for p in live_platforms)
        stub_html = "\n".join(_accordion_html(p) for p in stub_platforms) if stub_platforms else ""

        stub_block = ""
        if stub_platforms:
            n = len(stub_platforms)
            stub_block = f"""
    <div class="stub-group" hidden>
      {stub_html}
    </div>"""

        sections_html += f"""
  <section class="link-section">
    <h2>{html.escape(sec['title'])}</h2>
    <div class="accordion">
{live_html}
    </div>{stub_block}
  </section>"""

    reveal_btn = ""
    if all_stub_count:
        reveal_btn = f'<button class="reveal-stubs" onclick="toggleStubs(this)">Show {all_stub_count} platform{"s" if all_stub_count != 1 else ""} needing setup ▼</button>'

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
      padding: 24px 28px;
      min-height: 100vh;
    }}
    header {{
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 32px;
      border-bottom: 1px solid #222;
      padding-bottom: 16px;
    }}
    header h1 {{ font-size: 1.4rem; font-weight: 700; flex: 1; }}
    header .generated {{ font-size: 0.72rem; color: #444; }}
    .link-section {{ margin-bottom: 32px; }}
    .link-section h2 {{
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: #555;
      margin-bottom: 10px;
    }}
    .accordion {{ display: flex; flex-direction: column; gap: 4px; }}
    details {{
      background: #141414;
      border: 1px solid #222;
      border-radius: 8px;
      overflow: hidden;
    }}
    details[open] {{ border-color: #333; }}
    summary {{
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 14px;
      cursor: pointer;
      user-select: none;
      list-style: none;
      border-left: 3px solid var(--platform-color, #444);
    }}
    summary::-webkit-details-marker {{ display: none; }}
    summary:hover {{ background: #1a1a1a; }}
    .platform-icon {{ font-size: 1rem; width: 22px; text-align: center; flex-shrink: 0; }}
    .platform-name {{ font-size: 0.88rem; font-weight: 600; flex: 1; }}
    .link-count {{
      font-size: 0.7rem;
      color: #555;
      background: #1e1e1e;
      padding: 2px 8px;
      border-radius: 99px;
      white-space: nowrap;
    }}
    .stub-count {{ color: #3a3a3a; }}
    .platform-links {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      padding: 10px 14px 12px 48px;
      border-top: 1px solid #1e1e1e;
    }}
    .artist-link {{
      font-size: 0.82rem;
      color: #aaa;
      text-decoration: none;
      padding: 4px 10px;
      border-radius: 6px;
      background: #1e1e1e;
      border: 1px solid #2a2a2a;
      transition: color 0.12s, background 0.12s;
      white-space: nowrap;
    }}
    .artist-link:hover {{ color: #fff; background: #2a2a2a; }}
    .artist-link.stub {{ color: #3a3a3a; cursor: default; }}
    .needs-id {{
      font-size: 0.68rem;
      background: #2a1a00;
      color: #664400;
      padding: 1px 5px;
      border-radius: 4px;
      margin-left: 4px;
    }}
    .stub-platform summary {{ opacity: 0.45; }}
    .reveal-stubs {{
      display: block;
      margin: 8px auto 0;
      background: none;
      border: 1px dashed #2a2a2a;
      color: #444;
      font-size: 0.75rem;
      padding: 6px 16px;
      border-radius: 99px;
      cursor: pointer;
      transition: color 0.12s, border-color 0.12s;
    }}
    .reveal-stubs:hover {{ color: #666; border-color: #444; }}
    footer {{
      margin-top: 40px;
      font-size: 0.68rem;
      color: #2a2a2a;
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
  {reveal_btn}
  <footer>
    Source: studio_master/linkTyler.json &nbsp;·&nbsp; ❤Music &nbsp;·&nbsp; Tyler James Drake
  </footer>
  <script>
    function toggleStubs(btn) {{
      const groups = document.querySelectorAll('.stub-group');
      const hidden = groups[0]?.hidden;
      groups.forEach(g => g.hidden = !hidden);
      btn.textContent = hidden
        ? btn.textContent.replace('Show', 'Hide').replace('▼', '▲')
        : btn.textContent.replace('Hide', 'Show').replace('▲', '▼');
    }}
  </script>
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
    live_platforms = sum(sum(1 for p in s["platforms"] if not p["all_stub"]) for s in sections)
    stub_platforms  = sum(sum(1 for p in s["platforms"] if p["all_stub"]) for s in sections)

    html_out = render_html(sections, generated_at)
    OUTPUT_HTML.write_text(html_out, encoding="utf-8")

    print(f"Written → {OUTPUT_HTML}")
    print(f"  Sections : {len(sections)}")
    print(f"  Platforms: {live_platforms + stub_platforms} total ({live_platforms} live, {stub_platforms} stub/hidden)")

if __name__ == "__main__":
    main()
