import { useEffect, useRef, useState } from "react";
import Sidebar from "./components/Sidebar.jsx";
import Hero from "./components/Hero.jsx";
import TrackList from "./components/TrackList.jsx";
import NowPlaying from "./components/NowPlaying.jsx";
import SqlConsole from "./components/SqlConsole.jsx";
import { API, getArtists, getSongs, countPlay, rescan } from "./api.js";

export default function App() {
  const [artists, setArtists] = useState([]);
  const [songs, setSongs] = useState([]);
  const [current, setCurrent] = useState(-1);
  const [filterArtist, setFilterArtist] = useState(null);
  const [view, setView] = useState("browse");

  const audioRef = useRef(null);
  if (!audioRef.current) audioRef.current = new Audio();
  const audio = audioRef.current;

  const load = async () => {
    setArtists(await getArtists());
    setSongs(await getSongs());
  };

  useEffect(() => {
    load();
  }, []);

  const play = (i) => {
    const song = songs[i];
    if (!song) return;
    setCurrent(i);
    audio.src = `${API}/stream/${song.id}`;
    audio.play();
    countPlay(song.id);
  };

  useEffect(() => {
    const onEnded = () => play((current + 1) % songs.length);
    audio.addEventListener("ended", onEnded);
    return () => audio.removeEventListener("ended", onEnded);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current, songs]);

  const onPlayPause = () => {
    if (current < 0) return play(0);
    if (audio.paused) audio.play();
    else audio.pause();
  };
  const onNext = () => play((current + 1) % songs.length);
  const onPrev = () => play((current - 1 + songs.length) % songs.length);

  const onRescan = async () => {
    await rescan();
    load();
  };

  return (
    <div className="shell">
      <Sidebar view={view} onNavigate={setView} onRescan={onRescan} />

      <main className="main">
        {view === "browse" ? (
          <>
            <Hero songs={songs} />
            <TrackList
              artists={artists}
              songs={songs}
              filterArtist={filterArtist}
              setFilterArtist={setFilterArtist}
              current={current}
              onPlay={play}
            />
          </>
        ) : (
          <SqlConsole />
        )}
      </main>

      <NowPlaying
        songs={songs}
        current={current}
        audio={audio}
        onPlayPause={onPlayPause}
        onPrev={onPrev}
        onNext={onNext}
        onQueuePlay={play}
      />
    </div>
  );
}
