# TJD Radio Phase alpha — Icecast2 + Liquidsoap
set("log.stdout", true)
set("log.file", false)

# Playlist entries include annotate:title/artist metadata for now-playing visibility.
radio_tracks = playlist(mode="randomize", reload_mode="watch", "F:/❤Music/output/radio_phase_alpha/tyler_catalog_phase_alpha.liqlist")
radio = smart_crossfade(fade_in=2.0, fade_out=2.0, radio_tracks)

output.icecast(
  %mp3(bitrate=192, samplerate=44100, stereo=true),
  host="127.0.0.1",
  port=8000,
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
