/**
 * useToast Hook
 * Custom hook for managing toast notifications globally
 */
import { create } from 'zustand'
import type { ToastType } from '../components/Toast'

interface ToastData {
  id: string
  type: ToastType
  title: string
  message?: string
  duration?: number
}

interface ToastStore {
  toasts: ToastData[]
  addToast: (toast: Omit<ToastData, 'id'>) => void
  removeToast: (id: string) => void
  success: (title: string, message?: string, duration?: number) => void
  error: (title: string, message?: string, duration?: number) => void
  info: (title: string, message?: string, duration?: number) => void
  warning: (title: string, message?: string, duration?: number) => void
}

export const useToastStore = create<ToastStore>((set) => ({
  toasts: [],
  
  addToast: (toast) =>
    set((state) => ({
      toasts: [...state.toasts, { ...toast, id: `${Date.now()}-${Math.random()}` }],
    })),
  
  removeToast: (id) =>
    set((state) => ({
      toasts: state.toasts.filter((toast) => toast.id !== id),
    })),
  
  success: (title, message, duration = 5000) =>
    set((state) => ({
      toasts: [
        ...state.toasts,
        { id: `${Date.now()}-${Math.random()}`, type: 'success', title, message, duration },
      ],
    })),
  
  error: (title, message, duration = 5000) =>
    set((state) => ({
      toasts: [
        ...state.toasts,
        { id: `${Date.now()}-${Math.random()}`, type: 'error', title, message, duration },
      ],
    })),
  
  info: (title, message, duration = 5000) =>
    set((state) => ({
      toasts: [
        ...state.toasts,
        { id: `${Date.now()}-${Math.random()}`, type: 'info', title, message, duration },
      ],
    })),
  
  warning: (title, message, duration = 5000) =>
    set((state) => ({
      toasts: [
        ...state.toasts,
        { id: `${Date.now()}-${Math.random()}`, type: 'warning', title, message, duration },
      ],
    })),
}))

export function useToast() {
  const { success, error, info, warning } = useToastStore()
  return { success, error, info, warning }
}
