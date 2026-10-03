import { useState } from 'react'
import { Check, Pencil, X, Trash2 } from 'lucide-react'
import { cn } from '../../lib/utils'
import Card from './Card'
import SectionHeader from './SectionHeader'
import FormField from './FormField'
import { primary, secondary } from './styles'
import { BACKGROUND_KEYS, ICON_KEYS, BACKGROUND_PRESETS, ICON_PRESETS } from '../../constants/coursePresets'
import type { BackgroundKey, IconKey } from '../../constants/coursePresets'
import type { Course } from './types'
import { BookOpen } from 'lucide-react'
import { coursesService } from '../../services/courses'
import { useToast } from '../../hooks/useToast'
import ConfirmModal from '../ConfirmModal'

interface OverviewTabProps {
  course: Course
  setCourse: (course: Course) => void
  onDelete?: () => void
}

export default function OverviewTab({ course, setCourse, onDelete }: OverviewTabProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(course)
  const [saving, setSaving] = useState(false)
  const [deleteModalOpen, setDeleteModalOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const toast = useToast()
  
  const update = (key: keyof Course, value: string) => setDraft({ ...draft, [key]: value })

  const handleSave = async () => {
    setSaving(true)
    try {
      const updated = await coursesService.update(course.id, {
        code: draft.code,
        name: draft.name,
        lecturerName: draft.lecturer_name,
        backgroundKey: draft.background_key as any,
        iconKey: draft.icon_key as any,
      })
      
      setCourse({
        ...draft,
        announcements: updated.announcements,
      })
      setEditing(false)
      toast.success('Course updated!', 'Your changes have been saved successfully.')
    } catch (error: any) {
      console.error('Failed to update course:', error)
      
      // Handle specific error messages
      if (error.response?.status === 409) {
        toast.error('Course code already exists', `Another course already uses code "${draft.code}".`)
      } else if (error.response?.data?.detail) {
        toast.error('Update failed', error.response.data.detail)
      } else {
        toast.error('Update failed', 'Unable to save changes. Please try again.')
      }
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteCourse = async () => {
    setDeleting(true)
    try {
      await coursesService.deleteCourse(course.id)
      toast.success('Course deleted!', 'The course has been removed successfully.')
      setDeleteModalOpen(false)
      onDelete?.() // Navigate away or refresh list
    } catch (error: any) {
      console.error('Failed to delete course:', error)
      
      if (error.response?.status === 409) {
        toast.error('Cannot delete course', 'This course has enrolled students or labs. Please remove them first.')
      } else if (error.response?.data?.detail) {
        toast.error('Delete failed', error.response.data.detail)
      } else {
        toast.error('Delete failed', 'Unable to delete course. Please try again.')
      }
    } finally {
      setDeleting(false)
    }
  }
  
  return (
    <>
      <ConfirmModal
        isOpen={deleteModalOpen}
        onClose={() => setDeleteModalOpen(false)}
        onConfirm={handleDeleteCourse}
        title="Delete Course"
        message={`Are you sure you want to delete "${course.code} - ${course.name}"? This action cannot be undone and will only succeed if there are no enrolled students or labs.`}
        confirmText="Delete Course"
        cancelText="Cancel"
        variant="danger"
        isLoading={deleting}
      />
      
      <div className="grid gap-5 lg:grid-cols-2">
      <Card className="lg:col-span-2">
        <SectionHeader 
          icon={BookOpen} 
          title="Course details" 
          description="CRUD workspace for course identity and learner-facing information" 
          action={
            <button 
              className={editing ? secondary : primary} 
              onClick={() => { 
                setEditing(!editing)
                setDraft(course) 
              }}
            >
              {editing ? <><X size={15} /> Cancel</> : <><Pencil size={15} /> Edit course</>}
            </button>
          } 
        />
        
        {editing ? (
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            <FormField label="Course code" value={draft.code} onChange={(v) => update('code', v)} />
            <FormField label="Course name" value={draft.name} onChange={(v) => update('name', v)} />
            <FormField label="Lecturer name" value={draft.lecturer_name} onChange={(v) => update('lecturer_name', v)} />
            
            {/* Background Selection with Preview */}
            <div>
              <label htmlFor="edit-backgroundKey" className="mb-1.5 block text-xs font-semibold text-slate-500">
                Background
              </label>
              <div className="flex gap-2">
                <select
                  id="edit-backgroundKey"
                  value={draft.background_key || ''}
                  onChange={(e) => update('background_key', e.target.value)}
                  className="h-10 flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm text-slate-700 outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100"
                >
                  <option value="">None</option>
                  {BACKGROUND_KEYS.map((key) => (
                    <option key={key} value={key}>
                      {key.charAt(0).toUpperCase() + key.slice(1)}
                    </option>
                  ))}
                </select>
                {draft.background_key && (
                  <div className="h-10 w-16 shrink-0 overflow-hidden rounded-lg border border-slate-200">
                    <img 
                      src={BACKGROUND_PRESETS[draft.background_key as BackgroundKey]} 
                      alt="Preview"
                      className="h-full w-full object-cover"
                    />
                  </div>
                )}
              </div>
            </div>

            {/* Icon Selection with Preview */}
            <div>
              <label htmlFor="edit-iconKey" className="mb-1.5 block text-xs font-semibold text-slate-500">
                Icon
              </label>
              <div className="flex gap-2">
                <select
                  id="edit-iconKey"
                  value={draft.icon_key || ''}
                  onChange={(e) => update('icon_key', e.target.value)}
                  className="h-10 flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm text-slate-700 outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100"
                >
                  <option value="">None</option>
                  {ICON_KEYS.map((key) => (
                    <option key={key} value={key}>
                      {key.charAt(0).toUpperCase() + key.slice(1)}
                    </option>
                  ))}
                </select>
                {draft.icon_key && (
                  <div className="h-10 w-16 shrink-0 flex items-center justify-center overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
                    <img 
                      src={ICON_PRESETS[draft.icon_key as IconKey]} 
                      alt="Preview"
                      className="h-7 w-7 object-contain"
                    />
                  </div>
                )}
              </div>
            </div>
            
            <div className="flex justify-end gap-3 md:col-span-2">
              <button className={secondary} onClick={() => setEditing(false)} disabled={saving}>
                Cancel
              </button>
              <button 
                className={primary} 
                onClick={handleSave}
                disabled={saving}
              >
                {saving ? (
                  <>Saving...</>
                ) : (
                  <><Check size={15} /> Save changes</>
                )}
              </button>
            </div>
          </div>
        ) : (
          <div className="mt-5 grid gap-5 md:grid-cols-[280px_1fr]">
            <div className="relative overflow-hidden rounded-xl bg-slate-900">
              {course.image_url ? (
                <img 
                  className="h-44 w-full object-cover opacity-90" 
                  src={course.image_url} 
                  alt={`${course.name} course cover`} 
                />
              ) : course.background_key ? (
                <img 
                  className="h-44 w-full object-cover opacity-90" 
                  src={BACKGROUND_PRESETS[course.background_key as BackgroundKey]} 
                  alt={`${course.name} course cover`} 
                />
              ) : (
                <div className="h-44 w-full bg-gradient-to-br from-blue-600 to-blue-800" />
              )}
              <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-slate-950/80 to-transparent px-4 pb-3 pt-8 text-xs font-medium text-white">
                {course.name}
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <FormField label="Course code" value={course.code} />
              <FormField label="Course name" value={course.name} />
              <FormField label="Lecturer name" value={course.lecturer_name} />
              <FormField label="Background key" value={course.background_key || 'None'} />
              <FormField label="Icon key" value={course.icon_key || 'None'} />
            </div>
          </div>
        )}
      </Card>
      
      {/* Danger Zone - Delete Course */}
      <Card className="lg:col-span-2 border-red-200 bg-red-50/30">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-sm font-bold text-red-900">Danger Zone</h3>
            <p className="mt-1 text-xs text-red-700">
              Delete this course permanently. This action cannot be undone and will only succeed if there are no enrolled students or labs.
            </p>
          </div>
          <button
            onClick={() => setDeleteModalOpen(true)}
            className="inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-red-300 bg-white px-4 text-sm font-semibold text-red-700 shadow-sm transition hover:bg-red-50 active:bg-red-100"
          >
            <Trash2 size={15} />
            Delete Course
          </button>
        </div>
      </Card>
    </div>
    </>
  )
}
