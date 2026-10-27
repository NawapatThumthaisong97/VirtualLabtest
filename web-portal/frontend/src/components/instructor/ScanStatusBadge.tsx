import { CheckCircle2, CircleDashed, Clock, Loader2, ShieldAlert, XCircle } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { LabImage } from '../../services/labImage'

type Tone = 'emerald' | 'amber' | 'blue' | 'red' | 'slate'

const TONES: Record<Tone, string> = {
  emerald: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  amber: 'bg-amber-50 text-amber-700 ring-amber-200',
  blue: 'bg-blue-50 text-blue-700 ring-blue-200',
  red: 'bg-red-50 text-red-700 ring-red-200',
  slate: 'bg-slate-100 text-slate-600 ring-slate-200',
}

/** สถานะเดียวที่อาจารย์ต้องรู้: รวม status (approve แล้วไหม) กับ scanStatus (สแกนถึงไหน) */
export function describeImageState(image: LabImage): {
  label: string
  tone: Tone
  icon: React.ComponentType<{ size?: number; className?: string }>
  spin?: boolean
} {
  if (image.status === 'approved') return { label: 'Ready', tone: 'emerald', icon: CheckCircle2 }
  if (image.status === 'rejected') return { label: 'Rejected', tone: 'red', icon: XCircle }
  switch (image.scanStatus) {
    case 'not_started':
      return { label: 'Waiting for upload', tone: 'slate', icon: CircleDashed }
    case 'queued':
      return { label: 'Queued for scan', tone: 'amber', icon: Clock }
    case 'running':
      return { label: 'Scanning', tone: 'blue', icon: Loader2, spin: true }
    case 'passed':
      return { label: 'Passed, approving', tone: 'blue', icon: Loader2, spin: true }
    case 'failed':
      return { label: 'Failed scan', tone: 'red', icon: ShieldAlert }
    case 'error':
      return { label: 'Scan error', tone: 'red', icon: XCircle }
  }
}

export default function ScanStatusBadge({ image, className }: { image: LabImage; className?: string }) {
  const { label, tone, icon: Icon, spin } = describeImageState(image)
  return (
    <span
      className={cn(
        'inline-flex w-fit items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-bold ring-1 ring-inset',
        TONES[tone],
        className,
      )}
    >
      <Icon size={12} className={cn(spin && 'animate-spin')} aria-hidden />
      {label}
    </span>
  )
}
