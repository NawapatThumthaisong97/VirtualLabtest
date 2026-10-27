import { useForm } from 'react-hook-form'
import { Check, Container, Cpu, HardDrive, Loader2, MemoryStick, Timer } from 'lucide-react'
import { cn } from '../../lib/utils'
import { primary, secondary } from './styles'
import type { Lab, LabStatus, RunTarget } from '../../services/lab'
import { isImageReady, type LabImage } from '../../services/labImage'
import { inputClass, labelClass, selectClass } from './formStyles'
import ScanStatusBadge from './ScanStatusBadge'

export interface LabFormValues {
  title: string
  orderNo: string
  description: string
  docUrl: string
  imageId: string
  dueAt: string
  status: LabStatus
  runTarget: RunTarget
}

interface LabFormProps {
  lab?: Lab | null
  images: LabImage[]
  imagesLoading: boolean
  submitting: boolean
  onSubmit: (data: LabFormValues) => void
  onCancel: () => void
  /** ไปแท็บ Lab Image (ตอนยังไม่มี image ให้เลือก) */
  onManageImages: () => void
}

const RUN_TARGETS: { value: RunTarget; label: string; hint: string }[] = [
  { value: 'kubernetes', label: 'Lab machines (K3s)', hint: 'Runs on the lab cluster' },
  { value: 'aws', label: 'Cloud (AWS EC2)', hint: 'Image must be synced to ECR' },
  { value: 'auto', label: 'Auto', hint: 'Lab machine in class, cloud elsewhere' },
]

/** datetime ของ backend (ISO + timezone) -> ค่าที่ <input type="datetime-local"> รับ (เวลาท้องถิ่น) */
const toLocalInput = (iso: string | null | undefined): string => {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const offset = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - offset).toISOString().slice(0, 16)
}

