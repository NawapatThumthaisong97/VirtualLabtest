import { useState, useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { Check, FlaskConical, Plus, Edit3, Trash2 } from 'lucide-react'
import { cn } from '../../lib/utils'
import Card from './Card'
import SectionHeader from './SectionHeader'
import { primary, secondary, iconButton } from './styles'
import LabForm from './LabForm'
import { labService, type Lab } from '../../services/lab'
import { useToast } from '../../hooks/useToast'
import ConfirmModal from '../ConfirmModal'

interface LabsTabProps {
  courseId: string
}

export default function LabsTab({ courseId }: LabsTabProps) {
  const [labs, setLabs] = useState<Lab[]>([])
  const [loading, setLoading] = useState(true)
  const [isCreating, setIsCreating] = useState(false)
  const [editingLab, setEditingLab] = useState<Lab | null>(null)
  const [deleteModalOpen, setDeleteModalOpen] = useState(false)
  const [labToDelete, setLabToDelete] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const toast = useToast()

  const fetchLabs = async () => {
    setLoading(true)
    try {
      const data = await labService.getByCourse(courseId)
      setLabs(data)
    } catch (error) {
      console.error('Failed to fetch labs:', error)
      toast.error('Failed to load labs', 'Unable to fetch lab list.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchLabs()
  }, [courseId])

  const handleEditLab = async (lab: Lab) => {
    try {
      // Fetch full lab detail from API
      const labDetail = await labService.getById(lab.id)
      setEditingLab(labDetail)
      setIsCreating(true)
    } catch (error: any) {
      console.error('Failed to fetch lab detail:', error)
      toast.error('Failed to load lab', 'Unable to fetch lab details.')
    }
  }

  const handleSubmit = async (data: any) => {
    try {
      const payload = {
        title: data.title,
        orderNo: parseInt(data.orderNo),
        description: data.description || null,
        docUrl: data.docUrl || null,
        imageId: data.imageId || null,
        dueAt: data.dueAt || null,
        status: data.status,
      };

      if (editingLab) {
        // Update existing lab
        await labService.update(editingLab.id, payload)
        toast.success('Lab updated!', 'Your changes have been saved.')
      } else {
        // Create new lab
        await labService.create({ ...payload, courseId })
        toast.success('Lab created!', 'New lab has been added successfully.')
      }
      
      setIsCreating(false)
      setEditingLab(null)
      fetchLabs()
    } catch (error: any) {
      console.error('Failed to save lab:', error)
      toast.error('Failed to save lab', error.response?.data?.detail || 'Please try again.')
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
      fetchLabs()
    } catch (error: any) {
      console.error('Failed to delete lab:', error)
      toast.error('Failed to delete', error.response?.data?.detail || 'Please try again.')
    } finally {
      setDeleting(false)
    }
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-GB', { 
      day: 'numeric', 
      month: 'short'
    })
  }

  const publishedLabs = labs.filter(l => l.status === 'published')
  const draftLabs = labs.filter(l => l.status === 'draft')

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
            <button 
              className={primary} 
              onClick={() => { 
                setIsCreating(true)
                setEditingLab(null)
              }}
            >
              <Plus size={16} /> Create lab
            </button>
          } 
        />
        
        <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
          {[
            [publishedLabs.length.toString(), 'Published labs'], 
            ['—', 'Avg. completion'], 
            [draftLabs.length.toString(), 'Drafts to review']
          ].map(([v, l]) => (
            <div key={l} className="rounded-xl bg-blue-50 px-4 py-3">
              <p className="text-xl font-bold">{v}</p>
              <p className="text-[11px] text-slate-500">{l}</p>
            </div>
          ))}
        </div>
        
        {loading ? (
          <div className="mt-5 flex items-center justify-center py-12">
            <div className="text-sm text-slate-400">Loading labs...</div>
          </div>
        ) : labs.length === 0 ? (
          <div className="mt-5 rounded-xl border border-dashed border-slate-300 py-12 text-center">
            <FlaskConical className="mx-auto text-slate-300" size={32} />
            <p className="mt-3 text-sm font-semibold text-slate-600">No labs yet</p>
            <p className="mt-1 text-xs text-slate-400">Create your first lab to get started.</p>
          </div>
        ) : (
          <div className="mt-5 overflow-hidden rounded-xl border border-slate-200">
            {labs.map((lab) => (
              <div 
                key={lab.id} 
                className="grid grid-cols-[auto_1fr_100px_90px_auto] items-center gap-3 border-b border-slate-200 px-4 py-3 text-xs last:border-0"
              >
                <div className="font-mono text-slate-400">#{lab.orderNo}</div>
                <div>
                  <button 
                    className="text-left font-semibold text-blue-700 hover:text-blue-900 hover:underline" 
                    onClick={() => handleEditLab(lab)}
                  >
                    {lab.title}
                  </button>
                  <p className="text-[11px] text-slate-400">{lab.description || 'No description'}</p>
                </div>
                <span className="text-slate-600">
                  {lab.dueAt ? formatDate(lab.dueAt) : '—'}
                </span>
                <span className={cn(
                  'w-fit rounded-full px-2 py-1 text-[10px] font-bold',
                  lab.status === 'published' && 'bg-emerald-50 text-emerald-700',
                  lab.status === 'draft' && 'bg-amber-50 text-amber-700',
                  lab.status === 'archived' && 'bg-slate-100 text-slate-600'
                )}>
                  {lab.status === 'published' ? 'Published' : lab.status === 'draft' ? 'Draft' : 'Archived'}
                </span>
                <div className="flex gap-1">
                  <button 
                    className={iconButton} 
                    onClick={() => handleEditLab(lab)}
                    aria-label="Edit lab"
                  >
                    <Edit3 size={14} />
                  </button>
                  <button 
                    className={`${iconButton} hover:border-red-200 hover:bg-red-50 hover:text-red-600`}
                    onClick={() => handleDelete(lab.id)}
                    aria-label="Delete lab"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
      
      {isCreating && (
        <LabForm
          lab={editingLab}
          onSubmit={handleSubmit}
          onCancel={() => {
            setIsCreating(false)
            setEditingLab(null)
          }}
        />
      )}
    </>
  )
}
