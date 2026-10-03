import { ChevronDown, FlaskConical, Grid2X2, Library, Plus, BookOpen } from 'lucide-react'
import { cn } from '../../lib/utils'
import { iconButton } from './styles'

const courses = [
  { code: 'CS204', name: 'Data Structures & Algorithms', students: 48, active: true, icon: Grid2X2 },
  { code: 'CS315', name: 'Computer Networks', students: 36, icon: BookOpen },
  { code: 'CS342', name: 'Operating Systems', students: 42, icon: Library },
  { code: 'CS490', name: 'Cloud Systems Studio', students: 18, draft: true, icon: FlaskConical },
]

interface CourseSidebarProps {
  onCreateCourse: () => void
}

export default function CourseSidebar({ onCreateCourse }: CourseSidebarProps) {
  return (
    <aside className="h-fit rounded-2xl border border-slate-200 bg-white p-3 shadow-[0_8px_30px_-20px_rgba(15,23,42,0.35)]">
      <div className="flex items-center justify-between px-2 pb-3">
        <div>
          <p className="text-sm font-bold">Your courses</p>
          <p className="text-[11px] text-slate-500">4 courses · 144 students</p>
        </div>
        <button 
          className={iconButton} 
          aria-label="Add course" 
          onClick={onCreateCourse}
        >
          <Plus size={16} />
        </button>
      </div>
      
      <button className="mb-2 flex h-9 w-full items-center justify-between rounded-lg bg-slate-50 px-3 text-xs font-semibold text-slate-600">
        Semester 1 · 2026 <ChevronDown size={14} />
      </button>
      
      <div className="grid gap-1">
        {courses.map((item) => {
          const Icon = item.icon
          return (
            <button 
              key={item.code} 
              className={cn(
                'rounded-xl p-3 text-left transition',
                item.active 
                  ? 'bg-blue-50 ring-1 ring-blue-200' 
                  : 'hover:bg-slate-50'
              )}
            >
              <div className="flex gap-3">
                <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-white text-blue-600 shadow-sm">
                  <Icon size={15} />
                </span>
                <span className="min-w-0">
                  <span className="block text-[11px] font-bold text-blue-600">{item.code}</span>
                  <span className="block text-xs font-semibold text-slate-700">{item.name}</span>
                  <span className="mt-1 block text-[10px] text-slate-400">
                    {item.students} students {item.draft && '· Draft'}
                  </span>
                </span>
              </div>
            </button>
          )
        })}
      </div>
    </aside>
  )
}
