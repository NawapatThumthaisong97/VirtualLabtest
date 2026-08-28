/**
 * Login Page
 *
 * Full-bleed dark landing: an art constellation reveals itself node by
 * node on the right while the sign-in card sits on the left.
 * Rendered outside RootLayout — no navbar, no footer.
 */
import { useCallback, useEffect, useRef } from 'react';
import type { CSSProperties } from 'react';
import styles from './Login.module.css';

import art1 from '../assets/login/ART_1.jpeg';
import art2 from '../assets/login/ART_2.jpeg';
import art3 from '../assets/login/ART_3.jpeg';
import art4 from '../assets/login/ART_4.jpeg';
import art5 from '../assets/login/ART_5.jpeg';
import art6 from '../assets/login/ART_6.jpeg';
import art7 from '../assets/login/ART_7.jpeg';
import art8 from '../assets/login/ART_8.jpeg';
import art9 from '../assets/login/ART_9.jpeg';

/* ══ REVEAL TIMELINE — art nodes ══
   ART1+ART2 0.15s · ART3 0.55s · ART4 0.80s · ART5 1.15s
   ART7 1.35s · ART6 1.55s · ART8 1.80s · ART9 2.00s          */
type ArtNode = {
  id: number;
  src: string;
  d: string;
  left: string;
  top: string;
  w: number;
  h: number;
  /** endpoints of the two segments that frame the quote */
  role?: 'src' | 'tgt';
};

const ART_NODES: ArtNode[] = [
  { id: 1, src: art1, d: '0.15s', left: '60%', top: '6%', w: 110, h: 82 },
  { id: 2, src: art2, d: '0.15s', left: '72%', top: '17%', w: 64, h: 48 },
  { id: 3, src: art3, d: '0.55s', left: '80%', top: '17%', w: 160, h: 100 },
  { id: 4, src: art4, d: '0.80s', left: '56%', top: '23%', w: 135, h: 92, role: 'src' },
  { id: 5, src: art5, d: '1.15s', left: '54%', top: '63%', w: 108, h: 72 },
  { id: 6, src: art6, d: '1.55s', left: '70%', top: '73%', w: 70, h: 70 },
  { id: 7, src: art7, d: '1.35s', left: '79%', top: '67%', w: 155, h: 92, role: 'tgt' },
  { id: 8, src: art8, d: '1.80s', left: '56%', top: '86%', w: 95, h: 78 },
  { id: 9, src: art9, d: '2.00s', left: '78%', top: '82%', w: 150, h: 90 },
];

/* ══ REVEAL TIMELINE — connector lines ══
   each starts ≈0.35s after its later endpoint appears */
const LINES = [
  { x1: 65, y1: 11, x2: 75, y2: 20, d: '0.50s' },
  { x1: 87, y1: 23, x2: 62, y2: 29, d: '1.15s' },
  { x1: 62, y1: 29, x2: 65, y2: 11, d: '1.15s' },
  { x1: 62, y1: 29, x2: 100, y2: 42, d: '1.15s' },
  { x1: 59, y1: 68, x2: 74, y2: 78, d: '1.90s' },
  { x1: 74, y1: 78, x2: 86, y2: 72, d: '1.90s' },
  { x1: 86, y1: 72, x2: 100, y2: 58, d: '1.70s' },
  { x1: 86, y1: 72, x2: 85, y2: 87, d: '2.35s' },
  { x1: 59, y1: 68, x2: 60, y2: 92, d: '2.15s' },
];

const GOOGLE_PATHS: [string, string][] = [
  [
    '#4285F4',
    'M23.49 12.27c0-.79-.07-1.54-.19-2.27H12v4.51h6.47a5.55 5.55 0 0 1-2.4 3.64v3h3.86c2.26-2.09 3.56-5.17 3.56-8.88z',
  ],
  [
    '#34A853',
    'M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.86-3c-1.08.72-2.45 1.16-4.07 1.16-3.13 0-5.78-2.11-6.73-4.96H1.29v3.09A11.99 11.99 0 0 0 12 24z',
  ],
  ['#FBBC05', 'M5.27 14.29a7.19 7.19 0 0 1 0-4.58V6.62H1.29a12.04 12.04 0 0 0 0 10.76l3.98-3.09z'],
  [
    '#EA4335',
    'M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.31 0 3.26 2.69 1.29 6.62l3.98 3.09C6.22 6.86 8.87 4.75 12 4.75z',
  ],
];

type Point = { x: number; y: number };

