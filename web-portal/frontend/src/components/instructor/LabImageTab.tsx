import { useCallback, useEffect, useState } from 'react'
import { ChevronDown, Container, Cpu, HardDrive, MemoryStick, Plus, RefreshCw, Timer, Trash2 } from 'lucide-react'
import ConfirmModal from '../ConfirmModal'
import { cn } from '../../lib/utils'
import Card from './Card'
import SectionHeader from './SectionHeader'
import { iconButton, primary } from './styles'
import LabImageForm from './LabImageForm'
import ScanStatusBadge from './ScanStatusBadge'
import {
  apiErrorMessage,
  labImageService,
  type CreateLabImagePayload,
  type LabImage,
} from '../../services/labImage'
import { startUpload, useUploadStore } from '../../services/labImageUploads'
import { useToast } from '../../hooks/useToast'

interface LabImageTabProps {
  courseId: string
}

/** ระหว่างนี้ผลสแกนยังเปลี่ยนได้ จึงต้องถามซ้ำ */
const IN_PROGRESS = new Set(['queued', 'running', 'passed'])
const POLL_MS = 10_000

const isInProgress = (image: LabImage) =>
  image.status === 'pending' && (IN_PROGRESS.has(image.scanStatus) || (image.scanStatus === 'not_started' && !!image.archiveUploadedAt))

const formatDateTime = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
    : '—'

