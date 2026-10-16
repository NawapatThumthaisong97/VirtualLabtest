import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import ProtectedRoute from '../components/ProtectedRoute';
import * as AuthContextModule from '../contexts/AuthContext';
import type { CurrentUser } from '../services/auth';

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
});

