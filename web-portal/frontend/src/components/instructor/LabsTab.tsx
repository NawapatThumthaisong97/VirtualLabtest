import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Check, FlaskConical, Plus } from 'lucide-react'
import { cn } from '../../lib/utils'
import Card from './Card'
import SectionHeader from './SectionHeader'
import { primary, secondary } from './styles'
import LabForm from './LabForm'

const labs = [
  ['Lab 01 — Stack & Queue Visualizer', 'Interactive coding lab', '44 / 48', '2 Oct', 'Published'], 
  ['Lab 02 — Linked List Operations', 'Guided implementation', '31 / 48', '9 Oct', 'Published'], 
  ['Lab 03 — Binary Search Tree', 'Graded challenge', 'Not open', '16 Oct', 'Draft']
]

export default function LabsTab() {
  const [isCreating, setIsCreating] = useState(false)
  const [saved, setSaved] = useState(false)

  const handleSubmit = (data: any) => {
    console.log('Lab data:', data)
    setSaved(true)
    setIsCreating(false)
  }

  return (
    <>
      <Card>
        <SectionHeader 
          icon={FlaskConical} 
          title="Labs" 
          description="5 labs · create and configure hands-on learning activities" 
          action={
            <button 
              className={primary} 
              onClick={() => { 
                setIsCreating(true)
                setSaved(false) 
              }}
            >
              <Plus size={16} /> Create lab
            </button>
          } 
        />
        
        {saved && (
          <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700">
            Lab draft created successfully.
          </div>
        )}
        
        <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
          {[['4', 'Published labs'], ['82%', 'Avg. completion'], ['1', 'Drafts to review']].map(([v, l]) => (
            <div key={l} className="rounded-xl bg-blue-50 px-4 py-3">
              <p className="text-xl font-bold">{v}</p>
              <p className="text-[11px] text-slate-500">{l}</p>
            </div>
          ))}
        </div>
        
        <div className="mt-5 overflow-hidden rounded-xl border border-slate-200">
          {labs.map((item) => (
            <div 
              key={item[0]} 
              className="grid grid-cols-[1fr_100px_75px_90px] items-center gap-3 border-b border-slate-200 px-4 py-3 text-xs last:border-0"
            >
              <div>
                <button 
                  className="text-left font-semibold text-blue-700 hover:text-blue-900 hover:underline" 
                  onClick={() => { 
                    setIsCreating(true)
                    setSaved(false)
                  }}
                >
                  {item[0]}
                </button>
                <p className="text-[11px] text-slate-400">{item[1]}</p>
              </div>
              <span>{item[2]}</span>
              <span>{item[3]}</span>
              <span className="w-fit rounded-full bg-emerald-50 px-2 py-1 text-[10px] font-bold text-emerald-700">
                {item[4]}
              </span>
            </div>
          ))}
        </div>
      </Card>
      
      {isCreating && (
        <LabForm
          onSubmit={handleSubmit}
          onCancel={() => setIsCreating(false)}
        />
      )}
    </>
  )
}
