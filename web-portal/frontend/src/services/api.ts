/**
 * API Service
 * Axios instance configured with base URL from .env
 *
 * NOTE: Per security constraint (Issue #80), tokens are NEVER stored in
 * localStorage or sessionStorage to prevent XSS attacks.
 * Authentication relies exclusively on HTTP-Only, Secure cookies via withCredentials: true.
 */
import axios from 'axios';
import type { InternalAxiosRequestConfig } from 'axios';

// Exported because some endpoints return a file, not JSON — those are handed
// to the browser as a plain URL (<img>, <iframe>, pdf.js) instead of axios
export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

// Create axios instance
export const apiClient = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true, // Send and receive HTTP-Only cookies
});

interface RetryConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}
// Request interceptor
apiClient.interceptors.request.use(
  (config) => {
    // Add token if available (optional - server supports both auth and non-auth)
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    // ไม่มี token ก็ไม่เป็นไร บาง endpoint เข้าได้โดยไม่ต้อง login
    return config;
  },
  (error) => Promise.reject(error)
);

// Track ongoing refresh promise to prevent duplicate refresh calls
let refreshPromise: Promise<unknown> | null = null;

// Response interceptor: automatically handles expired tokens via /auth/refresh
apiClient.interceptors.response.use(
  (response) => response.data,
  async (error) => {
    const originalRequest = error.config as RetryConfig;

    if (error.response?.status === 401 && originalRequest) {
      const url = originalRequest.url || '';

      // Do not attempt token refresh for auth endpoints to prevent loops
      const isAuthEndpoint =
        url.includes('/auth/login') ||
        url.includes('/auth/refresh') ||
        url.includes('/auth/sso');

      if (!isAuthEndpoint && !originalRequest._retry) {
        originalRequest._retry = true;

        try {
          if (!refreshPromise) {
            refreshPromise = axios
              .post(
                `${API_URL}/auth/refresh`,
                {},
                { withCredentials: true }
              )
              .finally(() => {
                refreshPromise = null;
              });
          }

          await refreshPromise;
          // Retry the original request with renewed cookies
          return apiClient(originalRequest);
        } catch {
          // Refresh failed: session expired, force redirect to login
          if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
            window.location.href = '/login';
          }
        }
      }
    }

    return Promise.reject(error);
  }
);

export default apiClient;
