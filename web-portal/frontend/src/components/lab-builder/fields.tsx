import { useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { colors } from './theme';

export const inputBox: CSSProperties = {
  height: 42,
  border: `1px solid ${colors.inputBorder}`,
  borderRadius: 8,
  padding: '0 14px',
  fontFamily: 'inherit',
  fontSize: 13,
  color: colors.text,
  outline: 'none',
  minWidth: 0,
  background: '#fff',
};

const bare: CSSProperties = { flex: 1, minWidth: 0, border: 0, outline: 'none', fontFamily: 'inherit', fontSize: 13, color: colors.text, background: 'transparent' };

export function IconInput({ icon, value, onChange, placeholder }: { icon: ReactNode; value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 30, height: 42, border: `1px solid ${colors.inputBorder}`, borderRadius: 8, padding: '0 18px' }}>
      {icon}
      <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} style={bare} />
    </div>
  );
}

/** Textarea that shows an illustration + hint while empty. */
export function IllustratedTextarea({ value, onChange, image, imageWidth, hint, height = 246, hintSize = 13 }: { value: string; onChange: (v: string) => void; image: string; imageWidth: number; hint: string; height?: number; hintSize?: number }) {
  return (
    <div style={{ position: 'relative', height, border: `1px solid ${colors.inputBorder}`, borderRadius: 8, overflow: 'hidden' }}>
      {!value && (
        <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8, pointerEvents: 'none' }}>
          <img src={image} alt="" style={{ width: imageWidth, height: 'auto' }} />
          <span style={{ fontSize: hintSize, color: colors.text }}>{hint}</span>
        </div>
      )}
      <textarea
        aria-label={hint}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', border: 0, outline: 'none', resize: 'none', padding: '14px 16px', fontFamily: 'inherit', fontSize: 13, lineHeight: 1.5, color: colors.text, background: 'transparent' }}
      />
    </div>
  );
}

export const label: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 6 };

/** กล่องลากวาง / คลิกเลือกไฟล์ (ใช้ทั้ง .tar ของ image และ PDF ของเอกสาร) */
export function FileDrop({ file, onFile, accept, image, imageWidth, imageHeight, hint, height = 134 }: { file: File | null; onFile: (f: File | null) => void; accept: string; image: string; imageWidth: number; imageHeight?: number; hint: string; height?: number }) {
  const [dragging, setDragging] = useState(false);
  const ref = useRef<HTMLInputElement>(null);
  return (
    <>
      <div
        role="button"
        tabIndex={0}
        onClick={() => ref.current?.click()}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && ref.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const f = e.dataTransfer.files[0];
          if (f) onFile(f);
        }}
        style={{ height, border: `1px solid ${dragging ? colors.primary : colors.inputBorder}`, borderRadius: 8, background: dragging ? '#F2FAFE' : '#fff', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 4, cursor: 'pointer' }}
      >
        <img src={image} alt="" style={{ width: imageWidth, height: imageHeight ?? 'auto', objectFit: 'cover' }} />
        <span style={{ fontSize: 10 }}>{file?.name ?? hint}</span>
      </div>
      <input ref={ref} type="file" accept={accept} hidden onChange={(e) => onFile(e.target.files?.[0] ?? null)} />
    </>
  );
}

/** ข้อความ error / ความคืบหน้าใต้ฟอร์ม */
export function FormNote({ tone, children }: { tone: 'error' | 'info'; children: ReactNode }) {
  return <p style={{ margin: 0, fontSize: 11, lineHeight: 1.5, color: tone === 'error' ? '#C0392B' : colors.muted }}>{children}</p>;
}
