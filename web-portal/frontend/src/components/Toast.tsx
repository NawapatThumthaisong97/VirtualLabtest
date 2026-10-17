/**
 * Toast Notification Component
 * Beautiful toast notifications for success, error, info, and warning messages
 */
import { useEffect } from 'react'
import { CheckCircle, XCircle, Info, AlertTriangle, X } from 'lucide-react'
import { cn } from '../lib/utils'

export type ToastType = 'success' | 'error' | 'info' | 'warning'

export interface ToastProps {
  id: string
  type: ToastType
  title: string
  message?: string
  duration?: number
  onClose: (id: string) => void
}

const toastStyles = {
  success: {
    container: 'border-emerald-200 bg-emerald-50',
    icon: 'text-emerald-600',
    title: 'text-emerald-900',
    message: 'text-emerald-700',
    IconComponent: CheckCircle,
  },
  error: {
    container: 'border-red-200 bg-red-50',
    icon: 'text-red-600',
    title: 'text-red-900',
    message: 'text-red-700',
    IconComponent: XCircle,
  },
  info: {
    container: 'border-blue-200 bg-blue-50',
    icon: 'text-blue-600',
    title: 'text-blue-900',
    message: 'text-blue-700',
    IconComponent: Info,
  },
  warning: {
    container: 'border-amber-200 bg-amber-50',
    icon: 'text-amber-600',
    title: 'text-amber-900',
    message: 'text-amber-700',
    IconComponent: AlertTriangle,
  },
}

export default function Toast({ id, type, title, message, duration = 5000, onClose }: ToastProps) {
  const styles = toastStyles[type]
  const Icon = styles.IconComponent

  useEffect(() => {
    if (duration > 0) {
      const timer = setTimeout(() => {
        onClose(id)
      }, duration)
      return () => clearTimeout(timer)
    }
  }, [id, duration, onClose])

  return (
    <div
      role="alert"
      className={cn(
        'pointer-events-auto w-full max-w-sm overflow-hidden rounded-xl border shadow-lg transition-all',
        'animate-in slide-in-from-bottom-5 fade-in duration-300',
        styles.container
      )}
    >
      <div className="p-4">
        <div className="flex items-start gap-3">
          <Icon className={cn('mt-0.5 shrink-0', styles.icon)} size={20} />
          
          <div className="flex-1 min-w-0">
            <p className={cn('text-sm font-semibold', styles.title)}>
              {title}
            </p>
            {message && (
              <p className={cn('mt-1 text-xs leading-relaxed', styles.message)}>
                {message}
              </p>
            )}
          </div>

          <button
            onClick={() => onClose(id)}
            className={cn(
              'shrink-0 rounded-lg p-1 transition hover:bg-white/50',
              styles.icon
            )}
            aria-label="Close notification"
          >
            <X size={16} />
          </button>
        </div>
      </div>
    </div>
  )
}
