interface FormFieldProps {
  label: string
  value: string
  onChange?: (value: string) => void
}

export default function FormField({ label, value, onChange }: FormFieldProps) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-semibold text-slate-500">{label}</span>
      <input 
        value={value} 
        onChange={onChange ? (event) => onChange(event.target.value) : undefined} 
        readOnly={!onChange} 
        className="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm text-slate-700 outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100" 
      />
    </label>
  )
}
