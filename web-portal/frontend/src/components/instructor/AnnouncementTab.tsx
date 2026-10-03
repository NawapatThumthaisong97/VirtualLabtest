import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Bell, Check, Edit3, Eye, Plus, Trash2, X } from 'lucide-react'
import { cn } from '../../lib/utils'
import Card from './Card'
import SectionHeader from './SectionHeader'
import { primary, secondary, iconButton } from './styles'
import type { Announcement } from './types'
import { coursesService } from '../../services/courses'
import { useToast } from '../../hooks/useToast'
import ConfirmModal from '../ConfirmModal'

interface AnnouncementTabProps {
  announcements: Announcement[]
  courseId: string
  onUpdate?: () => void
}

export default function AnnouncementTab({ announcements, courseId, onUpdate }: AnnouncementTabProps) {
  const [items, setItems] = useState<Announcement[]>(announcements)
  const [editing, setEditing] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [deleteModalOpen, setDeleteModalOpen] = useState(false)
  const [announcementToDelete, setAnnouncementToDelete] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const toast = useToast()
  
  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
  } = useForm({
    defaultValues: {
      message: '',
    },
  })
  
  const open = (item?: Announcement) => {
    setEditing(item?.id ?? '0')
    reset({ message: item?.message ?? '' })
  }
  
  const onSubmit = async (data: { message: string }) => {
    if (!data.message.trim()) return
    
    setSaving(true)
    try {
      if (editing && editing !== '0') {
        // Update existing announcement
        const updated = await coursesService.updateAnnouncement(courseId, editing, {
          message: data.message
        })
        setItems(items.map((item) => item.id === editing ? updated : item))
        toast.success('Announcement updated!', 'Your changes have been saved.')
      } else {
        // Create new announcement
        const created = await coursesService.createAnnouncement(courseId, {
          message: data.message
        })
        setItems([created, ...items])
        toast.success('Announcement created!', 'Students can now see your announcement.')
      }
      
      setEditing(null)
      reset()
      onUpdate?.() // Refresh course detail
    } catch (error: any) {
      console.error('Failed to save announcement:', error)
      toast.error('Failed to save', error.response?.data?.detail || 'Please try again.')
    } finally {
      setSaving(false)
    }
  }
  
  const remove = async (id: string) => {
    setAnnouncementToDelete(id)
    setDeleteModalOpen(true)
  }

  const confirmDelete = async () => {
    if (!announcementToDelete) return
    
    setDeleting(true)
    try {
      await coursesService.deleteAnnouncement(courseId, announcementToDelete)
      setItems(items.filter((item) => item.id !== announcementToDelete))
      toast.success('Announcement deleted!', 'The announcement has been removed.')
      setDeleteModalOpen(false)
      setAnnouncementToDelete(null)
      onUpdate?.() // Refresh course detail
    } catch (error: any) {
      console.error('Failed to delete announcement:', error)
      toast.error('Failed to delete', error.response?.data?.detail || 'Please try again.')
    } finally {
      setDeleting(false)
    }
  }

  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    
    if (diffMins < 60) return 'Just now'
    if (diffMins < 1440) return `${Math.floor(diffMins / 60)} hours ago`
    
    return date.toLocaleDateString('en-GB', { 
      day: 'numeric', 
      month: 'short', 
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }
  
  return (
    <>
      <ConfirmModal
        isOpen={deleteModalOpen}
        onClose={() => {
          setDeleteModalOpen(false)
          setAnnouncementToDelete(null)
        }}
        onConfirm={confirmDelete}
        title="Delete Announcement"
        message="Are you sure you want to delete this announcement? This action cannot be undone."
        confirmText="Delete"
        cancelText="Cancel"
        variant="danger"
        isLoading={deleting}
      />
      
      <Card>
      <SectionHeader 
        icon={Bell} 
        title="Announcements" 
        description={`${items.length} announcements · manage what students see on the course page`} 
        action={
          <button className={primary} onClick={() => open()}>
            <Plus size={16} /> Add announcement
          </button>
        } 
      />
      
      {editing !== null && (
        <form onSubmit={handleSubmit(onSubmit)} className="mt-5 rounded-xl border border-blue-200 bg-blue-50/50 p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-800">
              {editing === '0' ? 'New announcement' : 'Edit announcement'}
            </h3>
            <button 
              type="button"
              className={iconButton} 
              onClick={() => {
                setEditing(null)
                reset()
              }} 
              aria-label="Close editor"
            >
              <X size={16} />
            </button>
          </div>
          
          <div className="mt-4 grid gap-4">
            <label>
              <span className="mb-1.5 block text-xs font-semibold text-slate-500">
                Message <span className="text-red-500">*</span>
              </span>
              <textarea 
                {...register('message', { 
                  required: 'Message is required',
                  minLength: { value: 1, message: 'Message cannot be empty' }
                })}
                className={cn(
                  'min-h-28 w-full resize-y rounded-lg border p-3 text-sm leading-6 outline-none focus:ring-4',
                  errors.message
                    ? 'border-red-300 bg-red-50 text-slate-700 focus:border-red-500 focus:ring-red-100'
                    : 'border-slate-200 bg-white text-slate-700 focus:border-blue-500 focus:ring-blue-100'
                )}
              />
              {errors.message && (
                <p className="mt-1 text-xs text-red-600">{errors.message.message}</p>
              )}
            </label>
            
            <div className="flex justify-end gap-3">
              <button 
                type="button"
                className={secondary} 
                onClick={() => {
                  setEditing(null)
                  reset()
                }}
              >
                Cancel
              </button>
              <button type="submit" className={primary} disabled={saving}>
                {saving ? (
                  <>Saving...</>
                ) : (
                  <><Check size={15} /> Save announcement</>
                )}
              </button>
            </div>
          </div>
        </form>
      )}
      
      <div className="mt-5 grid gap-3">
        {items.length === 0 && (
          <div className="rounded-xl border border-dashed border-slate-300 py-12 text-center">
            <Bell className="mx-auto text-slate-300" size={28} />
            <p className="mt-3 text-sm font-semibold text-slate-600">No announcements yet</p>
            <p className="mt-1 text-xs text-slate-400">Create one to keep your students informed.</p>
          </div>
        )}
        
        {items.map((item) => (
          <article 
            key={item.id} 
            className="rounded-xl border border-slate-200 bg-slate-50/60 p-4 transition hover:border-blue-200 hover:bg-blue-50/20"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="rounded-full bg-emerald-50 px-2 py-1 text-[10px] font-bold text-emerald-700">
                    Published
                  </span>
                </div>
                <p className="mt-1 text-xs text-slate-400">{item.authorName} · {formatDate(item.createdAt)}</p>
              </div>
              
              <div className="flex gap-2">
                <button 
                  className={iconButton} 
                  onClick={() => open(item)} 
                  aria-label="Edit announcement"
                >
                  <Edit3 size={15} />
                </button>
                <button 
                  className={`${iconButton} hover:border-red-200 hover:bg-red-50 hover:text-red-600`} 
                  onClick={() => remove(item.id)} 
                  aria-label="Delete announcement"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            </div>
            
            <p className="mt-4 text-sm leading-6 text-slate-600">{item.message}</p>
            <p className="mt-4 flex items-center gap-2 text-xs font-semibold text-emerald-600">
              <Eye size={14} /> Visible to 48 enrolled students
            </p>
          </article>
        ))}
      </div>
    </Card>
    </>
  )
}
