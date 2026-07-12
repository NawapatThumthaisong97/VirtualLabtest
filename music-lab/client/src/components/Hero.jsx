export default function Hero({ songs }) {
  const totalPlays = songs.reduce((a, s) => a + s.plays, 0);
  return (
    <>
      <header className="topbar">
        <div className="crumb">
          Camp <b>›</b> Summer 2026
        </div>
        <div className="top-actions">New releases · Shuffle play</div>
      </header>

      <section className="hero">
        <div className="hero-copy">
          <div className="eyebrow">Curated playlist</div>
          <h1>CAMP MIXTAPE</h1>
          <p>Every track on this image was synthesized (or performed) by code. Open the IDE and make it yours.</p>
          <div className="hero-meta">
            ♥ {totalPlays} plays · {songs.length} songs
          </div>
        </div>
        <div className="hero-art">
          <svg viewBox="0 0 100 100" aria-hidden="true">
            <circle cx="50" cy="50" r="34" fill="none" stroke="rgba(255,255,255,.5)" strokeWidth="1.5" />
            <circle cx="50" cy="50" r="22" fill="none" stroke="rgba(255,255,255,.35)" strokeWidth="1" />
            <circle cx="50" cy="50" r="7" fill="rgba(255,255,255,.85)" />
          </svg>
        </div>
      </section>
    </>
  );
}
