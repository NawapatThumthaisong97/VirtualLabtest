import { ChevronDown, FlaskConical, Grid2X2, Library, BookOpen, RotateCw } from 'lucide-react'
import { cn } from '../../lib/utils'
import { iconButton } from './styles'
import { useState, useEffect } from 'react'
import { coursesService, type Courses } from '../../services/courses'

const defaultCourseIcon: Record<string, any> = {
  'CS204': Grid2X2,
  'CS315': BookOpen,
  'CS342': Library,
  'CS490': FlaskConical,
}

interface CourseSidebarProps {
  onCreateCourse: () => void
  onSelectCourse?: (course: { id: string; code: string; name: string; lecturerName: string; imageUrl: string | null; backgroundKey: string | null; iconKey: string | null }) => void
  refreshTrigger?: number
}

export default function CourseSidebar({ onCreateCourse, onSelectCourse, refreshTrigger }: CourseSidebarProps) {
  const [selectedCourseCode, setSelectedCourseCode] = useState<string | null>(null)
  const [courses, setCourses] = useState<Courses[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const fetchCourses = async () => {
    setRefreshing(true)
    try {
      const data = await coursesService.getAll()
      setCourses(data)
    } catch (error) {
      console.error('Failed to fetch courses:', error)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    fetchCourses()
  }, [refreshTrigger])
  
  return (
    <aside className="h-fit rounded-2xl border border-slate-200 bg-white p-3 shadow-[0_8px_30px_-20px_rgba(15,23,42,0.35)]">
      <div className="flex items-center justify-between px-2 pb-3">
        <div>
          <p className="text-sm font-bold">Your courses</p>
          <p className="text-[11px] text-slate-500">
            {loading ? 'Loading...' : `${courses.length} courses`}
          </p>
        </div>
        <button 
          className={cn(
            iconButton,
            refreshing && 'pointer-events-none'
          )} 
          aria-label="Refresh courses" 
          onClick={fetchCourses}
          disabled={refreshing}
        >
          <RotateCw size={16} className={cn(refreshing && 'animate-spin')} />
        </button>
      </div>
      
      <button className="mb-2 flex h-9 w-full items-center justify-between rounded-lg bg-slate-50 px-3 text-xs font-semibold text-slate-600">
        Semester 1 · 2026 <ChevronDown size={14} />
      </button>
      
      {loading ? (
        <div className="flex items-center justify-center py-8">
          <div className="text-sm text-slate-400">Loading courses...</div>
        </div>
      ) : courses.length === 0 ? (
        <div className="flex items-center justify-center py-8">
          <div className="text-center">
            <p className="text-sm text-slate-500">No courses found</p>
            <p className="mt-1 text-xs text-slate-400">Create your first course</p>
          </div>
        </div>
      ) : (
        <div className="grid gap-1">
          {courses.map((item) => {
            const Icon = defaultCourseIcon[item.code] || Grid2X2
            const isSelected = selectedCourseCode === item.code
            return (
              <button 
                key={item.code} 
                className={cn(
                  'rounded-xl p-3 text-left transition',
                  isSelected 
                    ? 'bg-blue-50 ring-1 ring-blue-200' 
                    : 'hover:bg-slate-50'
                )}
                onClick={() => {
                  setSelectedCourseCode(item.code)
                  onSelectCourse?.({
                    id: item.id,
                    code: item.code,
                    name: item.name,
                    lecturerName: item.lecturerName,
                    imageUrl: item.imageUrl,
                    backgroundKey: item.backgroundKey,
                    iconKey: item.iconKey
                  })
                }}
              >
                <div className="flex gap-3">
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-white text-blue-600 shadow-sm">
                    <Icon size={15} />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-[11px] font-bold text-blue-600">{item.code}</span>
                    <span className="block text-xs font-semibold text-slate-700">{item.name}</span>
                    <span className="mt-1 block text-[10px] text-slate-400">
                      {item.lecturerName}
                    </span>
                  </span>
                </div>
              </button>
            )
          })}
        </div>
      )}
    </aside>
  )
}