export default function LabForm({
  lab,
  images,
  imagesLoading,
  submitting,
  onSubmit,
  onCancel,
  onManageImages,
}: LabFormProps) {
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<LabFormValues>({
    defaultValues: {
      title: lab?.title || '',
      orderNo: lab?.orderNo?.toString() || '1',
      description: lab?.description || '',
      docUrl: lab?.docUrl || '',
      imageId: lab?.imageId || '',
      dueAt: toLocalInput(lab?.dueAt),
      status: lab?.status || 'draft',
      runTarget: lab?.runTarget || 'kubernetes',
    },
  })

  const selectedId = watch('imageId')
  const selectedImage = images.find((image) => image.id === selectedId) ?? null
  const readyImages = images.filter(isImageReady)
  const pendingImages = images.filter((image) => !isImageReady(image))
  // lab เดิมผูก image ที่ไม่อยู่ในรายการ (เช่นถูกลบ / ไม่มีสิทธิ์เห็น) ยังต้องแสดงค่าเดิมได้
  const unknownCurrent = lab?.imageId && !images.some((image) => image.id === lab.imageId)

  return (
    <section className="mt-6 rounded-xl border border-blue-200 bg-blue-50/40 p-5">
      <div className="w-full rounded-2xl bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold text-slate-900">{lab ? 'Edit lab' : 'Create lab'}</h2>
            <p className="mt-1 text-sm text-slate-500">
              Set up the lab content, runtime image, and learner resources.
            </p>
          </div>
          <button className={secondary} onClick={onCancel} type="button" disabled={submitting}>
            Cancel
          </button>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="mt-6 grid gap-4 md:grid-cols-2" noValidate>
          <div className="md:col-span-2">
            <label htmlFor="lab-title" className={labelClass}>
              Title <span className="text-red-500">*</span>
            </label>
            <input
              id="lab-title"
              {...register('title', {
                required: 'Title is required',
                maxLength: { value: 255, message: 'At most 255 characters' },
              })}
              aria-invalid={!!errors.title}
              className={inputClass(!!errors.title)}
              placeholder="Lab 01 — Introduction to Programming"
            />
            {errors.title && <p className="mt-1 text-xs text-red-600">{errors.title.message}</p>}
          </div>

          <div>
            <label htmlFor="lab-order" className={labelClass}>
              Order number <span className="text-red-500">*</span>
            </label>
            <input
              id="lab-order"
              type="number"
              min={1}
              {...register('orderNo', {
                required: 'Order number is required',
                min: { value: 1, message: 'Must be greater than 0' },
              })}
              aria-invalid={!!errors.orderNo}
              className={inputClass(!!errors.orderNo)}
              placeholder="1"
            />
            {errors.orderNo && <p className="mt-1 text-xs text-red-600">{errors.orderNo.message}</p>}
          </div>

          <div>
            <label htmlFor="lab-status" className={labelClass}>Status</label>
            <select id="lab-status" {...register('status')} className={selectClass}>
              <option value="draft">Draft (hidden from students)</option>
              <option value="published">Published</option>
              <option value="archived">Archived</option>
            </select>
          </div>

          <div className="md:col-span-2">
            <label htmlFor="lab-description" className={labelClass}>Description</label>
            <textarea
              id="lab-description"
              {...register('description')}
              className="min-h-24 w-full rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100"
              placeholder="Brief overview of this lab activity..."
            />
          </div>

          {/* ---------- runtime ---------- */}
          <div className="md:col-span-2 mt-2 border-t border-slate-100 pt-4">
            <p className="text-sm font-bold text-slate-800">Runtime environment</p>
            <p className="mt-0.5 text-xs text-slate-500">
              Students get a container from this image when they press Start. Leave empty for a reading-only lab.
            </p>
          </div>

          <div className="md:col-span-2">
            <label htmlFor="lab-image" className={labelClass}>Lab image</label>
            <div className="relative">
              <select
                id="lab-image"
                {...register('imageId')}
                className={selectClass}
                disabled={imagesLoading}
                aria-describedby="lab-image-hint"
              >
                <option value="">No image (reading-only lab)</option>
                {unknownCurrent && (
                  <option value={lab!.imageId!}>Current image ({lab!.imageId!.slice(0, 8)}…)</option>
                )}
                {readyImages.length > 0 && (
                  <optgroup label="Ready to use">
                    {readyImages.map((image) => (
                      <option key={image.id} value={image.id}>
                        {image.repository}:{image.tag}
                      </option>
                    ))}
                  </optgroup>
                )}
                {pendingImages.length > 0 && (
                  <optgroup label="Not ready (scan not passed yet)">
                    {pendingImages.map((image) => (
                      <option key={image.id} value={image.id} disabled>
                        {image.repository}:{image.tag} — {image.scanStatus.replace('_', ' ')}
                      </option>
                    ))}
                  </optgroup>
                )}
              </select>
              {imagesLoading && (
                <Loader2 size={15} className="absolute right-9 top-3 animate-spin text-slate-400" aria-hidden />
              )}
            </div>
            <p id="lab-image-hint" className="mt-1 text-[11px] text-slate-400">
              Only images that passed the security scan can be attached.{' '}
              <button type="button" onClick={onManageImages} className="font-semibold text-blue-600 hover:underline">
                Upload a new image
              </button>
            </p>

            {selectedImage && (
              <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-600">
                <span className="inline-flex items-center gap-1.5 font-mono font-semibold text-slate-800">
                  <Container size={14} className="text-blue-600" aria-hidden />
                  {selectedImage.repository}:{selectedImage.tag}
                </span>
                <ScanStatusBadge image={selectedImage} />
                <span className="inline-flex items-center gap-1"><Cpu size={13} aria-hidden /> {selectedImage.cpuRequirement} CPU</span>
                <span className="inline-flex items-center gap-1"><MemoryStick size={13} aria-hidden /> {selectedImage.memoryRequirement} GB</span>
                <span className="inline-flex items-center gap-1"><HardDrive size={13} aria-hidden /> {selectedImage.diskSize} GB disk</span>
                <span className="inline-flex items-center gap-1"><Timer size={13} aria-hidden /> {selectedImage.lifespanMinutes} min</span>
                {selectedImage.exposedPorts.length > 0 && (
                  <span>Ports {selectedImage.exposedPorts.join(', ')}</span>
                )}
              </div>
            )}
          </div>

          <fieldset className="md:col-span-2">
            <legend className={labelClass}>Run on</legend>
            <div className="grid gap-2 sm:grid-cols-3">
              {RUN_TARGETS.map(({ value, label, hint }) => (
                <label
                  key={value}
                  className={cn(
                    'flex cursor-pointer flex-col rounded-lg border px-3 py-2.5 text-sm transition',
                    'has-[:checked]:border-blue-500 has-[:checked]:bg-blue-50 has-[:checked]:ring-2 has-[:checked]:ring-blue-100',
                    'border-slate-200 bg-white hover:border-slate-300',
                    'has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-blue-500',
                  )}
                >
                  <span className="flex items-center gap-2 font-semibold text-slate-800">
                    <input type="radio" value={value} {...register('runTarget')} className="accent-blue-600" />
                    {label}
                  </span>
                  <span className="mt-0.5 pl-5 text-[11px] text-slate-500">{hint}</span>
                </label>
              ))}
            </div>
          </fieldset>

          {/* ---------- resources ---------- */}
          <div className="md:col-span-2 mt-2 border-t border-slate-100 pt-4">
            <p className="text-sm font-bold text-slate-800">Schedule & materials</p>
          </div>

          <div>
            <label htmlFor="lab-due" className={labelClass}>Due date (optional)</label>
            <input id="lab-due" type="datetime-local" {...register('dueAt')} className={inputClass(false)} />
          </div>

          <div>
            <label htmlFor="lab-doc" className={labelClass}>Document URL (optional)</label>
            <input
              id="lab-doc"
              {...register('docUrl')}
              className={inputClass(false)}
              placeholder="labs/<lab-id>/doc.pdf"
            />
            <p className="mt-1 text-[11px] text-slate-400">Storage key of the lab instructions PDF</p>
          </div>
        </form>

        <div className="mt-6 flex justify-end gap-3">
          <button className={secondary} onClick={onCancel} type="button" disabled={submitting}>
            Cancel
          </button>
          <button
            className={cn(primary, 'disabled:cursor-not-allowed disabled:opacity-60')}
            onClick={handleSubmit(onSubmit)}
            type="button"
            disabled={submitting}
          >
            {submitting ? <Loader2 size={15} className="animate-spin" aria-hidden /> : <Check size={15} aria-hidden />}
            {lab ? 'Save changes' : 'Create lab'}
          </button>
        </div>
      </div>
    </section>
  )
}
