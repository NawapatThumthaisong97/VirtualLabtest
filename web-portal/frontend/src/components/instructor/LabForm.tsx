import { useForm } from 'react-hook-form'
import { Check } from 'lucide-react'
import { cn } from '../../lib/utils'
import { primary, secondary } from './styles'
import type { Lab } from '../../services/lab'

interface LabFormProps {
  lab?: Lab | null
  onSubmit: (data: any) => void
  onCancel: () => void
}

export default function LabForm({ lab, onSubmit, onCancel }: LabFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm({
    defaultValues: {
      title: lab?.title || '',
      orderNo: lab?.orderNo?.toString() || '1',
      description: lab?.description || '',
      docUrl: lab?.docUrl || '',
      imageId: lab?.imageId || '',
      dueAt: lab?.dueAt ? lab.dueAt.substring(0, 16) : '', // datetime-local format
      status: lab?.status || 'draft',
    },
  })

  return (
    <section className="mt-6 rounded-xl border border-blue-200 bg-blue-50/40 p-5">
      <div className="w-full rounded-2xl bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold text-slate-900">
              {lab ? 'Edit lab' : 'Create lab'}
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              Set up the lab content, runtime image, and learner resources.
            </p>
          </div>
          <button className={secondary} onClick={onCancel} type="button">
            Cancel
          </button>
        </div>
        
        <form onSubmit={handleSubmit(onSubmit)} className="mt-6 grid gap-4 md:grid-cols-2">
          {/* Title */}
          <div className="md:col-span-2">
            <label className="mb-1.5 block text-xs font-semibold text-slate-500">
              Title <span className="text-red-500">*</span>
            </label>
            <input
              {...register('title', { required: 'Title is required' })}
              className={cn(
                'h-10 w-full rounded-lg border px-3 text-sm outline-none transition focus:ring-4',
                errors.title
                  ? 'border-red-300 bg-red-50 focus:border-red-500 focus:ring-red-100'
                  : 'border-slate-200 bg-slate-50 focus:border-blue-500 focus:bg-white focus:ring-blue-100'
              )}
              placeholder="Lab 01 — Introduction to Programming"
            />
            {errors.title && (
              <p className="mt-1 text-xs text-red-600">{errors.title.message as string}</p>
            )}
          </div>

          {/* Order Number */}
          <div>
            <label className="mb-1.5 block text-xs font-semibold text-slate-500">
              Order number <span className="text-red-500">*</span>
            </label>
            <input
              type="number"
              {...register('orderNo', { required: 'Order number is required', min: { value: 1, message: 'Must be greater than 0' } })}
              className={cn(
                'h-10 w-full rounded-lg border px-3 text-sm outline-none transition focus:ring-4',
                errors.orderNo
                  ? 'border-red-300 bg-red-50 focus:border-red-500 focus:ring-red-100'
                  : 'border-slate-200 bg-slate-50 focus:border-blue-500 focus:bg-white focus:ring-blue-100'
              )}
              placeholder="1"
            />
            {errors.orderNo && (
              <p className="mt-1 text-xs text-red-600">{errors.orderNo.message as string}</p>
            )}
          </div>

          {/* Status */}
          <div>
            <label className="mb-1.5 block text-xs font-semibold text-slate-500">Status</label>
            <select 
              {...register('status')}
              className="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
            >
              <option value="draft">Draft</option>
              <option value="published">Published</option>
            </select>
          </div>
          
          {/* Description */}
          <div className="md:col-span-2">
            <label className="mb-1.5 block text-xs font-semibold text-slate-500">Description</label>
            <textarea 
              {...register('description')}
              className="min-h-24 w-full rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm outline-none focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100"
              placeholder="Brief overview of this lab activity..."
            />
          </div>

          {/* Due Date */}
          <div>
            <label className="mb-1.5 block text-xs font-semibold text-slate-500">Due date (optional)</label>
            <input
              type="datetime-local"
              {...register('dueAt')}
              className="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100"
            />
          </div>

          {/* Image ID */}
          <div>
            <label className="mb-1.5 block text-xs font-semibold text-slate-500">Lab image ID (optional)</label>
            <input
              {...register('imageId')}
              className="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100"
              placeholder="UUID of lab image"
            />
            <p className="mt-1 text-[11px] text-slate-400">Reference to lab_images table</p>
          </div>

          {/* Document URL */}
          <div className="md:col-span-2">
            <label className="mb-1.5 block text-xs font-semibold text-slate-500">Document URL (optional)</label>
            <input
              {...register('docUrl')}
              className="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100"
              placeholder="https://example.com/lab-guide.pdf or S3 key"
            />
            <p className="mt-1 text-[11px] text-slate-400">Link to lab instructions or materials</p>
          </div>
        </form>

        <div className="mt-6 flex justify-end gap-3">
          <button className={secondary} onClick={onCancel} type="button">
            Cancel
          </button>
          <button className={primary} onClick={handleSubmit(onSubmit)} type="button">
            <Check size={15} /> {lab ? 'Save changes' : 'Create lab'}
          </button>
        </div>
      </div>
    </section>
  )
}
