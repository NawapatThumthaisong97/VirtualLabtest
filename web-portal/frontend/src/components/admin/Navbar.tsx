import { Link, useNavigate } from 'react-router-dom';
import { colors } from './theme';
import { useAuth } from '../../contexts/AuthContext';

const link = { color: 'rgba(255,255,255,0.75)', fontSize: 13, textDecoration: 'none' } as const;

/** Navbar หน้า admin (ตาม Design system) — admin ยังกลับไปหน้านักศึกษา / วิชา / อาจารย์ได้ */
export default function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const onLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  return (
    <div
      style={{
        background: colors.navBg,
        height: 56,
        flexShrink: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 24px',
        gap: 24,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 18, flexShrink: 0 }}>
        <Link to="/admin">
          <img src="/virtual-lab-logo-white@2x.png" alt="Virtual Lab" style={{ height: 22, width: 'auto', display: 'block' }} />
        </Link>
      </div>

      <nav style={{ display: 'flex', alignItems: 'center', gap: 22, flex: 1, justifyContent: 'center' }}>
        <Link to="/" style={link}>Home</Link>
        <Link to="/courses" style={link}>Courses</Link>
        <Link to="/instructor" style={link}>Instructor</Link>
      </nav>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
        <span style={{ color: 'rgba(255,255,255,0.6)', fontSize: 12 }}>{user?.email}</span>
        <button
          onClick={onLogout}
          title="Logout"
          style={{
            width: 36,
            height: 36,
            borderRadius: '50%',
            border: '1px solid rgba(255,255,255,0.35)',
            background: 'none',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
          }}
        >
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.85)" strokeWidth="2">
            <circle cx="12" cy="8" r="4" />
            <path d="M4 20c0-4 3.5-6 8-6s8 2 8 6" />
          </svg>
        </button>
      </div>
    </div>
  );
}
