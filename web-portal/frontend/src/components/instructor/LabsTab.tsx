import { useCallback, useEffect, useMemo, useState } from 'react'
import { Container, Edit3, FlaskConical, Plus, Trash2 } from 'lucide-react'
import { cn } from '../../lib/utils'
import Card from './Card'
import SectionHeader from './SectionHeader'
import { iconButton, primary } from './styles'
import LabForm, { type LabFormValues } from './LabForm'
import { labService, type Lab } from '../../services/lab'
import { apiErrorMessage, labImageService, type LabImage } from '../../services/labImage'
import { useToast } from '../../hooks/useToast'
import ConfirmModal from '../ConfirmModal'
import ScanStatusBadge from './ScanStatusBadge'

interface LabsTabProps {
  courseId: string
  /** สลับไปแท็บ Lab Image */
  onManageImages: () => void
}

const RUN_TARGET_LABEL: Record<Lab['runTarget'], string> = {
  kubernetes: 'Lab machines',
  aws: 'Cloud',
  auto: 'Auto',
}

export default function LabsTab({ courseId, onManageImages }: LabsTabProps) {
  const [labs, setLabs] = useState<Lab[]>([])
  const [images, setImages] = useState<LabImage[]>([])
  const [loading, setLoading] = useState(true)
  const [imagesLoading, setImagesLoading] = useState(true)
  const [isCreating, setIsCreating] = useState(false)
  const [editingLab, setEditingLab] = useState<Lab | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [deleteModalOpen, setDeleteModalOpen] = useState(false)
  const [labToDelete, setLabToDelete] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const toast = useToast()

  const fetchLabs = useCallback(async () => {
    setLoading(true)
    try {
      setLabs(await labService.getByCourse(courseId))
    } catch (error) {
      console.error('Failed to fetch labs:', error)
      toast.error('Failed to load labs', apiErrorMessage(error, 'Unable to fetch lab list.'))
    } finally {
      setLoading(false)
    }
  }, [courseId, toast])

  const fetchImages = useCallback(async () => {
    setImagesLoading(true)
    try {
      setImages(await labImageService.listByCourse(courseId))
    } catch (error) {
      // ไม่มีสิทธิ์ดู image ไม่ควรทำให้ทั้งแท็บใช้ไม่ได้ dropdown จะว่างแทน
      console.error('Failed to fetch lab images:', error)
      setImages([])
    } finally {
      setImagesLoading(false)
    }
  }, [courseId])

  useEffect(() => {
    fetchLabs()
    fetchImages()
    setIsCreating(false)
    setEditingLab(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId])

  const imageById = useMemo(() => new Map(images.map((image) => [image.id, image])), [images])

  const openCreate = () => {
    setEditingLab(null)
    setIsCreating(true)
    fetchImages() // อาจเพิ่งอัปโหลด image ใหม่จากอีกแท็บ
  }

  const handleEditLab = async (lab: Lab) => {
    try {
      const labDetail = await labService.getById(lab.id)
      setEditingLab(labDetail)
      setIsCreating(true)
      fetchImages()
    } catch (error) {
      console.error('Failed to fetch lab detail:', error)
      toast.error('Failed to load lab', apiErrorMessage(error, 'Unable to fetch lab details.'))
    }
  }

  const closeForm = () => {
    setIsCreating(false)
    setEditingLab(null)
  }

  const handleSubmit = async (data: LabFormValues) => {
    const payload = {
      title: data.title.trim(),
      orderNo: parseInt(data.orderNo, 10),
      description: data.description.trim() || null,
      docUrl: data.docUrl.trim() || null,
      imageId: data.imageId || null,
      // datetime-local เป็นเวลาท้องถิ่นไม่มี timezone แปลงเป็น ISO (UTC) ก่อนส่ง
      dueAt: data.dueAt ? new Date(data.dueAt).toISOString() : null,
      status: data.status,
      runTarget: data.runTarget,
    }

    setSubmitting(true)
    try {
      if (editingLab) {
        await labService.update(editingLab.id, payload)
        toast.success('Lab updated!', 'Your changes have been saved.')
      } else {
        await labService.create({ ...payload, courseId })
        toast.success('Lab created!', 'New lab has been added successfully.')
      }
      closeForm()
      fetchLabs()
    } catch (error) {
      console.error('Failed to save lab:', error)
      toast.error('Failed to save lab', apiErrorMessage(error))
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = (labId: string) => {
    setLabToDelete(labId)
    setDeleteModalOpen(true)
  }

  const confirmDelete = async () => {
    if (!labToDelete) return
    setDeleting(true)
    try {
      await labService.delete(labToDelete)
      toast.success('Lab deleted!', 'The lab has been removed.')
      setDeleteModalOpen(false)
      setLabToDelete(null)
      if (editingLab?.id === labToDelete) closeForm()
      fetchLabs()
    } catch (error) {
      console.error('Failed to delete lab:', error)
      toast.error('Failed to delete', apiErrorMessage(error))
    } finally {
      setDeleting(false)
    }
  }

  const formatDate = (dateString: string) =>
    new Date(dateString).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })

  const publishedCount = labs.filter((l) => l.status === 'published').length
  const draftCount = labs.filter((l) => l.status === 'draft').length
  const withImageCount = labs.filter((l) => l.imageId).length

  return (
    <>
      <ConfirmModal
        isOpen={deleteModalOpen}
        onClose={() => {
          setDeleteModalOpen(false)
          setLabToDelete(null)
        }}
        onConfirm={confirmDelete}
        title="Delete Lab"
        message="Are you sure you want to delete this lab? This action cannot be undone."
        confirmText="Delete"
        cancelText="Cancel"
        variant="danger"
        isLoading={deleting}
      />

      <Card>
        <SectionHeader
          icon={FlaskConical}
          title="Labs"
          description={`${labs.length} labs · create and configure hands-on learning activities`}
          action={
            <button className={primary} onClick={openCreate}>
              <Plus size={16} aria-hidden /> Create lab
            </button>
          }
        />

        <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
          {[
            [publishedCount, 'Published labs'],
            [draftCount, 'Drafts to review'],
            [withImageCount, 'Labs with a runtime image'],
          ].map(([value, label]) => (
            <div key={label} className="rounded-xl bg-blue-50 px-4 py-3">
              <p className="text-xl font-bold">{value}</p>
              <p className="text-[11px] text-slate-500">{label}</p>
            </div>
          ))}
        </div>

        {loading ? (
          <div className="mt-5 flex items-center justify-center py-12">
            <div className="text-sm text-slate-400">Loading labs...</div>
          </div>
        ) : labs.length === 0 ? (
          <div className="mt-5 rounded-xl border border-dashed border-slate-300 py-12 text-center">
            <FlaskConical className="mx-auto text-slate-300" size={32} aria-hidden />
            <p className="mt-3 text-sm font-semibold text-slate-600">No labs yet</p>
            <p className="mt-1 text-xs text-slate-400">Create your first lab to get started.</p>
          </div>
        ) : (
          <div className="mt-5 overflow-x-auto rounded-xl border border-slate-200">
            <div className="hidden min-w-[720px] grid-cols-[48px_1fr_220px_80px_90px_84px] gap-3 border-b border-slate-200 bg-slate-50 px-4 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400 md:grid">
              <span>#</span>
              <span>Lab</span>
              <span>Image</span>
              <span>Due</span>
              <span>Status</span>
              <span className="sr-only">Actions</span>
            </div>
            {labs.map((lab) => {
              const image = lab.imageId ? imageById.get(lab.imageId) : undefined
              return (
                <div
                  key={lab.id}
                  className="grid min-w-[720px] grid-cols-[48px_1fr_220px_80px_90px_84px] items-center gap-3 border-b border-slate-200 px-4 py-3 text-xs last:border-0"
                >
                  <div className="font-mono text-slate-400">#{lab.orderNo}</div>
                  <div className="min-w-0">
                    <button
                      className="text-left font-semibold text-blue-700 hover:text-blue-900 hover:underline"
                      onClick={() => handleEditLab(lab)}
                    >
                      {lab.title}
                    </button>
                    <p className="truncate text-[11px] text-slate-400">
                      {lab.description || 'No description'} · {RUN_TARGET_LABEL[lab.runTarget]}
                    </p>
                  </div>
                  <div className="min-w-0">
                    {image ? (
                      <div className="flex flex-col gap-1">
                        <span className="inline-flex min-w-0 items-center gap-1 font-mono text-[11px] text-slate-700">
                          <Container size={12} className="shrink-0 text-blue-600" aria-hidden />
                          <span className="truncate">{image.repository}:{image.tag}</span>
                        </span>
                        <ScanStatusBadge image={image} />
                      </div>
                    ) : lab.imageId ? (
                      <span className="font-mono text-[11px] text-slate-400">{lab.imageId.slice(0, 8)}…</span>
                    ) : (
                      <span className="text-[11px] text-slate-400">Reading only</span>
                    )}
                  </div>
                  <span className="text-slate-600">{lab.dueAt ? formatDate(lab.dueAt) : '—'}</span>
                  <span
                    className={cn(
                      'w-fit rounded-full px-2 py-1 text-[10px] font-bold',
                      lab.status === 'published' && 'bg-emerald-50 text-emerald-700',
                      lab.status === 'draft' && 'bg-amber-50 text-amber-700',
                      lab.status === 'archived' && 'bg-slate-100 text-slate-600',
                    )}
                  >
                    {lab.status === 'published' ? 'Published' : lab.status === 'draft' ? 'Draft' : 'Archived'}
                  </span>
                  <div className="flex gap-1">
                    <button className={iconButton} onClick={() => handleEditLab(lab)} aria-label={`Edit ${lab.title}`}>
                      <Edit3 size={14} aria-hidden />
                    </button>
                    <button
                      className={`${iconButton} hover:border-red-200 hover:bg-red-50 hover:text-red-600`}
                      onClick={() => handleDelete(lab.id)}
                      aria-label={`Delete ${lab.title}`}
                    >
                      <Trash2 size={14} aria-hidden />
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </Card>

      {isCreating && (
        <LabForm
          key={editingLab?.id ?? 'new'}
          lab={editingLab}
          images={images}
          imagesLoading={imagesLoading}
          submitting={submitting}
          onSubmit={handleSubmit}
          onCancel={closeForm}
          onManageImages={onManageImages}
        />
      )}
    </>
  )
}
