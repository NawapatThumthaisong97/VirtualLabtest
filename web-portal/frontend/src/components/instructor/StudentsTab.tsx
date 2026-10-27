import { useEffect, useMemo, useState } from 'react'
import { Search, Users } from 'lucide-react'
import Card from './Card'
import SectionHeader from './SectionHeader'
import { coursesService, type EnrolledStudent } from '../../services/courses'
import { useToast } from '../../hooks/useToast'

interface StudentsTabProps {
  courseId: string
}

const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('') || '?'

const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })

export default function StudentsTab({ courseId }: StudentsTabProps) {
  const [students, setStudents] = useState<EnrolledStudent[]>([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const toast = useToast()

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    coursesService
      .getStudents(courseId)
      .then((data) => !cancelled && setStudents(data))
      .catch((error) => {
        console.error('Failed to fetch students:', error)
        if (!cancelled) {
          setStudents([])
          toast.error('Failed to load students', error?.response?.data?.detail ?? 'Please try again.')
        }
      })
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return students
    return students.filter((s) =>
      [s.name, s.email, s.studentId ?? ''].some((value) => value.toLowerCase().includes(q)),
    )
  }, [students, query])

  return (
    <Card>
      <SectionHeader
        icon={Users}
        title="Enrolled students"
        description={`${students.length} ${students.length === 1 ? 'student' : 'students'} in this course`}
      />

      <div className="mt-5 flex flex-wrap gap-3">
        <label className="relative min-w-56 flex-1">
          <span className="sr-only">Search students</span>
          <Search className="absolute left-3 top-3 text-slate-400" size={16} aria-hidden />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="h-10 w-full rounded-lg border border-slate-200 bg-white pl-9 text-sm outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
            placeholder="Search name, ID, or email"
          />
        </label>
      </div>

      {loading ? (
        <div className="mt-5 py-12 text-center text-sm text-slate-400">Loading students...</div>
      ) : filtered.length === 0 ? (
        <div className="mt-5 rounded-xl border border-dashed border-slate-300 py-12 text-center">
          <Users className="mx-auto text-slate-300" size={32} aria-hidden />
          <p className="mt-3 text-sm font-semibold text-slate-600">
            {students.length === 0 ? 'No students enrolled yet' : 'No students match your search'}
          </p>
        </div>
      ) : (
        <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200">
          <table className="w-full min-w-[600px] text-left text-xs">
            <thead className="bg-slate-50 text-[10px] font-bold uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">Student</th>
                <th>Student ID</th>
                <th>Role</th>
                <th>Enrolled</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((student) => (
                <tr key={student.id} className="border-t border-slate-200 hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="flex size-8 items-center justify-center rounded-full bg-blue-100 text-[10px] font-bold text-blue-700">
                        {initials(student.name)}
                      </span>
                      <div>
                        <p className="font-semibold text-slate-700">{student.name}</p>
                        <p className="text-[11px] text-slate-400">{student.email}</p>
                      </div>
                    </div>
                  </td>
                  <td>{student.studentId ?? '—'}</td>
                  <td>
                    <span className="rounded-full bg-emerald-50 px-2 py-1 text-[10px] font-bold uppercase text-emerald-700">
                      {student.roleInCourse}
                    </span>
                  </td>
                  <td>{formatDate(student.enrolledAt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
