"""Generate short synthesized songs as WAV files. Pure stdlib - no numpy."""
import json
import math
import os
import random
import struct
import wave

RATE = 22050

# note name -> semitone offset from A4
NOTES = {"C": -9, "D": -7, "E": -5, "F": -4, "G": -2, "A": 0, "B": 2}


def freq(name: str, octave: int) -> float:
    semi = NOTES[name[0]] + (1 if "#" in name else 0) + (octave - 4) * 12
    return 440.0 * (2 ** (semi / 12))


def tone(f: float, dur: float, wave_kind: str, vol: float):
    n = int(RATE * dur)
    out = []
    for i in range(n):
        t = i / RATE
        ph = 2 * math.pi * f * t
        if wave_kind == "square":
            s = 1.0 if math.sin(ph) >= 0 else -1.0
            s *= 0.5
        elif wave_kind == "saw":
            s = 2 * ((f * t) % 1.0) - 1.0
            s *= 0.6
        else:  # sine + soft harmonics
            s = math.sin(ph) + 0.35 * math.sin(2 * ph) + 0.15 * math.sin(3 * ph)
            s *= 0.65
        # simple attack/release envelope
        env = min(1.0, i / (RATE * 0.02), (n - i) / (RATE * 0.08))
        out.append(s * env * vol)
    return out


def mix(base, add, offset):
    for i, v in enumerate(add):
        j = offset + i
        if j < len(base):
            base[j] += v


# 🖼️  รูปประจำตัวศิลปิน (เช่นจาก S3) — เว้น "" ไว้จะ fallback เป็นวงกลมตัวย่อ
ARTISTS = {
    "Taylor Swift": "https://amz-picture.s3.ap-southeast-1.amazonaws.com/taylor+swift.jpeg",
    "Michael Jackson": "https://amz-picture.s3.ap-southeast-1.amazonaws.com/ab67616d00001e0232a7d87248d1b75463483df5.jpeg",
}

# 🖼️  รูปปกเพลง (ถ้าเว้นว่างจะ fallback ไปใช้รูปศิลปินแทน) ในช่อง "cover" ของแต่ละเพลง
SONGS = [
    # ไฟล์จริง (อยู่ใน server/music/ แล้ว) — render() ถูกข้ามอัตโนมัติเพราะไฟล์มีอยู่แล้ว
    {"file": "love_story.wav", "title": "Love Story", "artist": "Taylor Swift",
     "cover": "https://amz-picture.s3.ap-southeast-1.amazonaws.com/taylor+swift.jpeg"},
    # เดโมสังเคราะห์ โทน funk/bass เด่น ~117 BPM คีย์ minor (i-iv-v-VI ใน A minor)
    {"file": "billie-jean-demo.wav", "title": "Billie Jean (Demo)", "artist": "Michael Jackson",
     "cover": "https://amz-picture.s3.ap-southeast-1.amazonaws.com/ab67616d00001e0232a7d87248d1b75463483df5.jpeg",
     "bpm": 117, "wave": "square", "prog": ["A4 C5 E5", "D4 F4 A4", "E4 G4 B4", "F4 A4 C5"], "seed": 99},
]


def render(song, out_dir):
    rng = random.Random(song["seed"])
    beat = 60.0 / song["bpm"]
    bars = 8
    total = int(RATE * beat * 4 * bars) + RATE
    buf = [0.0] * total

    for bar in range(bars):
        chord = song["prog"][bar % len(song["prog"])].split()
        bar_off = int(bar * 4 * beat * RATE)
        # bass: root, one note per bar, one octave down
        root = chord[0]
        mix(buf, tone(freq(root[0], int(root[-1]) - 1), beat * 4, "sine", 0.35), bar_off)
        # arpeggio: 8 eighth-notes over the chord
        for step in range(8):
            note = chord[rng.randrange(len(chord))]
            octv = int(note[-1]) + (1 if rng.random() < 0.25 else 0)
            off = bar_off + int(step * beat / 2 * RATE)
            mix(buf, tone(freq(note[0], octv), beat / 2 * 0.9, song["wave"], 0.4), off)

    peak = max(abs(v) for v in buf) or 1.0
    frames = b"".join(
        struct.pack("<h", int(max(-1.0, min(1.0, v / peak)) * 32000)) for v in buf
    )
    with wave.open(os.path.join(out_dir, song["file"]), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(frames)


def generate_all(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    songs_meta = {}
    for s in SONGS:
        if not os.path.exists(os.path.join(out_dir, s["file"])):
            render(s, out_dir)
        songs_meta[s["file"]] = {"title": s["title"], "artist": s["artist"], "cover": s.get("cover", "")}
    meta = {"artists": ARTISTS, "songs": songs_meta}
    with open(os.path.join(out_dir, "meta.json"), "w") as f:
        json.dump(meta, f)


if __name__ == "__main__":
    generate_all(os.environ.get("MUSIC_DIR", "./data/music"))
    print("generated")
