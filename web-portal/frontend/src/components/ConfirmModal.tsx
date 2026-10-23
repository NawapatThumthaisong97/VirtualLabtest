/**
 * Confirmation Modal Component
 * Reusable modal for confirming dangerous actions
 */
import { X, AlertTriangle } from 'lucide-react'
import { cn } from '../lib/utils'

interface ConfirmModalProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void
  title: string
  message: string
  confirmText?: string
  cancelText?: string
  variant?: 'danger' | 'warning' | 'info'
  isLoading?: boolean
}

const button = 'inline-flex h-10 items-center justify-center gap-2 rounded-lg px-4 text-sm font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed'
const dangerButton = `${button} bg-red-600 text-white shadow-sm shadow-red-600/20 hover:bg-red-700 active:bg-red-800`
const secondaryButton = `${button} border border-slate-200 bg-white text-slate-700 shadow-sm hover:border-slate-300 hover:bg-slate-50 active:bg-slate-100`

export default function ConfirmModal({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  variant = 'danger',
  isLoading = false,
}: ConfirmModalProps) {
  if (!isOpen) return null

  const handleConfirm = () => {
    onConfirm()
  }

  return (
    <>
      {/* Backdrop */}
      <div 
        className="fixed inset-0 z-40 bg-slate-900/50 backdrop-blur-sm transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />
      
      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div 
          className="relative w-full max-w-md bg-white rounded-xl shadow-lg"
          role="dialog"
          aria-modal="true"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-start gap-3 border-b border-slate-200 px-5 py-4">
            <div className={cn(
              'flex size-10 shrink-0 items-center justify-center rounded-full',
              variant === 'danger' && 'bg-red-100 text-red-600',
              variant === 'warning' && 'bg-amber-100 text-amber-600',
              variant === 'info' && 'bg-blue-100 text-blue-600'
            )}>
              <AlertTriangle size={20} />
            </div>
            <div className="flex-1 min-w-0">
              <h2 className="text-base font-bold text-slate-900">
                {title}
              </h2>
              <p className="mt-1 text-sm text-slate-600">
                {message}
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="shrink-0 rounded-lg p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
              aria-label="Close modal"
              disabled={isLoading}
            >
              <X size={20} />
            </button>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3 px-5 py-4">
            <button
              type="button"
              onClick={onClose}
              className={secondaryButton}
              disabled={isLoading}
            >
              {cancelText}
            </button>
            <button
              type="button"
              onClick={handleConfirm}
              className={dangerButton}
              disabled={isLoading}
            >
              {isLoading ? 'Processing...' : confirmText}
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
