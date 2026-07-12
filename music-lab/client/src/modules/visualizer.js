// ✏️ STUDENT MODULE — visualizer.js
// วาดกราฟิกตามเสียงเพลงแบบ real-time ด้วย Web Audio AnalyserNode + canvas
//
// โจทย์ตัวอย่าง:
//   1. เปลี่ยนสีแท่งให้ไล่ hue ตามความถี่
//   2. เปลี่ยนจากแท่งเป็นวงกลม (วาด arc รัศมีตาม amplitude)
//   3. [ยาก] เขียนโหมด waveform ด้วย analyser.getByteTimeDomainData

export function startVisualizer(canvas, analyser) {
  const ctx = canvas.getContext("2d");
  const data = new Uint8Array(analyser.frequencyBinCount);

  function frame() {
    requestAnimationFrame(frame);
    analyser.getByteFrequencyData(data);

    ctx.fillStyle = "#2b2622";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    const bars = 32;
    const w = canvas.width / bars;
    for (let i = 0; i < bars; i++) {
      const v = data[i] / 255;                    // 0..1
      const h = v * canvas.height * 0.85;
      ctx.fillStyle = `rgba(200, 80, 30, ${0.35 + v * 0.65})`;
      ctx.fillRect(i * w + 2, canvas.height - h, w - 4, h);
    }
  }
  frame();
}
