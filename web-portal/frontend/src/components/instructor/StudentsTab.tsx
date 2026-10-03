import { ChevronDown, MoreHorizontal, Search, Users } from 'lucide-react'
import Card from './Card'
import SectionHeader from './SectionHeader'
import { iconButton, secondary } from './styles'

const students = [
  ['AM', 'Anya Mehta', 'anya.m@vlab.ac.th', '66100421', '01', '12 Aug 2026', 'Active'], 
  ['KC', 'Krit Chaiyasit', 'krit.c@vlab.ac.th', '66100436', '01', '12 Aug 2026', 'Active'], 
  ['PL', 'Pimchanok Lertchai', 'pimchanok.l@vlab.ac.th', '66100502', '02', '13 Aug 2026', 'Active'], 
  ['NR', 'Napat Rattanakul', 'napat.r@vlab.ac.th', '66100527', '02', '14 Aug 2026', 'At risk'], 
  ['TS', 'Tara Somboon', 'tara.s@vlab.ac.th', '66100611', '02', '18 Aug 2026', 'Invited']
]

export default function StudentsTab() {
  return (
    <Card>
      <SectionHeader 
        icon={Users} 
        title="Enrolled students" 
        description="48 students across 2 sections"
      />
      
      <div className="mt-5 flex flex-wrap gap-3">
        <label className="relative min-w-56 flex-1">
          <Search className="absolute left-3 top-3 text-slate-400" size={16} />
          <input 
            className="h-10 w-full rounded-lg border border-slate-200 bg-white pl-9 text-sm outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" 
            placeholder="Search name, ID, or email" 
          />
        </label>
        <button className={secondary}>
          All sections <ChevronDown size={15} />
        </button>
      </div>
      
      <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full min-w-[700px] text-left text-xs">
          <thead className="bg-slate-50 text-[10px] font-bold uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Student</th>
              <th>Student ID</th>
              <th>Section</th>
              <th>Enrolled</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {students.map((student) => (
              <tr key={student[3]} className="border-t border-slate-200 hover:bg-slate-50">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span className="flex size-8 items-center justify-center rounded-full bg-blue-100 text-[10px] font-bold text-blue-700">
                      {student[0]}
                    </span>
                    <div>
                      <p className="font-semibold text-slate-700">{student[1]}</p>
                      <p className="text-[11px] text-slate-400">{student[2]}</p>
                    </div>
                  </div>
                </td>
                <td>{student[3]}</td>
                <td>{student[4]}</td>
                <td>{student[5]}</td>
                <td>
                  <span className="rounded-full bg-emerald-50 px-2 py-1 text-[10px] font-bold text-emerald-700">
                    {student[6]}
                  </span>
                </td>
                <td>
                  <button 
                    className={iconButton} 
                    aria-label={`More actions for ${student[1]}`}
                  >
                    <MoreHorizontal size={15} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
