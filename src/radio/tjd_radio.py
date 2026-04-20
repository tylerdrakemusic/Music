"""
TJD Radio — Self-hosted AI Radio Station for Tyler James Drake
Phase β: Flask HTTP audio stream + web player + crossfade + bumpers

Streams Tyler's catalog as a continuous internet radio station.
All listeners hear the same stream (shared broadcast, not on-demand).
Phase β adds crossfade between tracks and station-ID bumper injection.

Usage:
    C:\\G\\python.exe src/radio/tjd_radio.py [--port 8100] [--bitrate 192]
    C:\\G\\python.exe src/radio/tjd_radio.py --crossfade 3 --bumper-dir catalog/bumpers
"""

from __future__ import annotations

import argparse
import io
import json
import os
import random
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from flask import Flask, Response, jsonify, render_template_string

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CATALOG_ROOT = PROJECT_ROOT / "catalog"
BUMPER_DIR = CATALOG_ROOT / "bumpers"

# ---------------------------------------------------------------------------
# Playlist builder — scan catalog for playable audio
# ---------------------------------------------------------------------------
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".ogg", ".m4a"}


def build_playlist(roots: list[Path], shuffle: bool = True) -> list[dict]:
    """Scan directories for audio files and build a playlist."""
    tracks = []
    for root in roots:
        if not root.exists():
            continue
        for f in root.rglob("*"):
            if f.suffix.lower() in AUDIO_EXTS and f.stat().st_size > 10_000:
                tracks.append({
                    "path": str(f),
                    "title": f.stem.replace("$", " ").replace("_", " ").strip(),
                    "album": f.parent.name,
                    "format": f.suffix.lower().lstrip("."),
                })
    if shuffle:
        random.shuffle(tracks)
    return tracks


