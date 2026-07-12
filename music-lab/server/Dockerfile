FROM python:3.12-slim

WORKDIR /app
# sqlite3 = the CLI shell (separate from Python's built-in sqlite3 module) - used to
# poke at /data/library.db directly, e.g. `docker compose exec server sqlite3 ...`
RUN apt-get update && apt-get install -y --no-install-recommends sqlite3 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir flask flask-cors gunicorn

COPY . /app/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV DATA_DIR=/data
# musicgen.py's own __main__ entrypoint reads MUSIC_DIR (not DATA_DIR - that's server.py's
# var) - set both to the same path so `python musicgen.py` and `import server` agree on
# where the music lives
ENV MUSIC_DIR=/data/music
# seed the real Love Story file into the runtime music dir *before* generating, so
# musicgen's "skip render if the file already exists" check picks it up instead of trying
# to synthesize it (its SONGS entry has no bpm/wave/prog/seed - render() would KeyError)
RUN mkdir -p /data/music && cp /app/music/love_story.wav /data/music/love_story.wav
RUN python musicgen.py && python -c "import server"

EXPOSE 8080
# entrypoint seeds /workspace/server from this image's baked-in /app on first run
# (only if empty - never clobbers student edits), then cd's there and execs the CMD
ENTRYPOINT ["/entrypoint.sh"]
# --preload keeps the startup scan single-shot across workers
CMD ["gunicorn", "--preload", "-w", "2", "-b", "0.0.0.0:8080", "server:app"]
