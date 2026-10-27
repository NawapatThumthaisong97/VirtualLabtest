import { useRef, useState } from 'react'
import { useFieldArray, useForm } from 'react-hook-form'
import { FileArchive, Loader2, Plus, UploadCloud, X } from 'lucide-react'
import { cn } from '../../lib/utils'
import { iconButton, primary, secondary } from './styles'
import { errorText, hintText, inputClass, labelClass } from './formStyles'
import {
  MAX_ARCHIVE_BYTES,
  REPOSITORY_PREFIX,
  RESERVED_REPOSITORIES,
  type CreateLabImagePayload,
} from '../../services/labImage'

export interface LabImageFormValues {
  name: string
  tag: string
  description: string
  cpuRequirement: string
  memoryRequirement: string
  diskSize: string
  lifespanMinutes: string
  exposedPorts: string
  entrypointScript: string
  workdir: string
  envVars: { key: string; value: string }[]
}

/** ความคืบหน้าที่ LabImageTab ส่งกลับมาแสดง */
export type UploadPhase =
  | { kind: 'idle' }
  | { kind: 'requesting' }
  | { kind: 'uploading'; percent: number }

interface LabImageFormProps {
  courseId: string
  phase: UploadPhase
  onSubmit: (payload: CreateLabImagePayload, file: File) => void
  onCancel: () => void
}

// กติกาเดียวกับ backend (lab_image_schema.RepositoryName / ImageTag)
const NAME_PATTERN = /^[a-z0-9]+(?:(?:\.|_|__|-+)[a-z0-9]+)*(?:\/[a-z0-9]+(?:(?:\.|_|__|-+)[a-z0-9]+)*)*$/
const TAG_PATTERN = /^[A-Za-z0-9_][A-Za-z0-9._-]*$/
const ENV_KEY_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/
const RESOURCE_PATTERN = /^\d+(\.\d+)?\+?$/

