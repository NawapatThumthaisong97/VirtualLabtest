// dev: empty (relative path, goes through the Vite proxy in vite.config.js)
// prod: set VITE_API_BASE at build time to point at the real server host
export const API = import.meta.env.VITE_API_BASE || "";

export const getArtists = () => fetch(`${API}/api/artists`).then((r) => r.json());
export const getSongs = () => fetch(`${API}/api/songs`).then((r) => r.json());
export const countPlay = (id) => fetch(`${API}/api/songs/${id}/play`, { method: "POST" });
export const rescan = () => fetch(`${API}/api/rescan`, { method: "POST" });
export const runSql = (query) =>
  fetch(`${API}/api/sql`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
