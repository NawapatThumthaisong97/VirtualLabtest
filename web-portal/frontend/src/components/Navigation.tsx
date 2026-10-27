/**
 * Navigation Component
 * Shared top navbar rendered once in Layout.tsx for every page.
 */
import { useState, useRef, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Activity, LogOut, Menu, Search, User } from 'lucide-react';
import logo from '../assets/virtual-lab-logo-white.svg';
import { useAuth } from '../contexts/AuthContext';

export default function Navigation() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleLogout = async () => {
    setDropdownOpen(false);
    await logout();
    navigate('/login', { replace: true });
  };

  return (
    <header className="flex h-14 flex-shrink-0 items-center justify-between gap-6 bg-[#0B0B0B] px-6">
      {/* Left: hamburger + logo */}
      <div className="flex flex-shrink-0 items-center gap-[18px]">
        <button
          type="button"
          aria-label="Menu"
          className="flex cursor-pointer items-center text-white"
        >
          <Menu size={20} strokeWidth={2} />
        </button>
        <Link to="/" className="flex items-center">
          <img src={logo} alt="Virtual Lab" className="block h-[22px] w-auto" />
        </Link>
      </div>

      {/* Center: search */}
      <div className="flex max-w-[420px] flex-1 items-center gap-2 rounded-lg bg-white/[0.08] px-3 py-2">
        <Search size={15} strokeWidth={2} className="text-white/50" />
        <span className="flex-1 text-[13px] text-white/50">Search labs, courses...</span>
        <span className="rounded border border-white/20 px-[5px] py-px text-[11px] text-white/35">
          ⌘K
        </span>
      </div>

      {/* Right: user account & logout */}
      <div className="relative flex items-center gap-3" ref={dropdownRef}>
        {user?.role === 'admin' && (
          <Link
            to="/admin"
            className="hidden sm:flex items-center gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-xs font-semibold text-amber-300 hover:bg-amber-500/20 transition-colors"
            title="Open Admin Dashboard"
          >
            <Activity size={14} className="text-amber-400" />
            <span>Admin Dashboard</span>
          </Link>
        )}

        {user ? (
          <>
            <button
              type="button"
              aria-label="Account"
              onClick={() => setDropdownOpen((prev) => !prev)}
              className="flex items-center gap-2 rounded-full border border-white/20 bg-white/[0.05] py-1 pl-2 pr-3 text-white/90 hover:border-white/40 transition-colors cursor-pointer"
            >
              <div className="flex h-7 w-7 items-center justify-center rounded-full bg-white/10 text-white/90">
                <User size={15} strokeWidth={2} />
              </div>
              <span className="text-[13px] font-medium max-w-[120px] truncate">
                {user.name || user.email}
              </span>
              <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-white/60">
                {user.role}
              </span>
            </button>

            {dropdownOpen && (
              <div className="absolute right-0 top-11 z-50 w-56 rounded-lg border border-white/15 bg-[#141414] py-2 text-white shadow-xl backdrop-blur-md">
                <div className="border-b border-white/10 px-4 py-2">
                  <p className="text-sm font-medium text-white truncate">{user.name}</p>
                  <p className="text-xs text-white/50 truncate">{user.email}</p>
                  {user.studentId && (
                    <p className="mt-1 text-[11px] text-white/40">ID: {user.studentId}</p>
                  )}
                </div>

                {user.role === 'admin' && (
                  <Link
                    to="/admin"
                    onClick={() => setDropdownOpen(false)}
                    className="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-amber-300 hover:bg-white/[0.06] transition-colors cursor-pointer"
                  >
                    <Activity size={15} className="text-amber-400" />
                    <span>Admin Dashboard</span>
                  </Link>
                )}

                <button
                  type="button"
                  onClick={handleLogout}
                  className="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-red-400 hover:bg-white/[0.06] transition-colors cursor-pointer"
                >
                  <LogOut size={15} />
                  <span>Sign out</span>
                </button>
              </div>
            )}
          </>
        ) : (
          <Link
            to="/login"
            className="rounded-lg bg-white/10 px-3 py-1.5 text-xs font-medium text-white hover:bg-white/20 transition-colors"
          >
            Sign in
          </Link>
        )}
      </div>
    </header>
  );
}
