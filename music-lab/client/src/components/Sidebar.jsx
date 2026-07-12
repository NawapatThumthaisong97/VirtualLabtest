export default function Sidebar({ view, onNavigate, onRescan }) {
  return (
    <nav className="sidebar">
      <div className="logo">
        Music<span>Lab</span>
      </div>
      <div className="nav-group">
        <div className="nav-label">Library</div>
        <button
          className={`nav-item ${view === "browse" ? "active" : ""}`}
          onClick={() => onNavigate("browse")}
        >
          Browse
        </button>
        <button className="nav-item">Songs</button>
        <button className="nav-item">Albums</button>
        <button className="nav-item">Artists</button>
        <button className="nav-item">Radio</button>
      </div>
      <div className="nav-group">
        <div className="nav-label">My music</div>
        <button className="nav-item">Recently Played</button>
        <button className="nav-item">Favorite Songs</button>
        <button className="nav-item" onClick={onRescan}>
          Local File
        </button>
      </div>
      <div className="nav-group">
        <div className="nav-label">Lab</div>
        <button
          className={`nav-item ${view === "sql" ? "active" : ""}`}
          onClick={() => onNavigate("sql")}
        >
          SQL Console
        </button>
      </div>
    </nav>
  );
}
