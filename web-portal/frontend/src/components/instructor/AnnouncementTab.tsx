import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Bell, Check, Edit3, Eye, Plus, Trash2, X } from 'lucide-react'
import { cn } from '../../lib/utils'
import Card from './Card'
import SectionHeader from './SectionHeader'
import { primary, secondary, iconButton } from './styles'
import type { Announcement } from './types'

export default function AnnouncementTab() {
  const [items, setItems] = useState<Announcement[]>([
    { 
      id: 1, 
      message: 'Please complete the environment check before Lab 01 and review the linked stack and queue notes.', 
      date: '24 Sep 2026 · 09:30', 
      published: true 
    }
  ])
  const [editing, setEditing] = useState<number | null>(null)
  
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
    setEditing(item?.id ?? 0)
    reset({ message: item?.message ?? '' })
  }
  
  const onSubmit = (data: { message: string }) => {
    if (!data.message.trim()) return
    
    if (editing && editing !== 0) {
      setItems(items.map((item) => item.id === editing ? { ...item, message: data.message } : item))
    } else {
      setItems([{ id: Date.now(), message: data.message, date: 'Just now', published: true }, ...items])
    }
    
    setEditing(null)
    reset()
  }
  
  const remove = (id: number) => setItems(items.filter((item) => item.id !== id))
  
  return (
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
              {editing === 0 ? 'New announcement' : 'Edit announcement'}
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
              <button type="submit" className={primary}>
                <Check size={15} /> Save announcement
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
                <p className="mt-1 text-xs text-slate-400">Dr. Narin Sutham · {item.date}</p>
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
  )
}
