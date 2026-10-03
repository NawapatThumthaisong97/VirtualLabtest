import { useForm } from 'react-hook-form'
import { Check } from 'lucide-react'
import { cn } from '../../lib/utils'
import { primary, secondary } from './styles'

const mockLabImages = [
  { id: '1', name: 'python-datascience:latest' },
  { id: '2', name: 'node-express:v18' },
  { id: '3', name: 'java-spring:v3' },
  { id: '4', name: 'react-dev:latest' },
]

const mockLabDocuments = [
  { id: '1', name: 'Lab01-DataStructures.pdf' },
  { id: '2', name: 'Lab02-Algorithms.pdf' },
  { id: '3', name: 'Lab03-Database.pdf' },
  { id: '4', name: 'Lab04-Networks.pdf' },
]

interface LabFormProps {
  onSubmit: (data: any) => void
  onCancel: () => void
}

export default function LabForm({ onSubmit, onCancel }: LabFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm({
    defaultValues: {
      title: '',
      order_no: '4',
      description: '',
      due_at: '',
      doc_url: '',
      image_id: '',
      status: 'DRAFT',
      exposed_ports: '8080, 5173, 8443',
      entrypoint_script: '/bin/bash /run.sh',
      workdir: '/workspace',
      env_vars: '',
      cpu: 'CPU 2',
      memory: 'RAM 4 GB',
      disk: 'Disk 50 GB',
      max_duration: '2 hours',
    },
  })

  return (
    <section className="mt-6 rounded-xl border border-blue-200 bg-blue-50/40 p-5">
      <div className="w-full rounded-2xl bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold text-slate-900">Create lab</h2>
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
          <div>
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
              placeholder="Lab 01 — Introduction"
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
              {...register('order_no', { required: 'Order number is required', min: 1 })}
              className={cn(
                'h-10 w-full rounded-lg border px-3 text-sm outline-none transition focus:ring-4',
                errors.order_no
                  ? 'border-red-300 bg-red-50 focus:border-red-500 focus:ring-red-100'
                  : 'border-slate-200 bg-slate-50 focus:border-blue-500 focus:bg-white focus:ring-blue-100'
              )}
            />
            {errors.order_no && (
              <p className="mt-1 text-xs text-red-600">{errors.order_no.message as string}</p>
            )}
          </div>
          
          {/* Description */}
          <label className="md:col-span-2 block">
            <span className="mb-1.5 block text-xs font-semibold text-slate-500">Description</span>
            <textarea 
              {...register('description')}
              className="min-h-24 w-full rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm outline-none focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100" 
            />
          </label>
          
          {/* Due at */}
          <div>
            <label className="mb-1.5 block text-xs font-semibold text-slate-500">Due at</label>
            <input 
              type="datetime-local"
              {...register('due_at')}
              className="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100"
            />
          </div>

          {/* Lab Document Dropdown */}
          <div>
            <label className="mb-1.5 block text-xs font-semibold text-slate-500">Lab document</label>
            <select
              {...register('doc_url')}
              className="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100"
            >
              <option value="">Select document...</option>
              {mockLabDocuments.map((doc) => (
                <option key={doc.id} value={doc.id}>
                  {doc.name}
                </option>
              ))}
            </select>
          </div>

          {/* Lab Image Dropdown */}
          <div>
            <label className="mb-1.5 block text-xs font-semibold text-slate-500">Lab image</label>
            <select
              {...register('image_id')}
              className="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100"
            >
              <option value="">Select image...</option>
              {mockLabImages.map((img) => (
                <option key={img.id} value={img.id}>
                  {img.name}
                </option>
              ))}
            </select>
          </div>
          
          {/* Status */}
          <label className="block">
            <span className="mb-1.5 block text-xs font-semibold text-slate-500">Status</span>
            <select 
              {...register('status')}
              className="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm"
            >
              <option value="DRAFT">Draft</option>
              <option value="PUBLISHED">Published</option>
            </select>
          </label>
          
          {/* Runtime Pod Specification */}
          <div className="md:col-span-2 rounded-xl border border-slate-200 p-4">
            <div>
              <p className="text-sm font-bold text-slate-800">Runtime pod specification</p>
              <p className="mt-1 text-xs text-slate-500">
                กำหนดทรัพยากรที่แต่ละ learner จะได้รับเมื่อเปิด Lab
              </p>
            </div>
            
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <label className="block">
                <span className="mb-1 block text-[11px] font-semibold text-slate-500">CPU (vCPU)</span>
                <select {...register('cpu')} className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold">
                  <option>CPU 1</option>
                  <option>CPU 2</option>
                  <option>CPU 4</option>
                  <option>CPU 8</option>
                </select>
              </label>
              
              <label className="block">
                <span className="mb-1 block text-[11px] font-semibold text-slate-500">Memory (RAM)</span>
                <select {...register('memory')} className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold">
                  <option>RAM 2 GB</option>
                  <option>RAM 4 GB</option>
                  <option>RAM 8 GB</option>
                  <option>RAM 16 GB</option>
                  <option>RAM 32 GB</option>
                </select>
              </label>
              
              <label className="block">
                <span className="mb-1 block text-[11px] font-semibold text-slate-500">Ephemeral disk</span>
                <select {...register('disk')} className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold">
                  <option>Disk 20 GB</option>
                  <option>Disk 50 GB</option>
                  <option>Disk 80 GB</option>
                  <option>Disk 100 GB</option>
                </select>
              </label>
            </div>
            
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <label className="block">
                <span className="mb-1 block text-[11px] font-semibold text-slate-500">Max session duration</span>
                <select {...register('max_duration')} className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold">
                  <option>2 hours</option>
                  <option>4 hours</option>
                  <option>8 hours</option>
                  <option>24 hours</option>
                </select>
              </label>
              <div>
                <label className="mb-1 block text-[11px] font-semibold text-slate-500">Exposed ports</label>
                <input {...register('exposed_ports')} className="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-xs outline-none focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100" />
              </div>
            </div>
            
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-[11px] font-semibold text-slate-500">Entrypoint script</label>
                <input {...register('entrypoint_script')} className="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-xs outline-none focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100" />
              </div>
              <div>
                <label className="mb-1 block text-[11px] font-semibold text-slate-500">Working directory</label>
                <input {...register('workdir')} className="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-xs outline-none focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100" />
              </div>
            </div>
            
            <label className="mt-4 block">
              <span className="mb-1 block text-[11px] font-semibold text-slate-500">Environment variables (optional)</span>
              <textarea 
                {...register('env_vars')}
                placeholder={'KEY=value\nANOTHER_KEY=value'} 
                className="min-h-20 w-full rounded-lg border border-slate-200 bg-white p-3 font-mono text-xs outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" 
              />
            </label>
          </div>
        </form>

        <div className="mt-6 flex justify-end gap-3">
          <button className={secondary} onClick={onCancel} type="button">
            Cancel
          </button>
          <button className={primary} onClick={handleSubmit(onSubmit)} type="button">
            <Check size={15} /> Create lab
          </button>
        </div>
      </div>
    </section>
  )
}
