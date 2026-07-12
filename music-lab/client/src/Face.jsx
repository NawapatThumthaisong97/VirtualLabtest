// shared avatar/thumb helper — real image (cover, falling back to the artist pic) when
// present, else a coloured initials circle. Ported from static/app.js's face()/initials().

export const PALETTE = ["#c8501e", "#5b7553", "#3d5a80", "#9a4f96", "#b3872a"];
export const color = (i) => PALETTE[i % PALETTE.length];
export const initials = (name) =>
  name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();

export default function Face({ art, bg, label, className }) {
  if (art) {
    return (
      <div
        className={`${className} art`}
        style={{ backgroundImage: `url('${art}')` }}
      />
    );
  }
  return (
    <div className={className} style={{ background: bg }}>
      {label}
    </div>
  );
}
