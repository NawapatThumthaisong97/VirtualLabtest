import { useEffect, useRef, useState } from "react";
import Face, { color } from "../Face.jsx";
import { fmt } from "../utils.js";

export default function NowPlaying({ songs, current, audio, onPlayPause, onPrev, onNext, onQueuePlay }) {
  const song = current >= 0 ? songs[current] : null;
  const eqRef = useRef(null);
  const trackRef = useRef(null);
  const stopPendingRef = useRef(false);
  const [isPlaying, setIsPlaying] = useState(!audio.paused);
  const [seek, setSeek] = useState(0);

  const restartMarquee = () => {
    const track = trackRef.current;
    if (!track) return;
    track.classList.remove("scrolling");
    stopPendingRef.current = false;
    requestAnimationFrame(() => {
      if (!audio.paused) track.classList.add("scrolling");
    });
  };

  // restart the marquee fresh every time the track changes
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(restartMarquee, [song?.id]);

  // eq bars + marquee stop/resume, wired straight to the shared <audio> element's native
  // play/pause events (kept imperative on purpose - see static/app.js's original comment:
  // pausing must NOT cut the marquee off mid-loop, it should finish the loop it's on first)
  useEffect(() => {
    const track = trackRef.current;
    const eq = eqRef.current;
    if (!track || !eq) return;

    const onIteration = () => {
      if (stopPendingRef.current) {
        track.classList.remove("scrolling");
        stopPendingRef.current = false;
      }
    };
    const onPlay = () => {
      setIsPlaying(true);
      eq.classList.add("playing");
      stopPendingRef.current = false;
      if (!track.classList.contains("scrolling")) restartMarquee();
    };
    const onPause = () => {
      setIsPlaying(false);
      eq.classList.remove("playing");
      stopPendingRef.current = true; // let it finish the loop it's on before stopping
    };
    const onTimeUpdate = () => {
      if (audio.duration) setSeek((audio.currentTime / audio.duration) * 100);
    };

    track.addEventListener("animationiteration", onIteration);
    audio.addEventListener("play", onPlay);
    audio.addEventListener("pause", onPause);
    audio.addEventListener("timeupdate", onTimeUpdate);
    return () => {
      track.removeEventListener("animationiteration", onIteration);
      audio.removeEventListener("play", onPlay);
      audio.removeEventListener("pause", onPause);
      audio.removeEventListener("timeupdate", onTimeUpdate);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [audio]);

  const cover = song ? song.cover_url || song.artist_pic : "";
  const fallbackColor = song ? color(current) : undefined; // no song yet -> let CSS's default show

  return (
    <aside className="nowplaying">
      <div className="np-label">
        <span className="eq" ref={eqRef}>
          <i></i>
          <i></i>
          <i></i>
          <i></i>
        </span>
        Now playing
      </div>

      <div className="np-art">
        <div
          className="np-cover"
          style={{
            backgroundImage: cover ? `url('${cover}')` : "none",
            backgroundColor: cover ? "" : fallbackColor,
          }}
        />
      </div>

      <div className="np-title-wrap">
        <div className="np-title-track" ref={trackRef}>
          <span className="np-title">{song ? song.title : "Pick a track"}</span>
          <span className="np-title" aria-hidden="true">
            {song ? song.title : ""}
          </span>
        </div>
      </div>
      <div className="np-artist">{song ? song.artist : "Music Lab"}</div>

      <div className="np-controls">
        <button title="Previous" onClick={onPrev}>
          ⏮
        </button>
        <button id="btn-play" title="Play/Pause" onClick={onPlayPause}>
          {isPlaying ? "⏸" : "▶"}
        </button>
        <button title="Next" onClick={onNext}>
          ⏭
        </button>
      </div>

      <input
        type="range"
        min="0"
        max="100"
        value={seek}
        onChange={(e) => {
          const v = Number(e.target.value);
          setSeek(v);
          if (audio.duration) audio.currentTime = (v / 100) * audio.duration;
        }}
      />

      <div className="queue">
        {songs.map((s, i) => (
          <div
            key={s.id}
            className={`q-item ${i === current ? "playing" : ""}`}
            onClick={() => onQueuePlay(i)}
          >
            <Face art={s.cover_url || s.artist_pic} bg={color(i)} label="" className="thumb" />
            <div>
              <div>{s.title}</div>
              <div className="q-artist">{s.artist}</div>
            </div>
            <div className="q-dur">{fmt(s.duration)}</div>
          </div>
        ))}
      </div>
    </aside>
  );
}
