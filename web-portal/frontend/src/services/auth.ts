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

interface TokenPayload {
  accessToken: string;
  tokenType: string;
}

const TOKEN_KEY = 'access_token';

export const authService = {
  login: async (username: string, password: string): Promise<string> => {
    const response = await apiClient.post<ApiResponse<TokenPayload>>('/auth/login', {
      username,
      password,
    });
    const { accessToken } = (response as unknown as ApiResponse<TokenPayload>).data;
    localStorage.setItem(TOKEN_KEY, accessToken);
    return accessToken;
  },

  me: async (): Promise<CurrentUser> => {
    const response = await apiClient.get<ApiResponse<CurrentUser>>('/me');
    return (response as unknown as ApiResponse<CurrentUser>).data;
  },

  logout: () => localStorage.removeItem(TOKEN_KEY),

  getToken: () => localStorage.getItem(TOKEN_KEY),
};
