import apiClient from './api';
import type { ApiResponse } from './lab';

export type UserRole = 'student' | 'instructor' | 'admin';

export interface CurrentUser {
  id: string;
  email: string;
  name: string;
  studentId: string | null;
  role: UserRole;
}

export interface TokenResponseData {
  accessToken: string;
  tokenType: string;
  refreshToken?: string | null;
}

export interface SSOAuthorizeData {
  authorizationUrl: string;
}

export interface SSOLoginPayload {
  code?: string;
  idToken?: string;
  accessToken?: string;
  redirectUri?: string;
  email?: string;
  name?: string;
  studentId?: string;
}

export interface LogoutResponseData {
  loggedOut: boolean;
}

/**
 * Auth Service
 * Interacts with backend authentication endpoints.
 * Note: Tokens are stored strictly in HTTP-Only, Secure cookies managed by the browser.
 * Never store tokens in localStorage or sessionStorage.
 */
export const authService = {
  login: async (username: string, password: string): Promise<TokenResponseData> => {
    const response = await apiClient.post<ApiResponse<TokenResponseData>>('/auth/login', {
      username,
      password,
    });
    return (response as unknown as ApiResponse<TokenResponseData>).data;
  },

  getSsoLoginUrl: async (state?: string, redirectUri?: string): Promise<SSOAuthorizeData> => {
    const params = new URLSearchParams();
    if (state) params.set('state', state);
    if (redirectUri) params.set('redirect_uri', redirectUri);

    const qs = params.toString() ? `?${params.toString()}` : '';
    const response = await apiClient.get<ApiResponse<SSOAuthorizeData>>(`/auth/sso/login${qs}`);
    return (response as unknown as ApiResponse<SSOAuthorizeData>).data;
  },

  ssoLogin: async (payload: SSOLoginPayload): Promise<TokenResponseData> => {
    const response = await apiClient.post<ApiResponse<TokenResponseData>>('/auth/sso', payload);
    return (response as unknown as ApiResponse<TokenResponseData>).data;
  },

  refresh: async (): Promise<TokenResponseData> => {
    const response = await apiClient.post<ApiResponse<TokenResponseData>>('/auth/refresh', {});
    return (response as unknown as ApiResponse<TokenResponseData>).data;
  },

  logout: async (): Promise<LogoutResponseData> => {
    const response = await apiClient.post<ApiResponse<LogoutResponseData>>('/auth/logout', {});
    return (response as unknown as ApiResponse<LogoutResponseData>).data;
  },

  me: async (): Promise<CurrentUser> => {
    const response = await apiClient.get<ApiResponse<CurrentUser>>('/me');
    return (response as unknown as ApiResponse<CurrentUser>).data;
  },
};

export default authService;
