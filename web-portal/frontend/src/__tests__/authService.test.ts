import { describe, it, expect, vi, beforeEach } from 'vitest';
import { authService } from '../services/auth';
import apiClient from '../services/api';

vi.mock('../services/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe('AuthService & Storage Constraints (Issue #80)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    sessionStorage.clear();
  });

  it('Constraint 1: login does NOT store tokens in localStorage or sessionStorage', async () => {
    const mockTokenData = {
      accessToken: 'jwt-access-token',
      tokenType: 'bearer',
      refreshToken: 'jwt-refresh-token',
    };

    vi.mocked(apiClient.post).mockResolvedValueOnce({
      success: true,
      message: 'Login successful',
      data: mockTokenData,
    } as unknown as never);

    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem');

    const result = await authService.login('sophia.dav', 'password123');

    expect(result).toEqual(mockTokenData);
    // Explicitly verify Constraint 1: no localStorage or sessionStorage writes
    expect(setItemSpy).not.toHaveBeenCalled();
    expect(localStorage.getItem('access_token')).toBeNull();
    expect(sessionStorage.getItem('access_token')).toBeNull();
  });

  it('getSsoLoginUrl requests university SSO authorization URL from backend', async () => {
    const mockAuthUrl = 'https://accounts.google.com/o/oauth2/v2/auth?client_id=tu-client&hd=dome.tu.ac.th';
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      success: true,
      data: { authorizationUrl: mockAuthUrl },
    } as unknown as never);

    const result = await authService.getSsoLoginUrl('random-state', 'http://localhost:5173/auth/callback');

    expect(apiClient.get).toHaveBeenCalledWith(
      '/auth/sso/login?state=random-state&redirect_uri=http%3A%2F%2Flocalhost%3A5173%2Fauth%2Fcallback'
    );
    expect(result.authorizationUrl).toBe(mockAuthUrl);
  });

  it('ssoLogin passes OAuth credentials to backend and returns token pair', async () => {
    const mockTokenData = {
      accessToken: 'sso-access-token',
      tokenType: 'bearer',
    };
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      success: true,
      data: mockTokenData,
    } as unknown as never);

    const result = await authService.ssoLogin({
      code: 'auth-code-123',
      redirectUri: 'http://localhost:5173/auth/callback',
    });

    expect(apiClient.post).toHaveBeenCalledWith('/auth/sso', {
      code: 'auth-code-123',
      redirectUri: 'http://localhost:5173/auth/callback',
    });
    expect(result).toEqual(mockTokenData);
  });

  it('logout requests backend cookie clearance without touching localStorage', async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      success: true,
      data: { loggedOut: true },
    } as unknown as never);

    const removeItemSpy = vi.spyOn(Storage.prototype, 'removeItem');

    const result = await authService.logout();

    expect(apiClient.post).toHaveBeenCalledWith('/auth/logout', {});
    expect(result.loggedOut).toBe(true);
    expect(removeItemSpy).not.toHaveBeenCalled();
  });

  it('me fetches current user profile via HTTP-Only cookie session', async () => {
    const mockUser = {
      id: 'usr-1',
      email: 'student@dome.tu.ac.th',
      name: 'Somchai TU',
      studentId: '6709616000',
      role: 'student' as const,
    };

    vi.mocked(apiClient.get).mockResolvedValueOnce({
      success: true,
      data: mockUser,
    } as unknown as never);

    const user = await authService.me();
    expect(apiClient.get).toHaveBeenCalledWith('/me');
    expect(user).toEqual(mockUser);
  });
});
