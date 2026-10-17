import { cn } from '../../lib/utils'

interface CardProps {
  children: React.ReactNode
  className?: string
}

export default function Card({ children, className = '' }: CardProps) {
  return (
    <section className={cn('rounded-2xl border border-slate-200/80 bg-white p-5 shadow-[0_8px_30px_-20px_rgba(15,23,42,0.35)]', className)}>
      {children}
    </section>
  )
}
