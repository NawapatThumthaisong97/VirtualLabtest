import Face, { color, initials } from "../Face.jsx";
import { fmt } from "../utils.js";

export default function TrackList({ artists, songs, filterArtist, setFilterArtist, current, onPlay }) {
  const visible =
    filterArtist == null ? songs : songs.filter((s) => s.artist_id === filterArtist);
  const activeArtist = artists.find((a) => a.id === filterArtist);

  return (
    <>
      <section>
        <div className="row-head">
          <h2>Camp artists</h2>
        </div>
        <div className="artists">
          {artists.map((a, i) => (
            <div
              key={a.id}
              className={`artist ${a.id === filterArtist ? "active" : ""}`}
              onClick={() => setFilterArtist(filterArtist === a.id ? null : a.id)}
            >
              <Face art={a.pic_url} bg={color(i)} label={initials(a.name)} className="avatar" />
              <div>{a.name}</div>
            </div>
          ))}
        </div>
      </section>

      <section>
        <div className="row-head">
          <div className="row-head-left">
            <h2>All tracks</h2>
            {filterArtist != null && (
              <button className="clear-filter" onClick={() => setFilterArtist(null)}>
                ✕ {activeArtist?.name}
              </button>
            )}
          </div>
          <span>{visible.length} tracks</span>
        </div>
        <div className="tracks">
          {visible.map((s) => {
            const i = songs.indexOf(s);
            return (
              <div
                key={s.id}
                className={`track ${i === current ? "playing" : ""}`}
                onClick={() => onPlay(i)}
              >
                <Face
                  art={s.cover_url || s.artist_pic}
                  bg={color(i)}
                  label={initials(s.title)}
                  className="thumb"
                />
                <div className="t-title">{s.title}</div>
                <div className="t-artist">{s.artist}</div>
                <div className="t-dur">{fmt(s.duration)}</div>
                <div className="t-add">+</div>
              </div>
            );
          })}
        </div>
      </section>
    </>
  );
}
