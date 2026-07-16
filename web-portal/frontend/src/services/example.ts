/**
 * Example API Service
 * All API calls related to examples
 */
import apiClient from './api';

export interface Example {
  id: number;
  title: string;
  description?: string;
  is_active: boolean;
  created_at: string;
  updated_at?: string;
}

export interface ApiResponse<T> {
  success: boolean;
  message: string;
  data: T;
  error?: string;
}

export const exampleService = {
  // Get all examples
  getAll: async (): Promise<Example[]> => {
    const response = await apiClient.get<ApiResponse<Example[]>>('/example');
    return (response as any).data || [];
  },

  // Get example by ID
  getById: async (id: number): Promise<Example | null> => {
    const response = await apiClient.get<ApiResponse<Example>>(`/example/${id}`);
    return (response as any).data || null;
  },

  // Create example
  create: async (data: Omit<Example, 'id' | 'created_at' | 'updated_at'>) => {
    const response = await apiClient.post<ApiResponse<Example>>('/example', data);
    return (response as any).data;
  },

  // Update example
  update: async (id: number, data: Partial<Example>) => {
    const response = await apiClient.put<ApiResponse<Example>>(`/example/${id}`, data);
    return (response as any).data;
  },

  // Delete example
  delete: async (id: number) => {
    const response = await apiClient.delete<ApiResponse<void>>(`/example/${id}`);
    return (response as any).data;
  },
};
