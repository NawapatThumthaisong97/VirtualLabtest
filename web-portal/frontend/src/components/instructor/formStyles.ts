import { cn } from '../../lib/utils'

// สไตล์ฟอร์มที่ใช้ร่วมกันในหน้าอาจารย์ (LabForm, LabImageForm)
export const labelClass = 'mb-1.5 block text-xs font-semibold text-slate-500'

export const inputClass = (hasError: boolean) =>
  cn(
    'h-10 w-full rounded-lg border px-3 text-sm outline-none transition focus:ring-4 disabled:cursor-not-allowed disabled:opacity-60',
    hasError
      ? 'border-red-300 bg-red-50 focus:border-red-500 focus:ring-red-100'
      : 'border-slate-200 bg-slate-50 focus:border-blue-500 focus:bg-white focus:ring-blue-100',
  )

export const selectClass =
  'h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100 disabled:cursor-not-allowed disabled:opacity-60'

export const errorText = 'mt-1 text-xs text-red-600'
export const hintText = 'mt-1 text-[11px] text-slate-400'
