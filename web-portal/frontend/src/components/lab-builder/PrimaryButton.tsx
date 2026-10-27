import { useState, type ButtonHTMLAttributes } from 'react';
import { colors } from './theme';

export default function PrimaryButton({ style, children, ...rest }: ButtonHTMLAttributes<HTMLButtonElement>) {
  const [hover, setHover] = useState(false);
  return (
    <button
      {...rest}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        border: 0,
        background: hover ? colors.primaryHover : colors.primary,
        color: '#fff',
        borderRadius: 6,
        height: 42,
        fontFamily: 'inherit',
        fontSize: 14,
        fontWeight: 300,
        cursor: 'pointer',
        boxShadow: '0 1px 3px rgba(0,0,0,0.12)',
        ...style,
      }}
    >
      {children}
    </button>
  );
}
