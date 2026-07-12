"""Music Lab server - Flask + SQLite. Pure JSON API; the client (Vite/React) is a separate service."""
import json
import os
import sqlite3
import wave

from flask import Flask, abort, jsonify, request, send_file
from flask_cors import CORS

import musicgen

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("DATA_DIR", os.path.join(BASE, "data"))
MUSIC = os.path.join(DATA, "music")
DB = os.path.join(DATA, "library.db")
SEED_SQL = os.path.join(BASE, "seed.sql")

app = Flask(__name__)
CORS(app)


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def wav_duration(path):
    try:
        with wave.open(path, "rb") as w:
            return round(w.getnframes() / w.getframerate())
    except Exception:
        return 0


def scan_library():
    """Sync the music dir into SQLite (artists + songs). Safe to call repeatedly."""
    meta = {"artists": {}, "songs": {}}
    meta_path = os.path.join(MUSIC, "meta.json")
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)

    conn = db()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS artists (
             id INTEGER PRIMARY KEY,
             name TEXT UNIQUE,
             pic_url TEXT DEFAULT '')"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS songs (
             id INTEGER PRIMARY KEY,
             filename TEXT UNIQUE,
             title TEXT, artist_id INTEGER REFERENCES artists(id), duration INTEGER,
             cover_url TEXT DEFAULT '',
             plays INTEGER DEFAULT 0)"""
    )

    found = []
    for root, _, files in os.walk(MUSIC):
        for f in files:
            if f.lower().endswith((".wav", ".mp3", ".ogg", ".flac")):
                found.append(os.path.relpath(os.path.join(root, f), MUSIC))

    songs_meta = meta.get("songs", {})
    artist_names = set(meta.get("artists", {}).keys())
    for fn in found:
        artist_names.add(songs_meta.get(fn, {}).get("artist") or "Local File")

    for name in sorted(artist_names):
        pic = meta.get("artists", {}).get(name, "")
        conn.execute(
            "INSERT INTO artists (name, pic_url) VALUES (?,?) "
            "ON CONFLICT(name) DO UPDATE SET "
            # keep a manually-set pic_url when meta.json has none (empty won't clobber)
            "pic_url=CASE WHEN excluded.pic_url != '' THEN excluded.pic_url ELSE artists.pic_url END",
            (name, pic),
        )
    artist_ids = {row["name"]: row["id"] for row in conn.execute("SELECT id, name FROM artists")}

    for fn in sorted(found):
        m = songs_meta.get(fn, {})
        title = m.get("title") or os.path.splitext(os.path.basename(fn))[0].replace("-", " ").title()
        artist = m.get("artist") or "Local File"
        cover = m.get("cover", "")
        dur = wav_duration(os.path.join(MUSIC, fn)) if fn.endswith(".wav") else 0
        conn.execute(
            "INSERT INTO songs (filename, title, artist_id, duration, cover_url) VALUES (?,?,?,?,?) "
            "ON CONFLICT(filename) DO UPDATE SET title=excluded.title, artist_id=excluded.artist_id, "
            # keep a manually-set cover_url when meta.json has none (empty won't clobber)
            "cover_url=CASE WHEN excluded.cover_url != '' THEN excluded.cover_url ELSE songs.cover_url END",
            (fn, title, artist_ids[artist], dur, cover),
        )
    conn.commit()
    conn.close()


def seed_lab():
    """Run seed.sql (SQL-lab tables: users/playlists/playlist_songs/listening_history).
    Additive only - never touches songs/artists, which scan_library owns. Must run after
    scan_library() so playlist_songs/listening_history can reference real song ids."""
    conn = db()
    with open(SEED_SQL) as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


SONGS_QUERY = """
    SELECT s.id, s.filename, s.title, s.duration, s.cover_url, s.plays,
           a.id AS artist_id, a.name AS artist, a.pic_url AS artist_pic
    FROM songs s JOIN artists a ON a.id = s.artist_id
"""


@app.get("/api/songs")
def songs():
    conn = db()
    artist_id = request.args.get("artist_id")
    if artist_id:
        rows = conn.execute(SONGS_QUERY + " WHERE s.artist_id = ? ORDER BY s.id", (artist_id,))
    else:
        rows = conn.execute(SONGS_QUERY + " ORDER BY s.id")
    rows = [dict(r) for r in rows]
    conn.close()
    return jsonify(rows)


@app.get("/api/artists")
def artists():
    conn = db()
    rows = [dict(r) for r in conn.execute(
        """SELECT a.id, a.name, a.pic_url, COUNT(s.id) AS songs
           FROM artists a LEFT JOIN songs s ON s.artist_id = a.id
           GROUP BY a.id ORDER BY a.id"""
    )]
    conn.close()
    return jsonify(rows)


@app.post("/api/songs/<int:song_id>/play")
def count_play(song_id):
    conn = db()
    conn.execute("UPDATE songs SET plays = plays + 1 WHERE id = ?", (song_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.get("/stream/<int:song_id>")
def stream(song_id):
    conn = db()
    row = conn.execute("SELECT filename FROM songs WHERE id = ?", (song_id,)).fetchone()
    conn.close()
    if not row:
        abort(404)
    return send_file(os.path.join(MUSIC, row["filename"]), conditional=True)


@app.post("/api/rescan")
def rescan():
    scan_library()
    return jsonify({"ok": True})


@app.post("/api/sql")
def run_sql():
    """SQL-lab console: SELECT only. Everything else (INSERT/ALTER/DROP/...) is meant to be
    done through the sqlite3 CLI inside the IDE container - that's the lesson."""
    body = request.get_json(force=True) or {}
    query = (body.get("query") or "").strip()
    if not query.lower().startswith("select"):
        return jsonify({"error": "only SELECT queries are allowed - use the sqlite3 CLI in the IDE for anything else"}), 400
    conn = db()
    try:
        # sqlite3 already refuses multi-statement input to execute() (raises
        # sqlite3.ProgrammingError, a sqlite3.Error subclass) - blocks "SELECT..; DROP.." for free
        cur = conn.execute(query)
        cols = [d[0] for d in cur.description]
        rows = [dict(r) for r in cur.fetchmany(200)]
    except sqlite3.Error as e:
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()
    return jsonify({"columns": cols, "rows": rows})


musicgen.generate_all(MUSIC)
scan_library()
seed_lab()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
