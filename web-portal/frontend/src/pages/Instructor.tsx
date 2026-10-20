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
import { useToast } from '../hooks/useToast'

const cover = 'https://hebbkx1anhila5yf.public.blob.vercel-storage.com/Instructor%20course%20management-EDmVCANJIrpdDLi4ll0ac5XLjdxQ1K.png'

export default function InstructorPage() {
  const [activeTab, setActiveTab] = useState<Tab>('overview')
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [course, setCourse] = useState<Course | null>(null)
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const [loading, setLoading] = useState(false)
  const toast = useToast()

  const handleSelectCourse = async (selectedCourse: any) => {
    setLoading(true)
    try {
      // Fetch full course detail with announcements
      const courseDetail = await coursesService.getById(selectedCourse.id)
      setCourse({
        id: courseDetail.id,
        code: courseDetail.code,
        name: courseDetail.name,
        lecturer_name: courseDetail.lecturerName,
        image_url: courseDetail.imageUrl,
        background_key: courseDetail.backgroundKey,
        icon_key: courseDetail.iconKey,
        announcements: courseDetail.announcements,
      })
    } catch (error) {
      console.error('Failed to fetch course detail:', error)
      toast.error('Failed to load course', 'Unable to fetch course details. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteCourse = () => {
    // Clear selected course and refresh list
    setCourse(null)
    setRefreshTrigger(prev => prev + 1)
  }

  const refreshCourseDetail = async () => {
    if (!course) return
    try {
      const courseDetail = await coursesService.getById(course.id)
      setCourse({
        ...course,
        announcements: courseDetail.announcements,
      })
    } catch (error) {
      console.error('Failed to refresh course detail:', error)
    }
  }
  
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
      const payload: CreateCoursePayload = {
        code: data.code,
        name: data.name,
        lecturerName: data.lecturerName,
        backgroundKey: data.backgroundKey as any || null,
        iconKey: data.iconKey as any || null,
      }

      await coursesService.create(payload)
      
      // Refresh course list
      setRefreshTrigger(prev => prev + 1)
      toast.success('Course created successfully!', `${data.code} has been added to your courses.`)
    } catch (error: any) {
      console.error('Failed to create course:', error)
      
      // Handle specific error messages
      if (error.response?.status === 409) {
        toast.error('Course already exists', `A course with code "${data.code}" already exists.`)
      } else if (error.response?.data?.detail) {
        toast.error('Failed to create course', error.response.data.detail)
      } else {
        toast.error('Failed to create course', 'Please check your input and try again.')
      }
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
                  {course ? `Create, edit, and manage everything for ${course.code} from one focused workspace.` : 'Select a course from the sidebar to get started.'}
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
            <CourseSidebar 
              onCreateCourse={() => setIsCreateModalOpen(true)} 
              onSelectCourse={handleSelectCourse}
              refreshTrigger={refreshTrigger}
            />
            
            {/* Main Content Area */}
            <div>
              {loading ? (
                <div className="flex h-96 items-center justify-center rounded-2xl border border-slate-200 bg-white">
                  <div className="text-center">
                    <div className="mb-4 h-12 w-12 animate-spin rounded-full border-4 border-slate-200 border-t-blue-600 mx-auto"></div>
                    <p className="text-slate-600">Loading course details...</p>
                  </div>
                </div>
              ) : course ? (
                <>
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
                    <OverviewTab 
                      course={course} 
                      setCourse={setCourse} 
                      onDelete={handleDeleteCourse}
                    />
                  )}
                  {activeTab === 'announcement' && (
                    <AnnouncementTab 
                      announcements={course.announcements || []} 
                      courseId={course.id}
                      onUpdate={refreshCourseDetail}
                    />
                  )}
                  {activeTab === 'labs' && <LabsTab courseId={course.id} />}
                  {activeTab === 'students' && <StudentsTab />}
                </>
              ) : (
                <div className="flex h-96 items-center justify-center rounded-2xl border-2 border-dashed border-slate-200 bg-white">
                  <div className="text-center">
                    <p className="text-lg font-semibold text-slate-700">No course selected</p>
                    <p className="mt-2 text-sm text-slate-500">Please select a course from the sidebar to get started</p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
