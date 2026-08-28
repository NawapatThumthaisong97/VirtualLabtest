/**
 * LabLoader — loading state for Virtual Lab.
 *
 * A claw descends, grabs the container, and retracts on a loop.
 * The four squares inside pulse independently on a clockwise chase.
 * The caption underneath cycles through a list of sentences.
 *
 * Retheme from the parent by overriding --brand / --brand-bg.
 */
import { useEffect, useState } from 'react';
import type { CSSProperties } from 'react';
import styles from './LabLoader.module.css';

const DEFAULT_CAPTIONS = [
  "Hang tight — we're putting your lab together.",
  'Spinning up your containers.',
  'Wiring up the network.',
  'This usually takes under a minute.',
];

type LabLoaderProps = {
  /** px size of one inner square — everything else scales from it */
  size?: number;
  /** seconds for one full claw cycle */
  duration?: number;
  /** sentences cycled under the box; pass [] or null to hide the caption */
  captions?: string[] | null;
  /** seconds each sentence stays on screen */
  captionInterval?: number;
  /** screen-reader announcement */
  label?: string;
  /** extra class for positioning from the parent */
  className?: string;
};

export default function LabLoader({
  size = 32,
  duration = 3,
  captions = DEFAULT_CAPTIONS,
  captionInterval = 5,
  label = 'Loading',
  className = '',
}: LabLoaderProps) {
  const lines = captions ?? [];
  const lineCount = lines.length;
  const [index, setIndex] = useState(0);

  useEffect(() => {
    // a single sentence never changes, so there is nothing to schedule
    if (lineCount < 2) return;

    const id = setInterval(() => {
      setIndex((i) => (i + 1) % lineCount);
    }, captionInterval * 1000);

    return () => clearInterval(id);
  }, [lineCount, captionInterval]);

  // Custom properties are not part of CSSProperties, hence the cast.
  const vars = {
    '--u': `${size}px`,
    '--dur': `${duration}s`,
    '--caption-dur': `${captionInterval}s`,
  } as CSSProperties;

  return (
    <div
      className={`${styles.scene} ${className}`}
      style={vars}
      role="status"
      aria-live="polite"
    >
      <svg className={styles.claw} viewBox="0 0 100 102" aria-hidden="true">
        <rect x="46" y="0" width="8" height="52" fill="currentColor" />
        <rect x="31" y="50" width="38" height="13" rx="3" fill="currentColor" />
        <path className={`${styles.arm} ${styles.armLeft}`} d="M42 63 L28 85 L36 96" />
        <path className={`${styles.arm} ${styles.armRight}`} d="M58 63 L72 85 L64 96" />
      </svg>

      <div className={styles.box} aria-hidden="true">
        <i />
        <i />
        <i />
        <i />
      </div>

      {/* hidden from the live region — otherwise every swap is announced */}
      {lineCount > 0 ? (
        <p className={styles.captionSlot} aria-hidden="true">
          {/* the key remounts the span so the fade restarts on every swap */}
          <span key={index} className={styles.captionLine}>
            {lines[index % lineCount]}
          </span>
        </p>
      ) : null}

      <span className={styles.srOnly}>{label}</span>
    </div>
  );
}
