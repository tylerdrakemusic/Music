"""Generate Phase alpha Icecast2/Liquidsoap assets for TJD Radio.

This tool prepares a Tyler-owned catalog playlist plus baseline Icecast and
Liquidsoap config files for the WSL2 proof-of-concept runtime.
"""

from __future__ import annotations

import argparse
from pathlib import Path

AUDIO_EXTS = {".mp3", ".wav", ".flac", ".ogg", ".m4a"}


def extract_artist_from_stem(stem: str) -> str:
    """Extract artist from 'Song - Artist' naming, defaulting to Tyler James Drake."""
    if " - " in stem:
        return stem.split(" - ", 1)[1].strip()
    return "Tyler James Drake"


def extract_title_from_stem(stem: str) -> str:
    """Extract title from 'Song - Artist' naming, preserving full stem if absent."""
    if " - " in stem:
        return stem.split(" - ", 1)[0].strip()
    return stem.strip()


def normalize_icecast_metadata(title: str, artist: str) -> tuple[str, str]:
    """Normalize Icecast metadata when MP3/ICY collapses artist and title into one field."""
    clean_title = title.strip()
    clean_artist = artist.strip()
    if clean_artist or " - " not in clean_title:
        return clean_title, clean_artist

    inferred_artist, inferred_title = clean_title.split(" - ", 1)
    return inferred_title.strip(), inferred_artist.strip()


