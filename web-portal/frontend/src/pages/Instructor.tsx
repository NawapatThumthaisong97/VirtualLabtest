/**
 * Instructor Course Management Page - Clean Architecture
 * Refactored into smaller components
 */
import { useState } from 'react'
import { ChevronRight, Plus, Bell, LayoutDashboard, FlaskConical, Users } from 'lucide-react'
import { cn } from '../lib/utils'
import CreateCourseModal from '../components/CreateCourseModal'
import { coursesService } from '../services/courses'
import type { CreateCoursePayload } from '../services/courses'
import { primary } from '../components/instructor/styles'
import type { Tab, Course } from '../components/instructor/types'
import CourseSidebar from '../components/instructor/CourseSidebar'
import OverviewTab from '../components/instructor/OverviewTab'
import AnnouncementTab from '../components/instructor/AnnouncementTab'
import LabsTab from '../components/instructor/LabsTab'
import StudentsTab from '../components/instructor/StudentsTab'

const cover = 'https://hebbkx1anhila5yf.public.blob.vercel-storage.com/Instructor%20course%20management-EDmVCANJIrpdDLi4ll0ac5XLjdxQ1K.png'

export default function InstructorPage() {
  const [activeTab, setActiveTab] = useState<Tab>('overview')
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [course, setCourse] = useState<Course>({
    code: 'CS204',
    name: 'Data Structures & Algorithms',
    lecturer_name: 'Dr. Narin Sutham',
    image_url: cover,
    background_key: 'bg-grid-blue',
    icon_key: 'binary-tree'
  })
  
  const tabs: { id: Tab; label: string; icon: React.ComponentType<{ size?: number; className?: string }> }[] = [
    { id: 'overview', label: 'Course CRUD', icon: LayoutDashboard },
    { id: 'announcement', label: 'Announcements', icon: Bell },
    { id: 'labs', label: 'Labs', icon: FlaskConical },
    { id: 'students', label: 'Enrolled students', icon: Users }
  ]

  const handleCreateCourse = async (data: { 
    code: string
    name: string
    lecturerName: string
    backgroundKey?: string
    iconKey?: string
  }) => {
    try {
      // TODO: Get actual user ID from auth context
      const userId = '00000000-0000-0000-0000-000000000000' // Placeholder
      
      const payload: CreateCoursePayload = {
        code: data.code,
        name: data.name,
        lecturerName: data.lecturerName,
        backgroundKey: data.backgroundKey as any || null,
        iconKey: data.iconKey as any || null,
        createdBy: userId,
      }

      await coursesService.create(payload)
      
      // TODO: Refresh course list or show success message
      alert('Course created successfully!')
    } catch (error) {
      console.error('Failed to create course:', error)
      alert('Failed to create course. Please try again.')
    }
  }
  
  return (
    <>
      {/* Create Course Modal */}
      <CreateCourseModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onSubmit={handleCreateCourse}
      />
      
      {/* Main Content */}
      <div className="bg-[#f7f9fc] min-h-screen">
        <div className="mx-auto max-w-[1440px] px-5 py-8 lg:px-14">
          {/* Breadcrumb & Page Header */}
          <div className="mb-7">
            <div className="mb-4 flex items-center gap-2 text-xs text-slate-500">
              <span>Instructor workspace</span>
              <ChevronRight size={14} />
              <span className="font-semibold text-slate-700">Courses</span>
            </div>
            
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <h1 className="text-3xl font-semibold tracking-tight text-slate-900">
                  Course management
                </h1>
                <p className="mt-2 text-sm text-slate-500">
                  Create, edit, and manage everything for {course.code} from one focused workspace.
                </p>
              </div>
              <div className="flex gap-3">
                <button className={primary} onClick={() => setIsCreateModalOpen(true)}>
                  <Plus size={16} /> Create course
                </button>
              </div>
            </div>
          </div>
          
          {/* Two Column Layout */}
          <div className="grid gap-6 lg:grid-cols-[250px_1fr]">
            {/* Sidebar */}
            <CourseSidebar onCreateCourse={() => setIsCreateModalOpen(true)} />
            
            {/* Main Content Area */}
            <div>
              {/* Tab Navigation */}
              <div className="mb-5 flex gap-1 overflow-x-auto rounded-xl border border-slate-200 bg-white p-1 shadow-sm">
                {tabs.map(({ id, label, icon: Icon }) => (
                  <button 
                    key={id} 
                    onClick={() => setActiveTab(id)} 
                    className={cn(
                      'inline-flex h-10 shrink-0 items-center gap-2 rounded-lg px-4 text-sm font-semibold transition',
                      activeTab === id 
                        ? 'bg-blue-600 text-white shadow-sm' 
                        : 'text-slate-500 hover:bg-slate-50 hover:text-slate-800'
                    )}
                  >
                    <Icon size={15} />
                    {label}
                  </button>
                ))}
              </div>
              
              {/* Tab Content */}
              {activeTab === 'overview' && (
                <OverviewTab course={course} setCourse={setCourse} />
              )}
              {activeTab === 'announcement' && <AnnouncementTab />}
              {activeTab === 'labs' && <LabsTab />}
              {activeTab === 'students' && <StudentsTab />}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
