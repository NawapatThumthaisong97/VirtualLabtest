import { useState } from "react";
import { runSql } from "../api.js";

const DEFAULT_QUERY = "SELECT * FROM users;";

export default function SqlConsole() {
  const [query, setQuery] = useState(DEFAULT_QUERY);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const run = async () => {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const res = await runSql(query);
      const body = await res.json();
      if (!res.ok) {
        setError(body.error || "query failed");
      } else {
        setResult(body);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="sql-console">
      <div className="row-head">
        <h2>SQL Console</h2>
      </div>
      <p style={{ color: "var(--muted)", fontSize: 13 }}>
        SELECT-only — try <code>users</code>, <code>playlists</code>, <code>playlist_songs</code>,{" "}
        <code>listening_history</code>. Anything else (ALTER/INSERT/DROP…) is done through the
        sqlite3 CLI in the IDE — that's the exercise.
      </p>
      <textarea
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        spellCheck={false}
      />
      <div className="run-row">
        <button onClick={run} disabled={loading}>
          {loading ? "Running…" : "Run"}
        </button>
        {result && <span style={{ color: "var(--muted)", fontSize: 13 }}>{result.rows.length} rows</span>}
      </div>
      {error && <div className="sql-error">{error}</div>}
      {result && (
        <div className="sql-result-wrap">
          <table className="sql-table">
            <thead>
              <tr>
                {result.columns.map((c) => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.map((row, i) => (
                <tr key={i}>
                  {result.columns.map((c) => (
                    <td key={c}>{String(row[c])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
