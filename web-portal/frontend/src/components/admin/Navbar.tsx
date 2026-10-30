import { Link, useNavigate } from 'react-router-dom';
import { colors } from './theme';
import { useAuth } from '../../contexts/AuthContext';

/** Navbar หน้า admin (ตาม Design system) — โลโก้ (กลับ /admin) + ชื่อผู้ใช้ ไม่มีลิงก์ไปหน้านักศึกษา / อาจารย์ */
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

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
        {/* แบบเดียวกับ Navigation ของนักศึกษา / อาจารย์: รูปโปรไฟล์ + ชื่อ ไม่มีกรอบ — กดแล้ว logout เหมือนเดิม */}
        <button
          onClick={onLogout}
          title="Logout"
          style={{
            border: 0,
            background: 'none',
            padding: 0,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            cursor: 'pointer',
            color: 'rgba(255,255,255,0.9)',
            fontFamily: 'inherit',
            fontSize: 13,
            fontWeight: 500,
          }}
        >
          <span
            style={{
              width: 28,
              height: 28,
              borderRadius: '50%',
              background: 'rgba(255,255,255,0.1)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.9)" strokeWidth="2">
              <circle cx="12" cy="8" r="4" />
              <path d="M4 20c0-4 3.5-6 8-6s8 2 8 6" />
            </svg>
          </span>
          <span style={{ maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {user?.name || user?.email}
          </span>
        </button>
      </div>
    </div>
  );
}
