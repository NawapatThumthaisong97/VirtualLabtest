-- SQL lab space — server.py runs this file itself every start (via seed_lab(), always
-- AFTER scan_library()). Additive only: never touch songs/artists — those belong to
-- scan_library. Safe to run repeatedly (CREATE TABLE IF NOT EXISTS + guarded inserts).

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  name TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS playlists (
  id INTEGER PRIMARY KEY,
  user_id INTEGER REFERENCES users(id),
  title TEXT,
  UNIQUE(user_id, title)
);

CREATE TABLE IF NOT EXISTS playlist_songs (
  playlist_id INTEGER REFERENCES playlists(id),
  song_id INTEGER REFERENCES songs(id),
  position INTEGER,
  PRIMARY KEY (playlist_id, song_id)
);

CREATE TABLE IF NOT EXISTS listening_history (
  id INTEGER PRIMARY KEY,
  user_id INTEGER REFERENCES users(id),
  song_id INTEGER REFERENCES songs(id),
  played_at TEXT DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO users (name) VALUES ('nan'), ('ploy'), ('gun'), ('mind');

INSERT OR IGNORE INTO playlists (user_id, title)
  SELECT id, 'Road Trip'   FROM users WHERE name = 'nan'
  UNION ALL
  SELECT id, 'Study Beats' FROM users WHERE name = 'ploy';

INSERT OR IGNORE INTO playlist_songs (playlist_id, song_id, position)
  SELECT p.id, s.id, 1 FROM playlists p, songs s WHERE p.title='Road Trip'   AND s.filename='love_story.wav'
  UNION ALL
  SELECT p.id, s.id, 2 FROM playlists p, songs s WHERE p.title='Road Trip'   AND s.filename='billie-jean-demo.wav'
  UNION ALL
  SELECT p.id, s.id, 1 FROM playlists p, songs s WHERE p.title='Study Beats' AND s.filename='billie-jean-demo.wav';

-- listening_history has no natural unique key (repeat plays are valid) — guard idempotency
-- with "only seed while the table is still empty" instead of INSERT OR IGNORE
INSERT INTO listening_history (user_id, song_id, played_at)
WITH RECURSIVE seq(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM seq WHERE n < 20)
SELECT
  (SELECT id FROM users ORDER BY RANDOM() LIMIT 1),
  (SELECT id FROM songs ORDER BY RANDOM() LIMIT 1),
  datetime('now', printf('-%d minutes', (ABS(RANDOM()) % 10000)))
FROM seq
WHERE NOT EXISTS (SELECT 1 FROM listening_history);
