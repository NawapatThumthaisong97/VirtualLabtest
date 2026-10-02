/**
 * API Service
 * Axios instance configured with base URL from .env
 */
import axios from 'axios';

// exported because some endpoints return a file, not JSON — those are handed
// to the browser as a plain URL (<img>, <iframe>, pdf.js) instead of axios
export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

// 🔧 DEV MODE: Set to false to disable auto-redirect to login on 401
const ENABLE_AUTO_REDIRECT = false;

// Create axios instance
export const apiClient = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true, // Include cookies for JWT
});

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

// Response interceptor
apiClient.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.response?.status === 401 && ENABLE_AUTO_REDIRECT) {
      // Handle unauthorized
      localStorage.removeItem('access_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default apiClient;
