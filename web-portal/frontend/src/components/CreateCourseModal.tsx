/**
 * Create Course Modal Component (Compact)
 * Using react-hook-form with backend schema validation
 * Dropdown with preview for background and icon
 */
import { X, Check } from 'lucide-react'
import { useForm } from 'react-hook-form'
import { cn } from '../lib/utils'
import { BACKGROUND_KEYS, ICON_KEYS, BACKGROUND_PRESETS, ICON_PRESETS } from '../constants/coursePresets'
import type { BackgroundKey, IconKey } from '../constants/coursePresets'

interface CreateCourseFormData {
  code: string
  name: string
  lecturerName: string
  backgroundKey?: BackgroundKey
  iconKey?: IconKey
}

interface CreateCourseModalProps {
  isOpen: boolean
  onClose: () => void
  onSubmit: (data: CreateCourseFormData) => void | Promise<void>
}

const button = 'inline-flex h-10 items-center justify-center gap-2 rounded-lg px-4 text-sm font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2'
const primary = `${button} bg-blue-600 text-white shadow-sm shadow-blue-600/20 hover:bg-blue-700 active:bg-blue-800 disabled:opacity-50 disabled:cursor-not-allowed`
const secondary = `${button} border border-slate-200 bg-white text-slate-700 shadow-sm hover:border-slate-300 hover:bg-slate-50 active:bg-slate-100`
const iconButton = 'inline-flex size-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500'

