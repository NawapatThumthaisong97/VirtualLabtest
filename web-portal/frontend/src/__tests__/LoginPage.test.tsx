import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import LoginPage from '../pages/Login';
import * as AuthContextModule from '../contexts/AuthContext';

describe('LoginPage & University SSO (Issue #80 Acceptance Criteria 1)', () => {
  it('renders button "Login with University Email" and triggers university SSO', () => {
    const mockLoginWithSSO = vi.fn().mockResolvedValue(undefined);

    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: null,
      isLoading: false,
      isAuthenticated: false,
      login: vi.fn(),
      loginWithSSO: mockLoginWithSSO,
      handleSsoCallback: vi.fn(),
      logout: vi.fn(),
      refreshUser: vi.fn(),
    });

    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    );

    // Acceptance Criteria 1: Verify exact button label
    const ssoButton = screen.getByRole('button', { name: /Login with University Email/i });
    expect(ssoButton).toBeDefined();

    // Clicking button initiates university SSO
    fireEvent.click(ssoButton);
    expect(mockLoginWithSSO).toHaveBeenCalledTimes(1);
  });

  it('renders credential fallback inputs for username and password', () => {
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
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    );

    expect(screen.getByPlaceholderText('student.id')).toBeDefined();
    expect(screen.getByPlaceholderText('••••••••')).toBeDefined();
    expect(screen.getByRole('button', { name: /^Sign in$/i })).toBeDefined();
  });
});