# ---------------------------------------------------------------------------
# Broadcast engine — transcodes audio to MP3 stream via ffmpeg
# ---------------------------------------------------------------------------
class RadioBroadcast:
    """Manages a continuous MP3 stream from a playlist using ffmpeg."""

    def __init__(self, playlist: list[dict], bitrate: int = 192):
        self.playlist = playlist
        self.bitrate = bitrate
        self._lock = threading.Lock()
        self._listeners: list[io.BytesIO] = []
        self._current_track: Optional[dict] = None
        self._track_index = 0
        self._running = False
        self._history: list[dict] = []

    @property
    def now_playing(self) -> Optional[dict]:
        return self._current_track

    @property
    def listener_count(self) -> int:
        with self._lock:
            return len(self._listeners)

    @property
    def history(self) -> list[dict]:
        return list(self._history[-20:])

    def add_listener(self) -> io.BytesIO:
        buf = io.BytesIO()
        with self._lock:
            self._listeners.append(buf)
        return buf

    def remove_listener(self, buf: io.BytesIO) -> None:
        with self._lock:
            if buf in self._listeners:
                self._listeners.remove(buf)

    def _next_track(self) -> dict:
        if not self.playlist:
            raise RuntimeError("Empty playlist")
        track = self.playlist[self._track_index % len(self.playlist)]
        self._track_index += 1
        # Re-shuffle when we loop
        if self._track_index >= len(self.playlist):
            self._track_index = 0
            random.shuffle(self.playlist)
        return track

    def _broadcast_chunk(self, data: bytes) -> None:
        with self._lock:
            dead = []
            for buf in self._listeners:
                try:
                    buf.write(data)
                except Exception:
                    dead.append(buf)
            for d in dead:
                self._listeners.remove(d)

    def run(self) -> None:
        """Main broadcast loop — runs in a background thread."""
        self._running = True
        print(f"[RADIO] Broadcasting {len(self.playlist)} tracks at {self.bitrate}kbps")

        while self._running and self.playlist:
            track = self._next_track()
            self._current_track = track
            self._history.append({
                "title": track["title"],
                "album": track["album"],
                "format": track["format"],
                "started_at": time.strftime("%H:%M:%S"),
            })
            print(f"[RADIO] ▶ Now playing: {track['title']} ({track['album']})")

            try:
                proc = subprocess.Popen(
                    [
                        "ffmpeg",
                        "-hide_banner",
                        "-loglevel", "error",
                        "-i", track["path"],
                        "-vn",                     # no video
                        "-acodec", "libmp3lame",
                        "-ab", f"{self.bitrate}k",
                        "-ar", "44100",
                        "-ac", "2",
                        "-f", "mp3",
                        "pipe:1",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

                while self._running:
                    chunk = proc.stdout.read(4096)
                    if not chunk:
                        break
                    self._broadcast_chunk(chunk)
                    # Pace the stream to roughly real-time
                    # 192kbps = 24000 bytes/sec → 4096 bytes ≈ 170ms
                    time.sleep(len(chunk) / (self.bitrate * 125))

                proc.wait(timeout=5)
            except Exception as e:
                print(f"[RADIO] Error playing {track['title']}: {e}")
                time.sleep(1)

        print("[RADIO] Broadcast stopped.")

    def stop(self) -> None:
        self._running = False


# ---------------------------------------------------------------------------
# Ring buffer for listener streams
# ---------------------------------------------------------------------------
class ListenerStream:
    """Thread-safe ring buffer that a listener reads from."""

    def __init__(self, maxsize: int = 512 * 1024):
        self._buf = bytearray()
        self._lock = threading.Lock()
        self._event = threading.Event()
        self._closed = False
        self._maxsize = maxsize

    def write(self, data: bytes) -> None:
        with self._lock:
            self._buf.extend(data)
            # Trim old data if buffer grows too large
            if len(self._buf) > self._maxsize:
                self._buf = self._buf[-self._maxsize:]
            self._event.set()

    def read(self, timeout: float = 2.0) -> bytes:
        self._event.wait(timeout=timeout)
        with self._lock:
            data = bytes(self._buf)
            self._buf.clear()
            self._event.clear()
        return data

    def close(self) -> None:
        self._closed = True
        self._event.set()

    @property
    def closed(self) -> bool:
        return self._closed


# ---------------------------------------------------------------------------
# Bumper / station-ID loader
# ---------------------------------------------------------------------------
def load_bumpers(bumper_dir: Path) -> list[dict]:
    """Load short audio clips used as station IDs between songs."""
    bumpers = []
    if not bumper_dir.exists():
        return bumpers
    for f in sorted(bumper_dir.iterdir()):
        if f.suffix.lower() in AUDIO_EXTS and f.stat().st_size > 1_000:
            bumpers.append({
                "path": str(f),
                "title": f"[Station ID] {f.stem}",
                "album": "TJD Radio",
                "format": f.suffix.lower().lstrip("."),
                "is_bumper": True,
            })
    return bumpers


class RadioBroadcastV2:
    """Upgraded broadcast engine — ListenerStream ring buffers + crossfade + bumpers."""

    def __init__(self, playlist: list[dict], bitrate: int = 192,
                 crossfade_sec: float = 0.0, bumpers: list[dict] | None = None,
                 bumper_every: int = 3):
        self.playlist = playlist
        self.bitrate = bitrate
        self.crossfade_sec = crossfade_sec
        self.bumpers = bumpers or []
        self.bumper_every = bumper_every  # play a bumper every N tracks
        self._lock = threading.Lock()
        self._listeners: list[ListenerStream] = []
        self._current_track: Optional[dict] = None
        self._track_index = 0
        self._songs_since_bumper = 0
        self._running = False
        self._history: list[dict] = []
        self._started_at: Optional[float] = None
        self._track_started: Optional[float] = None

    @property
    def now_playing(self) -> Optional[dict]:
        return self._current_track

    @property
    def listener_count(self) -> int:
        with self._lock:
            return len(self._listeners)

    @property
    def history(self) -> list[dict]:
        return list(self._history[-20:])

    @property
    def uptime_sec(self) -> float:
        if self._started_at is None:
            return 0.0
        return time.time() - self._started_at

    @property
    def track_elapsed_sec(self) -> float:
        if self._track_started is None:
            return 0.0
        return time.time() - self._track_started

    def add_listener(self) -> ListenerStream:
        stream = ListenerStream()
        with self._lock:
            self._listeners.append(stream)
        return stream

    def remove_listener(self, stream: ListenerStream) -> None:
        stream.close()
        with self._lock:
            if stream in self._listeners:
                self._listeners.remove(stream)

    def _next_track(self) -> dict:
        if not self.playlist:
            raise RuntimeError("Empty playlist")
        track = self.playlist[self._track_index % len(self.playlist)]
        self._track_index += 1
        if self._track_index >= len(self.playlist):
            self._track_index = 0
            random.shuffle(self.playlist)
        return track

    def _broadcast_chunk(self, data: bytes) -> None:
        with self._lock:
            dead = []
            for stream in self._listeners:
                try:
                    stream.write(data)
                except Exception:
                    dead.append(stream)
            for d in dead:
                d.close()
                self._listeners.remove(d)

    def _build_ffmpeg_cmd(self, path: str, fade_in: float = 0, fade_out: float = 0) -> list[str]:
        """Build ffmpeg command with optional fade filters."""
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", path, "-vn",
        ]
        # Apply crossfade filters if requested
        filters = []
        if fade_in > 0:
            filters.append(f"afade=t=in:st=0:d={fade_in}")
        if fade_out > 0:
            filters.append(f"afade=t=out:st=0:d={fade_out}:curve=tri")
        if filters:
            cmd += ["-af", ",".join(filters)]
        cmd += [
            "-acodec", "libmp3lame",
            "-ab", f"{self.bitrate}k",
            "-ar", "44100", "-ac", "2",
            "-f", "mp3", "pipe:1",
        ]
        return cmd

    def _play_audio(self, path: str, fade_in: float = 0, fade_out: float = 0) -> None:
        """Transcode a single file to the stream with optional fades."""
        cmd = self._build_ffmpeg_cmd(path, fade_in, fade_out)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        chunk_size = 4096
        pace = chunk_size / (self.bitrate * 125)
        while self._running:
            chunk = proc.stdout.read(chunk_size)
            if not chunk:
                break
            self._broadcast_chunk(chunk)
            time.sleep(pace)
        proc.wait(timeout=5)

    def _should_play_bumper(self) -> bool:
        return (self.bumpers
                and self.bumper_every > 0
                and self._songs_since_bumper >= self.bumper_every)

    def run(self) -> None:
        self._running = True
        self._started_at = time.time()
        xf = self.crossfade_sec
        bumper_count = len(self.bumpers)
        print(f"[RADIO] Broadcasting {len(self.playlist)} tracks at {self.bitrate}kbps")
        if xf > 0:
            print(f"[RADIO] Crossfade: {xf}s")
        if bumper_count:
            print(f"[RADIO] {bumper_count} bumper(s), every {self.bumper_every} tracks")

        while self._running and self.playlist:
            # Inject bumper between songs if due
            if self._should_play_bumper():
                bumper = random.choice(self.bumpers)
                self._current_track = bumper
                self._track_started = time.time()
                print(f"[RADIO] 🎙 Bumper: {bumper['title']}")
                try:
                    self._play_audio(bumper["path"])
                except Exception as e:
                    print(f"[RADIO] Bumper error: {e}")
                self._songs_since_bumper = 0

            track = self._next_track()
            self._current_track = track
            self._track_started = time.time()
            self._history.append({
                "title": track["title"],
                "album": track["album"],
                "format": track["format"],
                "started_at": time.strftime("%H:%M:%S"),
            })
            print(f"[RADIO] ▶ Now playing: {track['title']} ({track['album']})")

            try:
                self._play_audio(
                    track["path"],
                    fade_in=xf if xf > 0 else 0,
                    fade_out=xf if xf > 0 else 0,
                )
                self._songs_since_bumper += 1
            except Exception as e:
                print(f"[RADIO] Error playing {track['title']}: {e}")
                time.sleep(1)

        print("[RADIO] Broadcast stopped.")

    def stop(self) -> None:
        self._running = False


# ---------------------------------------------------------------------------
# Web player HTML
# ---------------------------------------------------------------------------
WEB_PLAYER_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TJD Radio</title>
<style>
  :root {
    --bg: #0a0a0f;
    --surface: #14141f;
    --surface2: #1e1e2e;
    --accent: #e44;
    --accent-glow: rgba(238,68,68,0.3);
    --gold: #d4a017;
    --text: #e8e8f0;
    --dim: #888;
    --mono: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
  }
  .hero {
    text-align: center;
    padding: 40px 20px 20px;
  }
  .hero h1 {
    font-size: 2.8em;
    letter-spacing: 4px;
    background: linear-gradient(135deg, var(--accent), var(--gold));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    text-transform: uppercase;
  }
  .hero .sub {
    color: var(--dim);
    font-size: 0.95em;
    margin-top: 6px;
    letter-spacing: 2px;
  }

  .player-card {
    background: var(--surface);
    border-radius: 20px;
    padding: 32px;
    width: min(500px, 90vw);
    margin: 24px auto;
    text-align: center;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
    position: relative;
    overflow: hidden;
  }
  .player-card::before {
    content: '';
    position: absolute;
    top: -2px; left: -2px; right: -2px; bottom: -2px;
    border-radius: 22px;
    background: linear-gradient(135deg, var(--accent), transparent 40%, var(--gold));
    z-index: -1;
    opacity: 0.4;
  }

  .vinyl {
    width: 160px; height: 160px;
    border-radius: 50%;
    background: conic-gradient(from 0deg, #111, #222, #111, #333, #111);
    margin: 0 auto 20px;
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 0 24px rgba(0,0,0,0.6);
    position: relative;
  }
  .vinyl.spinning { animation: spin 3s linear infinite; }
  .vinyl-hole {
    width: 28px; height: 28px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 12px var(--accent-glow);
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  @keyframes pulse { 0%,100% { opacity:0.6; } 50% { opacity:1; } }

  .now-playing-label {
    font-size: 0.75em;
    text-transform: uppercase;
    letter-spacing: 3px;
    color: var(--accent);
    margin-bottom: 6px;
    animation: pulse 2s ease-in-out infinite;
  }
  .track-title {
    font-size: 1.5em;
    font-weight: 700;
    margin-bottom: 4px;
  }
  .track-album {
    color: var(--dim);
    font-size: 0.9em;
    margin-bottom: 20px;
  }

  .play-btn {
    width: 64px; height: 64px;
    border-radius: 50%;
    border: none;
    background: var(--accent);
    color: #fff;
    font-size: 26px;
    cursor: pointer;
    box-shadow: 0 4px 20px var(--accent-glow);
    transition: transform 0.15s, box-shadow 0.15s;
    display: inline-flex; align-items: center; justify-content: center;
  }
  .play-btn:hover { transform: scale(1.08); box-shadow: 0 6px 28px var(--accent-glow); }
  .play-btn:active { transform: scale(0.96); }

  .volume-row {
    display: flex;
    align-items: center;
    gap: 10px;
    justify-content: center;
    margin-top: 16px;
  }
  .volume-row label { color: var(--dim); font-size: 0.85em; }
  input[type=range] {
    -webkit-appearance: none;
    width: 120px; height: 4px;
    background: var(--surface2);
    border-radius: 2px;
    outline: none;
  }
  input[type=range]::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 14px; height: 14px;
    border-radius: 50%;
    background: var(--accent);
    cursor: pointer;
  }

  .stats-bar {
    display: flex;
    justify-content: center;
    gap: 28px;
    margin-top: 20px;
    font-size: 0.82em;
    color: var(--dim);
  }
  .stats-bar .num { color: var(--gold); font-weight: 700; }

  .history-panel {
    background: var(--surface);
    border-radius: 16px;
    padding: 20px;
    width: min(500px, 90vw);
    margin: 0 auto 40px;
  }
  .history-panel h3 {
    font-size: 0.9em;
    text-transform: uppercase;
    letter-spacing: 2px;
    color: var(--dim);
    margin-bottom: 12px;
  }
  .history-item {
    display: flex;
    justify-content: space-between;
    padding: 6px 0;
    border-bottom: 1px solid var(--surface2);
    font-size: 0.88em;
  }
  .history-item:last-child { border: none; }
  .history-item .time { color: var(--dim); font-family: var(--mono); font-size: 0.8em; }

  .badge {
    display: inline-block;
    padding: 3px 8px;
    border-radius: 6px;
    font-size: 0.7em;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-weight: 600;
  }
  .badge-live { background: var(--accent); color: #fff; animation: pulse 1.5s ease-in-out infinite; }
  .badge-ai { background: #2563eb; color: #fff; }

  footer {
    text-align: center;
    padding: 20px;
    color: var(--dim);
    font-size: 0.75em;
  }
</style>
</head>
<body>

<div class="hero">
  <h1>TJD Radio</h1>
  <div class="sub">Tyler James Drake — 24/7 Streaming</div>
</div>

<div class="player-card">
  <div class="vinyl" id="vinyl">
    <div class="vinyl-hole"></div>
  </div>
  <div class="now-playing-label"><span class="badge badge-live">LIVE</span> NOW PLAYING</div>
  <div class="track-title" id="trackTitle">Loading...</div>
  <div class="track-album" id="trackAlbum">&nbsp;</div>

  <button class="play-btn" id="playBtn" onclick="togglePlay()">&#9654;</button>

  <div class="volume-row">
    <label>VOL</label>
    <input type="range" id="vol" min="0" max="100" value="80" oninput="setVol(this.value)">
  </div>

  <div class="stats-bar">
    <div>Listeners: <span class="num" id="listeners">0</span></div>
    <div>Tracks: <span class="num" id="totalTracks">0</span></div>
    <div>Uptime: <span class="num" id="uptime">0:00</span></div>
  </div>
</div>

<div class="history-panel">
  <h3>Recently Played</h3>
  <div id="historyList"><div class="history-item">Waiting for tracks...</div></div>
</div>

<footer>
  &copy; 2026 Tyler James Drake &middot; TJD Radio Phase &beta; &middot; Self-hosted AI Radio
</footer>

<script>
const audio = new Audio();
audio.volume = 0.8;
let playing = false;

function togglePlay() {
  if (playing) {
    audio.pause();
    audio.src = '';
    playing = false;
    document.getElementById('playBtn').innerHTML = '&#9654;';
    document.getElementById('vinyl').classList.remove('spinning');
  } else {
    // Cache-bust to join the live stream fresh
    audio.src = '/stream?t=' + Date.now();
    audio.play().catch(e => console.error('Play error:', e));
    playing = true;
    document.getElementById('playBtn').innerHTML = '&#9724;';
    document.getElementById('vinyl').classList.add('spinning');
  }
}

function setVol(v) { audio.volume = v / 100; }

// Poll now-playing metadata
async function pollMeta() {
  try {
    const r = await fetch('/api/now_playing');
    const d = await r.json();
    document.getElementById('trackTitle').textContent = d.title || 'Silence...';
    document.getElementById('trackAlbum').textContent = d.album || '';
    document.getElementById('listeners').textContent = d.listeners;
    document.getElementById('totalTracks').textContent = d.total_tracks;
    const m = Math.floor(d.uptime_sec / 60);
    const s = Math.floor(d.uptime_sec % 60);
    document.getElementById('uptime').textContent = m + ':' + String(s).padStart(2, '0');

    const hist = d.history || [];
    const hEl = document.getElementById('historyList');
    if (hist.length) {
      hEl.innerHTML = hist.reverse().map(h =>
        `<div class="history-item">
          <span>${h.title} <span style="color:var(--dim);font-size:0.8em">· ${h.album}</span></span>
          <span class="time">${h.started_at}</span>
        </div>`
      ).join('');
    }
  } catch(e) {}
}
setInterval(pollMeta, 3000);
pollMeta();
</script>

</body>
</html>
"""

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)
broadcast: Optional[RadioBroadcastV2] = None


@app.route("/")
def index():
    return render_template_string(WEB_PLAYER_HTML)


@app.route("/stream")
def stream():
    """MP3 audio stream endpoint — each connection gets a listener buffer."""
    if broadcast is None:
        return "Radio not started", 503

    listener = broadcast.add_listener()

    def generate():
        try:
            while not listener.closed:
                data = listener.read(timeout=2.0)
                if data:
                    yield data
                elif not broadcast._running:
                    break
        finally:
            broadcast.remove_listener(listener)

    return Response(
        generate(),
        mimetype="audio/mpeg",
        headers={
            "Cache-Control": "no-cache, no-store",
            "Connection": "keep-alive",
            "Content-Type": "audio/mpeg",
            "icy-name": "TJD Radio",
            "icy-genre": "Rock; Blues; Folk; Alternative",
            "icy-br": str(broadcast.bitrate),
            "icy-description": "Tyler James Drake - Self-hosted AI Radio",
        },
    )


@app.route("/api/now_playing")
def now_playing():
    if broadcast is None:
        return jsonify({"title": "Offline", "album": "", "listeners": 0})
    track = broadcast.now_playing
    return jsonify({
        "title": track["title"] if track else "Starting...",
        "album": track["album"] if track else "",
        "format": track.get("format", "") if track else "",
        "listeners": broadcast.listener_count,
        "total_tracks": len(broadcast.playlist),
        "uptime_sec": broadcast.uptime_sec,
        "elapsed_sec": broadcast.track_elapsed_sec,
        "history": broadcast.history,
    })


@app.route("/api/playlist")
def playlist_api():
    if broadcast is None:
        return jsonify([])
    return jsonify([
        {"title": t["title"], "album": t["album"], "format": t["format"]}
        for t in broadcast.playlist
    ])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    global broadcast

    parser = argparse.ArgumentParser(description="TJD Radio — Self-hosted AI Radio Station")
    parser.add_argument("--port", type=int, default=8100, help="HTTP port (default 8100)")
    parser.add_argument("--bitrate", type=int, default=192, help="Stream bitrate kbps (default 192)")
    parser.add_argument("--crossfade", type=float, default=2.0, help="Crossfade seconds between tracks (default 2.0, 0=off)")
    parser.add_argument("--bumper-dir", type=str, default=str(BUMPER_DIR), help="Directory with station-ID bumper audio")
    parser.add_argument("--bumper-every", type=int, default=3, help="Play a bumper every N tracks (default 3)")
    parser.add_argument("--extra-dirs", nargs="*", default=[], help="Extra directories to scan for audio")
    args = parser.parse_args()

    # Build playlist from EP catalog
    scan_dirs = [
        CATALOG_ROOT / "ep" / "Marigold",
        CATALOG_ROOT / "ep" / "Get Out",
        CATALOG_ROOT / "ep" / "What I do",
    ]
    for d in args.extra_dirs:
        scan_dirs.append(Path(d))

    playlist = build_playlist(scan_dirs)
    if not playlist:
        print("[RADIO] No audio files found in catalog. Exiting.")
        sys.exit(1)

    # Filter to prefer MP3 masters for efficiency
    mp3s = [t for t in playlist if t["format"] == "mp3"]
    if mp3s:
        playlist = mp3s

    # Load bumpers / station IDs
    bumpers = load_bumpers(Path(args.bumper_dir))
    if bumpers:
        print(f"[RADIO] Loaded {len(bumpers)} bumper(s):")
        for b in bumpers:
            print(f"  🎙 {b['title']}")

    print(f"[RADIO] Loaded {len(playlist)} tracks:")
    for t in playlist:
        print(f"  · {t['title']} ({t['album']}, {t['format']})")

    broadcast = RadioBroadcastV2(
        playlist,
        bitrate=args.bitrate,
        crossfade_sec=args.crossfade,
        bumpers=bumpers,
        bumper_every=args.bumper_every,
    )

    # Start broadcast in background thread
    radio_thread = threading.Thread(target=broadcast.run, daemon=True)
    radio_thread.start()

    print(f"\n🎵 TJD Radio → http://localhost:{args.port}")
    print(f"   Stream  → http://localhost:{args.port}/stream")
    print(f"   API     → http://localhost:{args.port}/api/now_playing\n")

    app.run(host="0.0.0.0", port=args.port, threaded=True)


if __name__ == "__main__":
    main()