def _escape_liquidsoap(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _to_runtime_path(path: Path) -> str:
    path_str = str(path).replace("\\", "/")
    drive = path.drive.rstrip(":")
    if drive and len(drive) == 1 and path.is_absolute():
        return f"/mnt/{drive.lower()}{path_str[2:]}"
    return path_str


def iter_tyler_catalog_audio(project_root: Path) -> list[Path]:
    """Return deterministic list of Tyler-owned audio assets for Phase alpha."""
    roots = [project_root / "catalog" / "masters", project_root / "catalog" / "ep"]
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for candidate in root.rglob("*"):
            if candidate.suffix.lower() not in AUDIO_EXTS:
                continue
            if not candidate.is_file() or candidate.stat().st_size < 10_000:
                continue
            files.append(candidate)
    return sorted(files)


def write_liquidsoap_playlist(audio_files: list[Path], playlist_path: Path) -> None:
    """Write Liquidsoap annotate() playlist entries for reliable metadata."""
    lines: list[str] = []
    for f in audio_files:
        stem = f.stem.replace("_", " ").replace("$", " ").strip()
        title = _escape_liquidsoap(extract_title_from_stem(stem))
        artist = _escape_liquidsoap(extract_artist_from_stem(stem))
        path_str = _escape_liquidsoap(_to_runtime_path(f))
        lines.append(f'annotate:title="{title}",artist="{artist}":{path_str}')
    playlist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_liquidsoap_config(playlist_path: Path, output_path: Path) -> None:
    """Write a minimal Liquidsoap config targeting local Icecast mount /stream."""
    playlist_str = _to_runtime_path(playlist_path)
    content = f"""# TJD Radio Phase alpha — Icecast2 + Liquidsoap
set(\"init.allow_root\", true)
set(\"log.stdout\", true)
set(\"log.file\", false)

# Playlist entries include annotate:title/artist metadata for now-playing visibility.
radio_tracks = playlist(mode=\"randomize\", reload_mode=\"watch\", \"{playlist_str}\")
radio = mksafe(radio_tracks)

output.icecast(
  %mp3(bitrate=192, samplerate=44100, stereo=true),
  host=\"127.0.0.1\",
  port=8000,
  password=\"CHANGE_ME_SOURCE_PASSWORD\",
  mount=\"/stream\",
  name=\"TJD Radio Phase alpha\",
  description=\"Tyler James Drake self-hosted radio POC\",
  genre=\"Rock, Blues, Folk, Alternative\",
  url=\"http://localhost:8000/stream\",
  public=false,
  icy_metadata=\"true\",
  radio
)
"""
    output_path.write_text(content, encoding="utf-8")


def write_icecast_config(output_path: Path) -> None:
    """Write baseline Icecast XML with /stream mount for local POC usage."""
    content = """<icecast>
  <location>Localhost</location>
  <admin>admin@localhost</admin>

  <limits>
    <clients>100</clients>
    <sources>2</sources>
    <queue-size>524288</queue-size>
    <client-timeout>30</client-timeout>
    <header-timeout>15</header-timeout>
    <source-timeout>10</source-timeout>
    <burst-on-connect>1</burst-on-connect>
    <burst-size>65535</burst-size>
  </limits>

  <authentication>
    <source-password>CHANGE_ME_SOURCE_PASSWORD</source-password>
    <relay-password>CHANGE_ME_RELAY_PASSWORD</relay-password>
    <admin-user>admin</admin-user>
    <admin-password>CHANGE_ME_ADMIN_PASSWORD</admin-password>
  </authentication>

  <hostname>localhost</hostname>
  <listen-socket>
    <port>8000</port>
  </listen-socket>

  <mount>
    <mount-name>/stream</mount-name>
    <public>0</public>
    <charset>UTF-8</charset>
  </mount>

  <fileserve>1</fileserve>
  <paths>
    <basedir>/usr/share/icecast2</basedir>
    <logdir>/var/log/icecast2</logdir>
    <webroot>/usr/share/icecast2/web</webroot>
    <adminroot>/usr/share/icecast2/admin</adminroot>
    <pidfile>/run/icecast2/icecast.pid</pidfile>
    <alias source=\"/\" destination=\"/status.xsl\"/>
  </paths>

  <logging>
    <accesslog>access.log</accesslog>
    <errorlog>error.log</errorlog>
    <loglevel>3</loglevel>
  </logging>

  <security>
    <chroot>0</chroot>
  </security>
</icecast>
"""
    output_path.write_text(content, encoding="utf-8")


def write_player_html(output_path: Path) -> None:
    """Write a simple static player page for mount playback checks."""
    content = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>TJD Radio Phase alpha Player</title>
  <style>
    body { font-family: Segoe UI, sans-serif; max-width: 760px; margin: 40px auto; padding: 0 16px; }
    .card { border: 1px solid #ddd; border-radius: 12px; padding: 20px; }
    h1 { margin-top: 0; }
    .muted { color: #555; }
  </style>
</head>
<body>
  <div class=\"card\">
    <h1>TJD Radio Phase alpha</h1>
    <p class=\"muted\">Icecast mount: http://localhost:8000/stream</p>
    <audio controls preload=\"none\" style=\"width:100%\">
      <source src=\"http://localhost:8000/stream\" type=\"audio/mpeg\">
      Your browser does not support HTML5 audio playback.
    </audio>
  </div>
</body>
</html>
"""
    output_path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare TJD Radio Phase alpha POC assets")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    output_dir = args.output_dir.resolve() if args.output_dir else (project_root / "output" / "radio_phase_alpha")
    output_dir.mkdir(parents=True, exist_ok=True)

    audio_files = iter_tyler_catalog_audio(project_root)
    if not audio_files:
        raise SystemExit("No Tyler-owned catalog audio files found under catalog/masters or catalog/ep")

    playlist_path = output_dir / "tyler_catalog_phase_alpha.liqlist"
    liquidsoap_path = output_dir / "tjd_radio_phase_alpha.liq"
    icecast_path = output_dir / "icecast_phase_alpha.xml"
    player_path = project_root / "reports" / "tjd_radio_phase_alpha_player.html"

    write_liquidsoap_playlist(audio_files, playlist_path)
    write_liquidsoap_config(playlist_path, liquidsoap_path)
    write_icecast_config(icecast_path)
    write_player_html(player_path)

    print(f"Generated {len(audio_files)} playlist entries")
    print(f"Playlist: {playlist_path}")
    print(f"Liquidsoap config: {liquidsoap_path}")
    print(f"Icecast config: {icecast_path}")
    print(f"Player page: {player_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
