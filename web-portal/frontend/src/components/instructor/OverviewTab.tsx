import { useState } from 'react'
import { Check, Pencil, X } from 'lucide-react'
import { cn } from '../../lib/utils'
import Card from './Card'
import SectionHeader from './SectionHeader'
import FormField from './FormField'
import { primary, secondary } from './styles'
import { BACKGROUND_KEYS, ICON_KEYS, BACKGROUND_PRESETS, ICON_PRESETS } from '../../constants/coursePresets'
import type { BackgroundKey, IconKey } from '../../constants/coursePresets'
import type { Course } from './types'
import { BookOpen } from 'lucide-react'

interface OverviewTabProps {
  course: Course
  setCourse: (course: Course) => void
}

export default function OverviewTab({ course, setCourse }: OverviewTabProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(course)
  
  const update = (key: keyof Course, value: string) => setDraft({ ...draft, [key]: value })
  
  return (
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
                  value={draft.background_key}
                  onChange={(e) => update('background_key', e.target.value)}
                  className="h-10 flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm text-slate-700 outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100"
                >
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
                  value={draft.icon_key}
                  onChange={(e) => update('icon_key', e.target.value)}
                  className="h-10 flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm text-slate-700 outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100"
                >
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
              <button className={secondary} onClick={() => setEditing(false)}>Cancel</button>
              <button 
                className={primary} 
                onClick={() => { 
                  setCourse(draft)
                  setEditing(false) 
                }}
              >
                <Check size={15} /> Save changes
              </button>
            </div>
          </div>
        ) : (
          <div className="mt-5 grid gap-5 md:grid-cols-[280px_1fr]">
            <div className="relative overflow-hidden rounded-xl bg-slate-900">
              <img 
                className="h-44 w-full object-cover opacity-90" 
                src={course.image_url} 
                alt="Data Structures and Algorithms course cover" 
              />
              <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-slate-950/80 to-transparent px-4 pb-3 pt-8 text-xs font-medium text-white">
                {course.name}
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <FormField label="Course code" value={course.code} />
              <FormField label="Course name" value={course.name} />
              <FormField label="Lecturer name" value={course.lecturer_name} />
              <FormField label="Background key" value={course.background_key} />
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}
