import { createContext, useContext, useEffect, useState, useCallback } from 'react';
import type { ReactNode } from 'react';
import { authService } from '../services/auth';
import type { CurrentUser } from '../services/auth';

export interface AuthContextType {
  user: CurrentUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<CurrentUser>;
  loginWithSSO: (redirectUri?: string) => Promise<void>;
  handleSsoCallback: (code: string, redirectUri?: string) => Promise<CurrentUser>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<CurrentUser | null>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  // Check auth status on mount by querying /api/me
  // Authentication status is backed entirely by HTTP-Only cookies
  const checkAuth = useCallback(async (): Promise<CurrentUser | null> => {
    try {
      const currentUser = await authService.me();
      setUser(currentUser);
      return currentUser;
    } catch {
      setUser(null);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void checkAuth();
  }, [checkAuth]);

  const login = async (username: string, password: string): Promise<CurrentUser> => {
    setIsLoading(true);
    try {
      await authService.login(username, password);
      const currentUser = await authService.me();
      setUser(currentUser);
      return currentUser;
    } finally {
      setIsLoading(false);
    }
  };

  const loginWithSSO = async (redirectUri?: string): Promise<void> => {
    const callbackUri =
      redirectUri || `${window.location.origin}/auth/callback`;
    const { authorizationUrl } = await authService.getSsoLoginUrl(undefined, callbackUri);
    window.location.href = authorizationUrl;
  };

  const handleSsoCallback = async (code: string, redirectUri?: string): Promise<CurrentUser> => {
    setIsLoading(true);
    try {
      const callbackUri =
        redirectUri || `${window.location.origin}/auth/callback`;
      await authService.ssoLogin({ code, redirectUri: callbackUri });
      const currentUser = await authService.me();
      setUser(currentUser);
      return currentUser;
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async (): Promise<void> => {
    try {
      await authService.logout();
    } catch {
      // Even if network fails, reset frontend auth state
    } finally {
      setUser(null);
    }
  };

  const refreshUser = async (): Promise<CurrentUser | null> => {
    return checkAuth();
  };

  const value: AuthContextType = {
    user,
    isLoading,
    isAuthenticated: Boolean(user),
    login,
    loginWithSSO,
    handleSsoCallback,
    logout,
    refreshUser,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

