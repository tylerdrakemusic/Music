# ❤Music — Scale Trainer (Fly.io cloud deploy)
# FR-20260808-scale-trainer-flyio-deploy
#
# Slim, cloud-only image for musician_training_ui.py. Exercise cards, the
# catalog browser, and local session launching all depend on files that only
# exist on Tyler's machine (G:\Muzic, C:\G\python.exe, the guitar_exercises
# table) — those routes are disabled by default here via env-var feature
# flags (FR-20260808) so the image only needs to serve the Scales tab.
FROM python:3.11-slim

WORKDIR /app

# Only the runtime deps the Scales-tab code path needs. Excludes demucs
# (stem isolation, heavyweight ML dep) and pytest-mock (test-only) — neither
# is reachable from this image's always-on routes.
RUN pip install --no-cache-dir \
    "flask>=3.0,<4.0" \
    "mutagen>=1.47,<2.0" \
    "python-docx>=1.1" \
    "pypdf>=4.0" \
    "pronouncing>=0.2" \
    "requests>=2.31,<3.0"

# Includes the bundled scale count-in WAVs for keyless Fly.io deploys.
# Instructor audio remains optional and requires ELEVENLABS_API_KEY.
COPY src/ src/
COPY click/ click/

# Cloud-only defaults: exercise cards / catalog / session logging need local
# song files and heartmusic.db access that this image does not ship with.
# Override at runtime (e.g. `-e ENABLE_EXERCISE_CARDS=true`) if that ever
# changes.
ENV ENABLE_EXERCISE_CARDS=false
ENV ENABLE_SCALE_LOG=false
ENV PORT=8080

EXPOSE 8080

# Shell form so ${PORT} expands at container start (Fly.io convention).
CMD python src/training/musician_training_ui.py --host 0.0.0.0 --port ${PORT}