export default function LabImageTab({ courseId }: LabImageTabProps) {
  const [images, setImages] = useState<LabImage[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<LabImage | null>(null)
  const [deleting, setDeleting] = useState(false)
  const toast = useToast()
  // การอัปโหลดของวิชานี้ที่กำลังเดินอยู่ (อยู่ใน store กลาง ไม่หายเมื่อออกจากหน้านี้)
  const uploads = useUploadStore((state) => state.uploads)
  const uploadOf = (imageId: string) => uploads.find((u) => u.id === imageId && u.courseId === courseId)
  // เปลี่ยนเมื่อการอัปโหลดของวิชานี้จบ (สำเร็จ / ล้ม / ยกเลิก) ใช้สั่งโหลดรายการใหม่
  const finishedKey = uploads
    .filter((u) => u.courseId === courseId && u.status !== 'uploading')
    .map((u) => `${u.id}:${u.status}`)
    .join(',')

  const fetchImages = useCallback(
    async (quiet = false) => {
      if (quiet) setRefreshing(true)
      else setLoading(true)
      try {
        setImages(await labImageService.listByCourse(courseId))
      } catch (error) {
        console.error('Failed to fetch lab images:', error)
        if (!quiet) toast.error('Failed to load images', apiErrorMessage(error))
      } finally {
        setLoading(false)
        setRefreshing(false)
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [courseId],
  )

  useEffect(() => {
    setShowForm(false)
    setExpanded(null)
    fetchImages()
  }, [fetchImages])

  // ถามสถานะสแกนซ้ำเฉพาะตอนที่ยังมี image กำลังสแกน
  // รวมการอัปโหลดที่เพิ่งจบ: webhook จาก R2 อาจมาช้ากว่า PUT ไม่กี่วินาที ถ้าไม่ถามซ้ำแถวจะค้างที่ "No file received"
  const hasInProgress =
    images.some(isInProgress) || uploads.some((u) => u.courseId === courseId && (u.status === 'uploading' || u.status === 'done'))
  useEffect(() => {
    if (!hasInProgress) return
    const timer = window.setInterval(() => fetchImages(true), POLL_MS)
    return () => window.clearInterval(timer)
  }, [hasInProgress, fetchImages])

  // การอัปโหลดจบ (แม้จบตอนอยู่หน้าอื่นแล้วกลับมา) → โหลดสถานะใหม่ แถวจะเปลี่ยนเป็น QUEUED เมื่อ webhook มาถึง
  useEffect(() => {
    if (finishedKey) fetchImages(true)
  }, [finishedKey, fetchImages])

  /**
   * ขั้นที่ 1 (ขอ presigned URL) รอในฟอร์ม เพราะ error อย่างชื่อซ้ำต้องแก้ในฟอร์ม
   * ขั้นที่ 2 (PUT ไฟล์) ส่งให้ startUpload ทำเบื้องหลัง แล้วปิดฟอร์มทันที ความคืบหน้าอยู่ที่ UploadTray
   */
  const handleUpload = async (payload: CreateLabImagePayload, file: File) => {
    setSubmitting(true)
    let upload
    try {
      upload = await labImageService.createUpload(payload)
    } catch (error: any) {
      const status = error?.response?.status
      toast.error(
        status === 409 ? 'Name already taken' : status === 403 ? 'Not allowed' : 'Could not start upload',
        apiErrorMessage(error),
      )
      return
    } finally {
      setSubmitting(false)
    }

    void startUpload(upload, file, payload)
    setShowForm(false)
    setExpanded(upload.imageId)
    fetchImages(true) // ให้แถว draft โผล่ในรายการพร้อมแถบความคืบหน้า
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      const { detachedLabs } = await labImageService.remove(deleteTarget.id)
      toast.success(
        'Image deleted',
        detachedLabs > 0 ? `Removed from ${detachedLabs} lab(s). Those labs now have no image.` : undefined,
      )
      setDeleteTarget(null)
      setExpanded(null)
      fetchImages(true)
    } catch (error: any) {
      toast.error(error?.response?.status === 403 ? 'Not allowed' : 'Delete failed', apiErrorMessage(error))
    } finally {
      setDeleting(false)
    }
  }

  const readyCount = images.filter((i) => i.status === 'approved').length
  const scanningCount = images.filter(isInProgress).length
  const problemCount = images.filter((i) => i.scanStatus === 'failed' || i.scanStatus === 'error').length

  return (
    <>
      <Card>
        <SectionHeader
          icon={Container}
          title="Lab images"
          description={`${images.length} images · container environments students run in this course`}
          action={
            <div className="flex gap-2">
              <button
                className={iconButton}
                onClick={() => fetchImages(true)}
                aria-label="Refresh images"
                disabled={refreshing || loading}
              >
                <RefreshCw size={14} className={cn(refreshing && 'animate-spin')} aria-hidden />
              </button>
              <button className={primary} onClick={() => setShowForm(true)} disabled={showForm}>
                <Plus size={16} aria-hidden /> Upload image
              </button>
            </div>
          }
        />

        <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
          {[
            [readyCount, 'Ready to use'],
            [scanningCount, 'Being scanned'],
            [problemCount, 'Need attention'],
          ].map(([value, label]) => (
            <div key={label} className="rounded-xl bg-blue-50 px-4 py-3">
              <p className="text-xl font-bold">{value}</p>
              <p className="text-[11px] text-slate-500">{label}</p>
            </div>
          ))}
        </div>

        {loading ? (
          <div className="mt-5 flex items-center justify-center py-12">
            <div className="text-sm text-slate-400">Loading images...</div>
          </div>
        ) : images.length === 0 ? (
          <div className="mt-5 rounded-xl border border-dashed border-slate-300 py-12 text-center">
            <Container className="mx-auto text-slate-300" size={32} aria-hidden />
            <p className="mt-3 text-sm font-semibold text-slate-600">No images yet</p>
            <p className="mt-1 text-xs text-slate-400">Upload a docker image (.tar) to give your labs a runtime.</p>
          </div>
        ) : (
          <ul className="mt-5 overflow-hidden rounded-xl border border-slate-200">
            {images.map((image) => {
              const open = expanded === image.id
              const upload = uploadOf(image.id)
              const uploading = upload?.status === 'uploading'
              const summary = image.scanSummary
              const reasons = summary?.reasons ?? []
              const warnings = summary?.warnings ?? []
              return (
                <li key={image.id} className="border-b border-slate-200 last:border-0">
                  <button
                    type="button"
                    onClick={() => setExpanded(open ? null : image.id)}
                    aria-expanded={open}
                    className="grid w-full grid-cols-[1fr_auto_auto] items-center gap-3 px-4 py-3 text-left text-xs transition hover:bg-slate-50 focus-visible:bg-slate-50 focus-visible:outline-none"
                  >
                    <div className="min-w-0">
                      <p className="truncate font-mono text-[13px] font-semibold text-slate-800">
                        {image.repository}:{image.tag}
                      </p>
                      <p className="truncate text-[11px] text-slate-400">
                        {uploading ? (
                          <span className="font-semibold text-blue-600">Uploading {upload.percent}% · </span>
                        ) : null}
                        {image.description || 'No description'} · {image.sizeMb} MB · added {formatDateTime(image.createdAt)}
                      </p>
                    </div>
                    <ScanStatusBadge image={image} />
                    <ChevronDown size={16} className={cn('text-slate-400 transition', open && 'rotate-180')} aria-hidden />
                  </button>

                  {open && (
                    <div className="grid gap-4 border-t border-slate-100 bg-slate-50/60 px-4 py-4 text-xs text-slate-600 md:grid-cols-2">
                      <div className="space-y-2">
                        <p className="font-semibold text-slate-800">Configuration</p>
                        <div className="flex flex-wrap gap-x-4 gap-y-1.5">
                          <span className="inline-flex items-center gap-1"><Cpu size={13} aria-hidden /> {image.cpuRequirement} CPU</span>
                          <span className="inline-flex items-center gap-1"><MemoryStick size={13} aria-hidden /> {image.memoryRequirement} GB</span>
                          <span className="inline-flex items-center gap-1"><HardDrive size={13} aria-hidden /> {image.diskSize} GB disk</span>
                          <span className="inline-flex items-center gap-1"><Timer size={13} aria-hidden /> {image.lifespanMinutes} min</span>
                        </div>
                        <dl className="grid grid-cols-[110px_1fr] gap-x-2 gap-y-1">
                          <dt className="text-slate-400">Ports</dt>
                          <dd className="font-mono">{image.exposedPorts.length ? image.exposedPorts.join(', ') : '—'}</dd>
                          <dt className="text-slate-400">Entrypoint</dt>
                          <dd className="break-all font-mono">{image.entrypointScript || <FromImage />}</dd>
                          <dt className="text-slate-400">Workdir</dt>
                          <dd className="font-mono">{image.workdir || <FromImage />}</dd>
                          <dt className="text-slate-400">Env vars</dt>
                          <dd className="font-mono">
                            {image.envVars && Object.keys(image.envVars).length ? Object.keys(image.envVars).join(', ') : '—'}
                          </dd>
                          <dt className="text-slate-400">Digest</dt>
                          <dd className="break-all font-mono">{image.imageDigest ? `${image.imageDigest.slice(0, 19)}…` : '—'}</dd>
                        </dl>
                      </div>

                      <div className="space-y-2">
                        <p className="font-semibold text-slate-800">Security scan</p>
                        <dl className="grid grid-cols-[110px_1fr] gap-x-2 gap-y-1">
                          <dt className="text-slate-400">Uploaded</dt>
                          <dd>{formatDateTime(image.archiveUploadedAt)}</dd>
                          <dt className="text-slate-400">Started</dt>
                          <dd>{formatDateTime(image.scanStartedAt)}</dd>
                          <dt className="text-slate-400">Finished</dt>
                          <dd>{formatDateTime(image.scanFinishedAt)}</dd>
                          <dt className="text-slate-400">Attempts</dt>
                          <dd>{image.scanAttempts}</dd>
                          {summary?.counts && (
                            <>
                              <dt className="text-slate-400">Findings</dt>
                              <dd>
                                {Object.entries(summary.counts)
                                  .filter(([, n]) => n > 0)
                                  .map(([severity, n]) => `${n} ${severity.toLowerCase()}`)
                                  .join(', ') || 'none'}
                              </dd>
                            </>
                          )}
                        </dl>

                        {!image.archiveUploadedAt && image.status === 'pending' && !uploading && upload?.status !== 'done' && (
                          <p className="rounded-lg bg-slate-100 px-3 py-2 text-slate-600">
                            No file received yet. If the upload was interrupted, upload again with the same name and tag.
                          </p>
                        )}
                        {summary?.lastError && isInProgress(image) && (
                          <p className="rounded-lg bg-amber-50 px-3 py-2 text-amber-800">Retrying: {summary.lastError}</p>
                        )}
                        {reasons.length > 0 && image.status !== 'approved' && (
                          <div className="rounded-lg bg-red-50 px-3 py-2 text-red-800">
                            <p className="font-semibold">Why it did not pass</p>
                            <ul className="mt-1 list-disc pl-4">
                              {reasons.map((reason) => <li key={reason}>{reason}</li>)}
                            </ul>
                            <p className="mt-1 text-[11px] text-red-700/80">Fix the image and upload it again with a new tag. This entry is removed after 7 days.</p>
                          </div>
                        )}
                        {warnings.length > 0 && (
                          <div className="rounded-lg bg-amber-50 px-3 py-2 text-amber-800">
                            <p className="font-semibold">Warnings</p>
                            <ul className="mt-1 list-disc pl-4">
                              {warnings.map((warning) => <li key={warning}>{warning}</li>)}
                            </ul>
                          </div>
                        )}
                        <button
                          type="button"
                          onClick={() => setDeleteTarget(image)}
                          className="mt-2 inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 py-1.5 text-xs font-semibold text-red-600 transition hover:bg-red-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
                        >
                          <Trash2 size={13} aria-hidden /> Delete image
                        </button>
                      </div>
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        )}

        {hasInProgress && (
          <p className="mt-3 text-[11px] text-slate-400" aria-live="polite">
            Scan status refreshes every {POLL_MS / 1000} seconds.
          </p>
        )}
      </Card>

      <ConfirmModal
        isOpen={!!deleteTarget}
        onClose={() => !deleting && setDeleteTarget(null)}
        onConfirm={handleDelete}
        title="Delete this image?"
        message={`${deleteTarget?.repository}:${deleteTarget?.tag} will be permanently removed from storage (R2) and ECR. Labs using it will be left without an image.`}
        confirmText="Delete"
        isLoading={deleting}
      />

      {showForm && (
        <LabImageForm
          courseId={courseId}
          submitting={submitting}
          onSubmit={handleUpload}
          onCancel={() => setShowForm(false)}
        />
      )}
    </>
  )
}

/** ช่องที่อาจารย์เว้นว่าง: ตอนรันใช้ค่าของ image เอง (ENTRYPOINT / CMD / WORKDIR) */
function FromImage() {
  return <span className="font-sans italic text-slate-400">from image</span>
}