export default function LoginPage() {
  const pageRef = useRef<HTMLDivElement>(null);

  /* The two segments behind the quote are measured at runtime: images are
     px-sized and the quote's box depends on the webfont, so hard-coded %
     coordinates drift. Both segments stay collinear with a gap for the text. */
  const layoutQuoteLines = useCallback(() => {
    const root = pageRef.current;
    if (!root) return;
    const svg = root.querySelector(`.${styles.constellation} svg`);
    const src = root.querySelector(`.${styles.lineSrc}`);
    const tgt = root.querySelector(`.${styles.lineTgt}`);
    const quote = root.querySelector(`.${styles.quote}`);
    if (!svg || !src || !tgt || !quote) return;

    const base = root.getBoundingClientRect();
    const toPct = (px: number, total: number) => (px / total) * 100;
    const rc = (el: Element): Point => {
      const r = el.getBoundingClientRect();
      return { x: r.left - base.left + r.width / 2, y: r.top - base.top + r.height / 2 };
    };

    const A = rc(src);
    const B = rc(tgt);
    const q = quote.getBoundingClientRect();
    const M = 24; // px of breathing room around the text
    const qTop = q.top - base.top - M;
    const qBottom = q.bottom - base.top + M;

    const clamp = (t: number) => Math.max(0, Math.min(1, t));
    const tAt = (y: number) => (y - A.y) / (B.y - A.y);
    const pointAt = (t: number): Point => ({ x: A.x + t * (B.x - A.x), y: A.y + t * (B.y - A.y) });
    const gapStart = pointAt(clamp(tAt(qTop)));
    const gapEnd = pointAt(clamp(tAt(qBottom)));

    const setLine = (sel: string, p1: Point, p2: Point) => {
      const l = svg.querySelector(sel);
      if (!l) return;
      l.setAttribute('x1', String(toPct(p1.x, base.width)));
      l.setAttribute('y1', String(toPct(p1.y, base.height)));
      l.setAttribute('x2', String(toPct(p2.x, base.width)));
      l.setAttribute('y2', String(toPct(p2.y, base.height)));
    };
    // TOP draws downward (x1 at the image), BOTTOM draws upward (x1 at the far end)
    setLine(`.${styles.lQuoteTop}`, A, gapStart);
    setLine(`.${styles.lQuoteBottom}`, B, gapEnd);
  }, []);

  useEffect(() => {
    const page = pageRef.current;
    layoutQuoteLines();
    const raf = requestAnimationFrame(() => page?.classList.add(styles.play));

    window.addEventListener('resize', layoutQuoteLines);
    // the quote uses a webfont — its box changes once the serif loads
    document.fonts?.ready.then(layoutQuoteLines);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', layoutQuoteLines);
    };
  }, [layoutQuoteLines]);

  return (
    <div className={styles.page} ref={pageRef}>
      <div className={styles.wordmark}>VIRTUAL&nbsp;LAB</div>

      <div className={styles.constellation} aria-hidden="true">
        <svg viewBox="0 0 100 100" preserveAspectRatio="none">
          <g stroke="rgba(255,255,255,0.32)" strokeWidth="0.15" vectorEffect="non-scaling-stroke">
            {LINES.map((l, i) => (
              <line
                key={i}
                x1={l.x1}
                y1={l.y1}
                x2={l.x2}
                y2={l.y2}
                pathLength="1"
                style={{ '--d': l.d } as CSSProperties}
              />
            ))}
            <line
              className={styles.lQuoteTop}
              x1="61"
              y1="37"
              x2="70.6"
              y2="48.6"
              pathLength="1"
              style={{ '--d': '1.55s' } as CSSProperties}
            />
            <line
              className={styles.lQuoteBottom}
              x1="85"
              y1="66"
              x2="75.88"
              y2="54.98"
              pathLength="1"
              style={{ '--d': '1.55s' } as CSSProperties}
            />
          </g>
        </svg>

        {ART_NODES.map((n) => (
          <div
            key={n.id}
            className={[
              styles.artNode,
              n.role === 'src' ? styles.lineSrc : '',
              n.role === 'tgt' ? styles.lineTgt : '',
            ]
              .filter(Boolean)
              .join(' ')}
            style={
              { '--d': n.d, left: n.left, top: n.top, width: n.w, height: n.h } as CSSProperties
            }
          >
            <img src={n.src} alt="" />
          </div>
        ))}
      </div>

      <div className={styles.quote}>
        A Thousand Ideas
        <br />
        Happened Here
      </div>

      <main className={styles.card}>
        <h1>Sign up to our lab</h1>
        <p>Please login with your university account</p>

        <button type="button" className={`${styles.btn} ${styles.btnSso}`}>
          Sign in with SSO
          <svg viewBox="0 0 24 24" aria-hidden="true">
            {GOOGLE_PATHS.map(([fill, d]) => (
              <path key={fill} fill={fill} d={d} />
            ))}
          </svg>
        </button>

        <div className={styles.divider} />

        <p className={styles.help}>Any problem with authentication?</p>
        <button type="button" className={`${styles.btn} ${styles.btnContact}`}>
          Contact us
        </button>
      </main>
    </div>
  );
}
