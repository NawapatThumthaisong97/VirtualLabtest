/**
 * Toast Container Component
 * Manages and displays multiple toast notifications
 */
import type { ReactNode } from 'react'
import Toast, { type ToastProps } from './Toast'

interface ToastContainerProps {
  // onClose ใส่ให้ทุกตัวตอน render ข้อมูลใน store ไม่ต้องมี
  toasts: Omit<ToastProps, 'onClose'>[]
  onClose: (id: string) => void
  // วางไว้ล่างสุดของมุมขวาล่าง toast ซ้อนขึ้นไปข้างบน (ใช้กับ UploadTray) ไม่อยู่ใน aria-live ของ toast
  children?: ReactNode
}

export default function ToastContainer({ toasts, onClose, children }: ToastContainerProps) {
  return (
    <div className="pointer-events-none fixed right-0 bottom-0 z-50 flex max-h-screen w-full flex-col items-end gap-3 p-4 sm:p-6">
      {toasts.length > 0 && (
        <div aria-live="polite" aria-atomic="true" className="flex w-full flex-col items-end gap-3">
          {toasts.map((toast) => (
            <Toast key={toast.id} {...toast} onClose={onClose} />
          ))}
        </div>
      )}
      {children}
    </div>
  )
}
