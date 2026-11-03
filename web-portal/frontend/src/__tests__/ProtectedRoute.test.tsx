import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import ProtectedRoute from '../components/ProtectedRoute';
import * as AuthContextModule from '../contexts/AuthContext';
import type { CurrentUser } from '../services/auth';
import { staffHomeFor } from '../utils/homePath';

describe('ProtectedRoute & Route Protection (Issue #80 Acceptance Criteria 2)', () => {
  it('redirects unauthenticated users to /login automatically', () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: null,
      isLoading: false,
      isAuthenticated: false,
      login: vi.fn(),
      loginWithSSO: vi.fn(),
      handleSsoCallback: vi.fn(),
      logout: vi.fn(),
      refreshUser: vi.fn(),
    });

    render(
      <MemoryRouter initialEntries={['/courses']}>
        <Routes>
          <Route path="/login" element={<div>Login Page Screen</div>} />
          <Route element={<ProtectedRoute />}>
            <Route path="/courses" element={<div>Protected Courses Content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

    // Should redirect to /login and not show protected content
    expect(screen.getByText('Login Page Screen')).toBeDefined();
    expect(screen.queryByText('Protected Courses Content')).toBeNull();
  });

  it('renders protected content when user is authenticated', () => {
    const mockUser: CurrentUser = {
      id: 'usr-1',
      email: 'student@dome.tu.ac.th',
      name: 'Somchai TU',
      studentId: '6709616000',
      role: 'student',
    };

    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: mockUser,
      isLoading: false,
      isAuthenticated: true,
      login: vi.fn(),
      loginWithSSO: vi.fn(),
      handleSsoCallback: vi.fn(),
      logout: vi.fn(),
      refreshUser: vi.fn(),
    });

    render(
      <MemoryRouter initialEntries={['/courses']}>
        <Routes>
          <Route path="/login" element={<div>Login Page Screen</div>} />
          <Route element={<ProtectedRoute />}>
            <Route path="/courses" element={<div>Protected Courses Content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

    // Should render protected content
    expect(screen.getByText('Protected Courses Content')).toBeDefined();
    expect(screen.queryByText('Login Page Screen')).toBeNull();
  });

  it('displays session verification loader while checking auth state', () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: null,
      isLoading: true,
      isAuthenticated: false,
      login: vi.fn(),
      loginWithSSO: vi.fn(),
      handleSsoCallback: vi.fn(),
      logout: vi.fn(),
      refreshUser: vi.fn(),
    });

    render(
      <MemoryRouter initialEntries={['/courses']}>
        <Routes>
          <Route element={<ProtectedRoute />}>
            <Route path="/courses" element={<div>Protected Courses Content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText(/Verifying session/i)).toBeDefined();
    expect(screen.queryByText('Protected Courses Content')).toBeNull();
  });

  it('redirectTo: role ไม่ผ่านแล้วพาไปหน้าที่กำหนด (อาจารย์เปิดหน้าแลปนักศึกษา)', () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: { id: 'usr-2', email: 't@tu.ac.th', name: 'Teacher', studentId: null, role: 'instructor' } as CurrentUser,
      isLoading: false,
      isAuthenticated: true,
      login: vi.fn(),
      loginWithSSO: vi.fn(),
      handleSsoCallback: vi.fn(),
      logout: vi.fn(),
      refreshUser: vi.fn(),
    });

    render(
      <MemoryRouter initialEntries={['/labs/lab-1']}>
        <Routes>
          <Route path="/instructor" element={<div>Instructor Home</div>} />
          <Route element={<ProtectedRoute allowedRoles={['student', 'admin']} redirectTo="/instructor" />}>
            <Route path="/labs/:labId" element={<div>Student Lab Page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText('Instructor Home')).toBeDefined();
    expect(screen.queryByText('Student Lab Page')).toBeNull();
    expect(screen.queryByText('Access Restricted')).toBeNull();
  });

  it('redirectTo as a function: each role goes to its own home (admin -> /admin)', () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: { id: 'usr-3', email: 'admin@tu.ac.th', name: 'Admin', studentId: null, role: 'admin' } as CurrentUser,
      isLoading: false,
      isAuthenticated: true,
      login: vi.fn(),
      loginWithSSO: vi.fn(),
      handleSsoCallback: vi.fn(),
      logout: vi.fn(),
      refreshUser: vi.fn(),
    });

    render(
      <MemoryRouter initialEntries={['/courses/c1']}>
        <Routes>
          <Route path="/admin" element={<div>Admin Home</div>} />
          <Route path="/instructor" element={<div>Instructor Home</div>} />
          <Route element={<ProtectedRoute allowedRoles={['student']} redirectTo={staffHomeFor} />}>
            <Route path="/courses/:courseId" element={<div>Student Course Page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByText('Admin Home')).toBeDefined();
    expect(screen.queryByText('Student Course Page')).toBeNull();
  });
});

