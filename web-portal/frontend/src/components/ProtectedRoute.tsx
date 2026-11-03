import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import type { UserRole } from '../services/auth';
import type { ReactNode } from 'react';

interface ProtectedRouteProps {
  children?: ReactNode;
  allowedRoles?: UserRole[];
  /** role ไม่ผ่านแล้วพาไปหน้านี้แทนหน้า Access Restricted (เช่น อาจารย์เปิดลิงก์หน้าแลปนักศึกษา)
   *  ส่งเป็นฟังก์ชันได้ ถ้าแต่ละ role ต้องไปคนละหน้า (admin → /admin, อาจารย์ → /instructor) */
  redirectTo?: string | ((role: UserRole) => string);
}

export default function ProtectedRoute({ children, allowedRoles, redirectTo }: ProtectedRouteProps) {
  const { user, isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="flex min-h-screen w-full items-center justify-center bg-[#0a0a0a] text-white">
        <div className="flex flex-col items-center gap-4">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-white/20 border-t-white" />
          <p className="text-sm text-white/60">Verifying session…</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated || !user) {
    // Preserve intended target location for post-login redirect
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    if (redirectTo) {
      const to = typeof redirectTo === 'function' ? redirectTo(user.role) : redirectTo;
      return <Navigate to={to} replace />;
    }
    return (
      <div className="flex min-h-screen w-full items-center justify-center bg-[#0a0a0a] text-white">
        <div className="flex max-w-md flex-col items-center gap-3 text-center p-6">
          <h2 className="text-lg font-semibold text-red-400">Access Restricted</h2>
          <p className="text-sm text-white/70">
            Your account ({user.role}) does not have permission to access this page.
          </p>
          <a
            href="/"
            className="mt-2 rounded-lg bg-white/10 px-4 py-2 text-sm text-white hover:bg-white/20 transition-colors"
          >
            Return to Home
          </a>
        </div>
      </div>
    );
  }

  return children ? <>{children}</> : <Outlet />;
}