const formatBytes = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB']
  let value = bytes / 1024
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unit]}`
}

/** "8080, 5173 8443" -> [8080, 5173, 8443] หรือข้อความ error */
const parsePorts = (raw: string): number[] | string => {
  const parts = raw.split(/[\s,]+/).filter(Boolean)
  const ports: number[] = []
  for (const part of parts) {
    if (!/^\d+$/.test(part)) return `"${part}" is not a port number`
    const port = Number(part)
    if (port < 1 || port > 65535) return `${port} is out of range (1-65535)`
    if (ports.includes(port)) return `${port} is listed twice`
    ports.push(port)
  }
  return ports
}

export default function LabImageForm({ courseId, phase, onSubmit, onCancel }: LabImageFormProps) {
  const [file, setFile] = useState<File | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const busy = phase.kind !== 'idle'

  const {
    register,
    control,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<LabImageFormValues>({
    defaultValues: {
      name: '',
      tag: 'latest',
      description: '',
      cpuRequirement: '2+',
      memoryRequirement: '4+',
      diskSize: '50',
      lifespanMinutes: '60',
      exposedPorts: '8080, 5173, 8443',
      entrypointScript: '/bin/bash /run.sh',
      workdir: '/workspace',
      envVars: [{ key: 'IDE_PASSWORD', value: '' }],
    },
  })
  const env = useFieldArray({ control, name: 'envVars' })
  const name = watch('name')
  const tag = watch('tag')

  const pickFile = (picked: File | undefined | null) => {
    if (!picked) return
    if (!picked.name.toLowerCase().endsWith('.tar')) {
      setFile(null)
      setFileError('Choose an uncompressed .tar file (from docker save)')
      return
    }
    if (picked.size === 0) {
      setFile(null)
      setFileError('The file is empty')
      return
    }
    if (picked.size > MAX_ARCHIVE_BYTES) {
      setFile(null)
      setFileError(`File is ${formatBytes(picked.size)}, the limit is ${formatBytes(MAX_ARCHIVE_BYTES)}`)
      return
    }
    setFile(picked)
    setFileError(null)
  }

  const submit = (values: LabImageFormValues) => {
    if (!file) {
      setFileError('Attach the image .tar file')
      return
    }
    const ports = parsePorts(values.exposedPorts)
    if (typeof ports === 'string') return // validate ของ field จัดการข้อความแล้ว

    const envVars = Object.fromEntries(
      values.envVars
        .filter((row) => row.key.trim())
        .map((row) => [row.key.trim(), row.value]),
    )

    onSubmit(
      {
        courseId,
        repository: `${REPOSITORY_PREFIX}${values.name.trim()}`,
        tag: values.tag.trim(),
        fileSizeBytes: file.size,
        description: values.description.trim() || null,
        cpuRequirement: values.cpuRequirement.trim(),
        memoryRequirement: values.memoryRequirement.trim(),
        diskSize: Number(values.diskSize),
        lifespanMinutes: Number(values.lifespanMinutes),
        exposedPorts: ports,
        entrypointScript: values.entrypointScript.trim(),
        workdir: values.workdir.trim() || null,
        envVars: Object.keys(envVars).length ? envVars : null,
      },
      file,
    )
  }

  // กันไม่ให้ submit ด้วยปุ่มก่อนเช็คไฟล์ (react-hook-form ไม่รู้จัก state ของไฟล์)
  const onValid = handleSubmit(submit, () => {
    if (!file) setFileError('Attach the image .tar file')
  })

  return (
    <section className="mt-6 rounded-xl border border-blue-200 bg-blue-50/40 p-5">
      <div className="w-full rounded-2xl bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold text-slate-900">Upload lab image</h2>
            <p className="mt-1 text-sm text-slate-500">
              Export your image with <code className="rounded bg-slate-100 px-1 font-mono text-xs">docker save -o image.tar &lt;image&gt;</code>.
              It is scanned for vulnerabilities and secrets before students can use it.
            </p>
          </div>
          <button className={secondary} onClick={onCancel} type="button" disabled={busy}>
            Cancel
          </button>
        </div>

        <form onSubmit={onValid} className="mt-6 grid gap-4 md:grid-cols-2" noValidate>
          {/* ---------- identity ---------- */}
          <div>
            <label htmlFor="img-name" className={labelClass}>
              Repository <span className="text-red-500">*</span>
            </label>
            <div
              className={cn(
                'flex h-10 overflow-hidden rounded-lg border transition focus-within:ring-4',
                errors.name
                  ? 'border-red-300 bg-red-50 focus-within:border-red-500 focus-within:ring-red-100'
                  : 'border-slate-200 bg-slate-50 focus-within:border-blue-500 focus-within:bg-white focus-within:ring-blue-100',
              )}
            >
              <span className="flex select-none items-center border-r border-slate-200 bg-slate-100 px-3 font-mono text-sm text-slate-500">
                {REPOSITORY_PREFIX}
              </span>
              <input
                id="img-name"
                {...register('name', {
                  required: 'Repository name is required',
                  setValueAs: (v: string) => v.trim().toLowerCase(),
                  validate: (v) => {
                    if (v.startsWith(REPOSITORY_PREFIX)) return `Don't type the "${REPOSITORY_PREFIX}" prefix`
                    if (!NAME_PATTERN.test(v)) return 'Lowercase letters, digits, and . _ - / only'
                    if ((REPOSITORY_PREFIX + v).length > 255) return 'Too long'
                    if (RESERVED_REPOSITORIES.includes(REPOSITORY_PREFIX + v)) return 'This name is reserved'
                    return true
                  },
                })}
                aria-invalid={!!errors.name}
                className="w-full bg-transparent px-3 font-mono text-sm outline-none"
                placeholder="print-test2077"
                autoComplete="off"
                disabled={busy}
              />
            </div>
            {errors.name && <p className={errorText}>{errors.name.message}</p>}
          </div>

          <div>
            <label htmlFor="img-tag" className={labelClass}>
              Tag <span className="text-red-500">*</span>
            </label>
            <input
              id="img-tag"
              {...register('tag', {
                required: 'Tag is required',
                maxLength: { value: 100, message: 'At most 100 characters' },
                pattern: { value: TAG_PATTERN, message: 'Letters, digits, . _ - (cannot start with . or -)' },
              })}
              aria-invalid={!!errors.tag}
              className={cn(inputClass(!!errors.tag), 'font-mono')}
              placeholder="latest"
              autoComplete="off"
              disabled={busy}
            />
            {errors.tag && <p className={errorText}>{errors.tag.message}</p>}
          </div>

          <p className="-mt-2 font-mono text-[11px] text-slate-400 md:col-span-2">
            Image reference: <span className="text-slate-600">{REPOSITORY_PREFIX}{name || '<name>'}:{tag || '<tag>'}</span>
          </p>

          {/* ---------- file ---------- */}
          <div className="md:col-span-2">
            <span className={labelClass}>
              Image archive (.tar) <span className="text-red-500">*</span>
            </span>
            <div
              role="button"
              tabIndex={busy ? -1 : 0}
              aria-disabled={busy}
              aria-describedby="img-file-hint"
              onClick={() => !busy && fileInput.current?.click()}
              onKeyDown={(e) => {
                if (!busy && (e.key === 'Enter' || e.key === ' ')) {
                  e.preventDefault()
                  fileInput.current?.click()
                }
              }}
              onDragOver={(e) => {
                e.preventDefault()
                if (!busy) setDragging(true)
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDragging(false)
                if (!busy) pickFile(e.dataTransfer.files?.[0])
              }}
              className={cn(
                'flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 py-7 text-center transition focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-blue-100',
                dragging ? 'border-blue-500 bg-blue-50' : fileError ? 'border-red-300 bg-red-50' : 'border-slate-300 bg-slate-50 hover:border-blue-400 hover:bg-blue-50/40',
                busy && 'cursor-not-allowed opacity-60',
              )}
            >
              {file ? (
                <div className="flex items-center gap-3 text-left">
                  <FileArchive size={28} className="text-blue-600" aria-hidden />
                  <div>
                    <p className="text-sm font-semibold text-slate-800">{file.name}</p>
                    <p className="text-xs text-slate-500">{formatBytes(file.size)} · click to choose another file</p>
                  </div>
                </div>
              ) : (
                <>
                  <UploadCloud size={28} className="text-slate-400" aria-hidden />
                  <p className="mt-2 text-sm font-semibold text-slate-700">Drop your .tar here or click to browse</p>
                  <p className="mt-0.5 text-xs text-slate-400">Up to {formatBytes(MAX_ARCHIVE_BYTES)}, linux/amd64, one image per file</p>
                </>
              )}
            </div>
            <input
              ref={fileInput}
              type="file"
              accept=".tar,application/x-tar"
              className="sr-only"
              tabIndex={-1}
              aria-label="Image archive file"
              onChange={(e) => {
                pickFile(e.target.files?.[0])
                e.target.value = '' // เลือกไฟล์เดิมซ้ำได้
              }}
            />
            {fileError ? (
              <p className={errorText} role="alert">{fileError}</p>
            ) : (
              <p id="img-file-hint" className={hintText}>The file goes straight to storage; it is not sent through the web server.</p>
            )}
          </div>

          <div className="md:col-span-2">
            <label htmlFor="img-description" className={labelClass}>Description</label>
            <textarea
              id="img-description"
              {...register('description', { maxLength: { value: 2000, message: 'At most 2000 characters' } })}
              className="min-h-20 w-full rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100"
              placeholder="All-in-one lab: Flask API, Vite client, code-server"
              disabled={busy}
            />
            {errors.description && <p className={errorText}>{errors.description.message}</p>}
          </div>

          {/* ---------- resources ---------- */}
          <div className="md:col-span-2 mt-2 border-t border-slate-100 pt-4">
            <p className="text-sm font-bold text-slate-800">Resources per student</p>
            <p className="mt-0.5 text-xs text-slate-500">Use a trailing + for "at least", e.g. 2+ CPUs.</p>
          </div>

          <div className="grid gap-4 sm:grid-cols-4 md:col-span-2">
            {([
              ['cpuRequirement', 'CPU', '2+', 'text'],
              ['memoryRequirement', 'Memory (GB)', '4+', 'text'],
              ['diskSize', 'Disk (GB)', '50', 'number'],
              ['lifespanMinutes', 'Lifespan (min)', '60', 'number'],
            ] as const).map(([field, label, placeholder, type]) => (
              <div key={field}>
                <label htmlFor={`img-${field}`} className={labelClass}>
                  {label} <span className="text-red-500">*</span>
                </label>
                <input
                  id={`img-${field}`}
                  type={type}
                  min={type === 'number' ? 1 : undefined}
                  {...register(field, {
                    required: 'Required',
                    validate: (v) =>
                      type === 'number'
                        ? (Number.isInteger(Number(v)) && Number(v) > 0) || 'Whole number > 0'
                        : (RESOURCE_PATTERN.test(v.trim()) && v.trim().length <= 20) || 'e.g. 2, 2+, 0.5',
                  })}
                  aria-invalid={!!errors[field]}
                  className={inputClass(!!errors[field])}
                  placeholder={placeholder}
                  disabled={busy}
                />
                {errors[field] && <p className={errorText}>{errors[field]?.message}</p>}
              </div>
            ))}
          </div>

          {/* ---------- container ---------- */}
          <div className="md:col-span-2 mt-2 border-t border-slate-100 pt-4">
            <p className="text-sm font-bold text-slate-800">Container</p>
          </div>

          <div>
            <label htmlFor="img-entrypoint" className={labelClass}>
              Entrypoint script <span className="text-red-500">*</span>
            </label>
            <input
              id="img-entrypoint"
              {...register('entrypointScript', {
                required: 'Entrypoint is required',
                maxLength: { value: 255, message: 'At most 255 characters' },
              })}
              aria-invalid={!!errors.entrypointScript}
              className={cn(inputClass(!!errors.entrypointScript), 'font-mono')}
              placeholder="/bin/bash /run.sh"
              disabled={busy}
            />
            {errors.entrypointScript && <p className={errorText}>{errors.entrypointScript.message}</p>}
          </div>

          <div>
            <label htmlFor="img-workdir" className={labelClass}>Working directory</label>
            <input
              id="img-workdir"
              {...register('workdir', { maxLength: { value: 255, message: 'At most 255 characters' } })}
              className={cn(inputClass(!!errors.workdir), 'font-mono')}
              placeholder="/workspace"
              disabled={busy}
            />
            <p className={hintText}>Empty = use the image's WORKDIR</p>
          </div>

          <div className="md:col-span-2">
            <label htmlFor="img-ports" className={labelClass}>Exposed ports</label>
            <input
              id="img-ports"
              {...register('exposedPorts', {
                validate: (v) => {
                  const result = parsePorts(v)
                  return typeof result === 'string' ? result : true
                },
              })}
              aria-invalid={!!errors.exposedPorts}
              className={cn(inputClass(!!errors.exposedPorts), 'font-mono')}
              placeholder="8080, 5173, 8443"
              disabled={busy}
            />
            {errors.exposedPorts ? (
              <p className={errorText}>{errors.exposedPorts.message}</p>
            ) : (
              <p className={hintText}>Separate with commas. Students reach the lab through these ports.</p>
            )}
          </div>

          <div className="md:col-span-2">
            <div className="mb-1.5 flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-500">Environment variables</span>
              <button
                type="button"
                onClick={() => env.append({ key: '', value: '' })}
                className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600 hover:underline disabled:opacity-50"
                disabled={busy}
              >
                <Plus size={13} aria-hidden /> Add variable
              </button>
            </div>
            {env.fields.length === 0 ? (
              <p className="rounded-lg border border-dashed border-slate-200 px-3 py-3 text-xs text-slate-400">No variables</p>
            ) : (
              <div className="space-y-2">
                {env.fields.map((row, index) => {
                  const keyError = errors.envVars?.[index]?.key
                  return (
                    <div key={row.id}>
                      <div className="grid grid-cols-[1fr_1fr_auto] gap-2">
                        <input
                          {...register(`envVars.${index}.key`, {
                            validate: (v) => !v.trim() || ENV_KEY_PATTERN.test(v.trim()) || 'Letters, digits, _ (not starting with a digit)',
                          })}
                          aria-label={`Variable ${index + 1} name`}
                          aria-invalid={!!keyError}
                          className={cn(inputClass(!!keyError), 'font-mono')}
                          placeholder="NAME"
                          disabled={busy}
                        />
                        <input
                          {...register(`envVars.${index}.value`)}
                          aria-label={`Variable ${index + 1} value`}
                          className={cn(inputClass(false), 'font-mono')}
                          placeholder="value"
                          disabled={busy}
                        />
                        <button
                          type="button"
                          className={`${iconButton} hover:border-red-200 hover:bg-red-50 hover:text-red-600`}
                          onClick={() => env.remove(index)}
                          aria-label={`Remove variable ${index + 1}`}
                          disabled={busy}
                        >
                          <X size={14} aria-hidden />
                        </button>
                      </div>
                      {keyError && <p className={errorText}>{keyError.message}</p>}
                    </div>
                  )
                })}
              </div>
            )}
            <p className={hintText}>Stored as plain text in the lab config. Don't put real credentials here.</p>
          </div>
        </form>

        {phase.kind === 'uploading' && (
          <div className="mt-6" aria-live="polite">
            <div className="mb-1.5 flex justify-between text-xs font-semibold text-slate-600">
              <span>Uploading {file?.name}</span>
              <span>{phase.percent}%</span>
            </div>
            <div
              className="h-2 overflow-hidden rounded-full bg-slate-100"
              role="progressbar"
              aria-valuenow={phase.percent}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="Upload progress"
            >
              <div className="h-full rounded-full bg-blue-600 transition-[width]" style={{ width: `${phase.percent}%` }} />
            </div>
            <p className={hintText}>Keep this page open until the upload finishes.</p>
          </div>
        )}

        <div className="mt-6 flex justify-end gap-3">
          <button className={secondary} onClick={onCancel} type="button" disabled={busy}>
            Cancel
          </button>
          <button
            className={cn(primary, 'disabled:cursor-not-allowed disabled:opacity-60')}
            onClick={onValid}
            type="button"
            disabled={busy}
          >
            {busy ? <Loader2 size={15} className="animate-spin" aria-hidden /> : <UploadCloud size={15} aria-hidden />}
            {phase.kind === 'requesting' ? 'Preparing upload…' : phase.kind === 'uploading' ? 'Uploading…' : 'Upload image'}
          </button>
        </div>
      </div>
    </section>
  )
}
