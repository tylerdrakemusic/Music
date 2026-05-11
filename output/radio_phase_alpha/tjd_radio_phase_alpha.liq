# TJD Radio Phase alpha — Icecast2 + Liquidsoap
set("init.allow_root", true)
set("log.stdout", true)
set("log.file", false)

# Playlist entries include annotate:title/artist metadata for now-playing visibility.
radio_tracks = playlist(mode="normal", reload_mode="watch", "/mnt/f/❤Music/output/radio_phase_alpha/muzic_primary_phase_alpha.liqlist")
radio = mksafe(radio_tracks)

output.icecast(
  %mp3(bitrate=192, samplerate=44100, stereo=true),
  host="127.0.0.1",
  port=8000,
  user="source",
  password="CHANGE_ME_SOURCE_PASSWORD",
  mount="/stream",
  name="TJD Radio Phase alpha",
  description="Tyler James Drake self-hosted radio POC",
  genre="Rock, Blues, Folk, Alternative",
  url="http://localhost:8000/stream",
  public=false,
  icy_metadata="true",
  radio
)