export default function CreateCourseModal({ isOpen, onClose, onSubmit }: CreateCourseModalProps) {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    reset,
    watch,
  } = useForm<CreateCourseFormData>({
    defaultValues: {
      code: '',
      name: '',
      lecturerName: '',
      backgroundKey: 'blue1',
      iconKey: 'layers',
    },
  })

  const selectedBackground = watch('backgroundKey')
  const selectedIcon = watch('iconKey')

  const handleClose = () => {
    reset()
    onClose()
  }

  const handleFormSubmit = async (data: CreateCourseFormData) => {
    try {
      await onSubmit(data)
      reset()
      onClose()
    } catch (error) {
      // Error already handled by parent component (Instructor.tsx)
      // Just keep the modal open for user to fix the issue
    }
  }

  if (!isOpen) return null

  return (
    <>
      {/* Backdrop */}
      <div 
        className="fixed inset-0 z-40 bg-slate-900/50 backdrop-blur-sm transition-opacity"
        onClick={handleClose}
        aria-hidden="true"
      />
      
      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 overflow-y-auto">
        <div 
          className="relative w-full max-w-sm bg-white rounded-xl shadow-lg"
          role="dialog"
          aria-modal="true"
          aria-labelledby="modal-title"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
            <h2 id="modal-title" className="text-base font-bold text-slate-900">
              New course
            </h2>
            <button
              type="button"
              onClick={handleClose}
              className={iconButton}
              aria-label="Close modal"
            >
              <X size={16} />
            </button>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit(handleFormSubmit)} className="px-4 py-3">
            <div className="grid gap-3">
              {/* Course Code */}
              <div>
                <label htmlFor="code" className="mb-1 block text-xs font-semibold text-slate-700">
                  Code <span className="text-red-500">*</span>
                </label>
                <input
                  id="code"
                  type="text"
                  {...register('code', {
                    required: 'Required',
                    maxLength: { value: 50, message: 'Max 50 chars' },
                  })}
                  className={cn(
                    'h-8 w-full rounded-lg border bg-slate-50 px-3 text-xs text-slate-700 outline-none transition focus:bg-white focus:ring-4',
                    errors.code
                      ? 'border-red-300 focus:border-red-500 focus:ring-red-100'
                      : 'border-slate-200 focus:border-blue-500 focus:ring-blue-100'
                  )}
                  placeholder="CS204"
                />
                {errors.code && (
                  <p className="mt-0.5 text-xs text-red-600">{errors.code.message}</p>
                )}
              </div>

              {/* Course Name */}
              <div>
                <label htmlFor="name" className="mb-1 block text-xs font-semibold text-slate-700">
                  Name <span className="text-red-500">*</span>
                </label>
                <input
                  id="name"
                  type="text"
                  {...register('name', {
                    required: 'Required',
                    maxLength: { value: 255, message: 'Max 255 chars' },
                  })}
                  className={cn(
                    'h-8 w-full rounded-lg border bg-slate-50 px-3 text-xs text-slate-700 outline-none transition focus:bg-white focus:ring-4',
                    errors.name
                      ? 'border-red-300 focus:border-red-500 focus:ring-red-100'
                      : 'border-slate-200 focus:border-blue-500 focus:ring-blue-100'
                  )}
                  placeholder="Data Structures..."
                />
                {errors.name && (
                  <p className="mt-0.5 text-xs text-red-600">{errors.name.message}</p>
                )}
              </div>

              {/* Lecturer Name */}
              <div>
                <label htmlFor="lecturerName" className="mb-1 block text-xs font-semibold text-slate-700">
                  Lecturer <span className="text-red-500">*</span>
                </label>
                <input
                  id="lecturerName"
                  type="text"
                  {...register('lecturerName', {
                    required: 'Required',
                    maxLength: { value: 255, message: 'Max 255 chars' },
                  })}
                  className={cn(
                    'h-8 w-full rounded-lg border bg-slate-50 px-3 text-xs text-slate-700 outline-none transition focus:bg-white focus:ring-4',
                    errors.lecturerName
                      ? 'border-red-300 focus:border-red-500 focus:ring-red-100'
                      : 'border-slate-200 focus:border-blue-500 focus:ring-blue-100'
                  )}
                  placeholder="Dr. Narin S."
                />
                {errors.lecturerName && (
                  <p className="mt-0.5 text-xs text-red-600">{errors.lecturerName.message}</p>
                )}
              </div>

              {/* Background Selection with Preview */}
              <div>
                <label htmlFor="backgroundKey" className="mb-1 block text-xs font-semibold text-slate-700">
                  Background
                </label>
                <div className="flex gap-2">
                  <select
                    id="backgroundKey"
                    {...register('backgroundKey')}
                    className="h-8 flex-1 rounded-lg border border-slate-200 bg-slate-50 px-2 text-xs text-slate-700 outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100"
                  >
                    {BACKGROUND_KEYS.map((key) => (
                      <option key={key} value={key}>
                        {key.charAt(0).toUpperCase() + key.slice(1)}
                      </option>
                    ))}
                  </select>
                  {selectedBackground && (
                    <div className="h-8 w-12 shrink-0 overflow-hidden rounded-lg border border-slate-200">
                      <img 
                        src={BACKGROUND_PRESETS[selectedBackground]} 
                        alt="Preview"
                        className="h-full w-full object-cover"
                      />
                    </div>
                  )}
                </div>
              </div>

              {/* Icon Selection with Preview */}
              <div>
                <label htmlFor="iconKey" className="mb-1 block text-xs font-semibold text-slate-700">
                  Icon
                </label>
                <div className="flex gap-2">
                  <select
                    id="iconKey"
                    {...register('iconKey')}
                    className="h-8 flex-1 rounded-lg border border-slate-200 bg-slate-50 px-2 text-xs text-slate-700 outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100"
                  >
                    {ICON_KEYS.map((key) => (
                      <option key={key} value={key}>
                        {key.charAt(0).toUpperCase() + key.slice(1)}
                      </option>
                    ))}
                  </select>
                  {selectedIcon && (
                    <div className="h-8 w-12 shrink-0 flex items-center justify-center overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
                      <img 
                        src={ICON_PRESETS[selectedIcon]} 
                        alt="Preview"
                        className="h-6 w-6 object-contain"
                      />
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Footer Actions */}
            <div className="mt-4 flex justify-end gap-2 border-t border-slate-200 pt-3">
              <button
                type="button"
                onClick={handleClose}
                className={`${secondary} h-9 px-3`}
                disabled={isSubmitting}
              >
                Cancel
              </button>
              <button
                type="submit"
                className={`${primary} h-9 px-3`}
                disabled={isSubmitting}
              >
                {isSubmitting ? (
                  <>Creating...</>
                ) : (
                  <>
                    <Check size={14} /> Create
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </>
  )
}
