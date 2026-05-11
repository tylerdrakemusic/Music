# TJD Radio Icecast-Primary Architecture

## Intent
Unify listener experience behind one canonical stream path by making Icecast the default backend for the local TJD panel, while keeping the legacy Flask broadcaster as explicit fallback.

## Runtime boundary
- Local panel (`src/radio/tjd_radio.py`) serves UI + API on `:8100`
- Default panel stream route (`/stream`) redirects to Icecast mount (`:8000/stream`)
- Default now-playing route (`/api/now_playing`) reads Icecast status JSON (`:8000/status-json.xsl`)
- Legacy local broadcaster remains available only when launched with `--backend local`

## Source policy
- Primary source: `G:/Muzic`
- Fallback source: `catalog/masters` + `catalog/ep`
- Policy applies to panel source snapshot and fallback behavior to keep metadata/ops aligned with station intent

## Exposure model
Icecast itself controls public accessibility:
1. Local-only: bind/listen on localhost only (not internet-facing)
2. LAN-only: allow local network access
3. Internet-facing: explicit host/network exposure, reverse proxy/TLS, and firewall controls

The migration does not force internet exposure; it standardizes the internal interface.

## Diagram
See architecture diagram:
- `f:/⊕Workspace/diagrams/music-icecast-primary-architecture.mmd`

## Verification summary
Implementation smoke checks validated:
- `GET /api/now_playing` via local panel in Icecast mode returns normalized artist/title
- `GET /stream` via local panel resolves to Icecast stream URL
- Targeted radio tests pass for source-priority and metadata normalization helpers
