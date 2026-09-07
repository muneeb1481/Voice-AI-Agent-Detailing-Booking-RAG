import { cn } from '@/lib/utils'
import type { BookingStatus } from '@/lib/types'
import { stateColor } from '@/lib/usStates'

const STATUS_STYLE: Record<BookingStatus, string> = {
  scheduled: 'bg-[rgb(var(--info)/0.14)] text-[rgb(var(--info))] ring-[rgb(var(--info)/0.3)]',
  done: 'bg-[rgb(var(--ok)/0.14)] text-[rgb(var(--ok))] ring-[rgb(var(--ok)/0.3)]',
  rescheduled: 'bg-[rgb(var(--warn)/0.14)] text-[rgb(var(--warn))] ring-[rgb(var(--warn)/0.3)]',
  cancelled: 'bg-[rgb(var(--danger)/0.14)] text-[rgb(var(--danger))] ring-[rgb(var(--danger)/0.3)]',
}

const base =
  'inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium capitalize ring-1 ring-inset'

export function StatusBadge({ status }: { status: BookingStatus }) {
  return <span className={cn(base, STATUS_STYLE[status])}>{status}</span>
}

export function StateBadge({ state }: { state: string | null }) {
  if (!state) {
    return <span className={cn(base, 'bg-[rgb(var(--bg-subtle))] text-muted ring-[rgb(var(--border))]')}>—</span>
  }
  const color = stateColor(state)
  return (
    <span
      className={base}
      style={{
        backgroundColor: `color-mix(in srgb, ${color} 16%, transparent)`,
        color,
        boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${color} 35%, transparent)`,
      }}
    >
      {state}
    </span>
  )
}

const SOURCE_STYLE: Record<string, string> = {
  voice: 'bg-[rgb(var(--accent)/0.14)] text-[rgb(var(--accent))] ring-[rgb(var(--accent)/0.3)]',
  admin: 'bg-[rgb(var(--bg-subtle))] text-muted ring-[rgb(var(--border))]',
  parser: 'bg-[rgb(var(--ok)/0.14)] text-[rgb(var(--ok))] ring-[rgb(var(--ok)/0.3)]',
}

export function SourceBadge({ source }: { source: string }) {
  return (
    <span
      className={cn(
        base,
        'uppercase tracking-wide',
        SOURCE_STYLE[source] ?? SOURCE_STYLE.admin,
      )}
    >
      {source}
    </span>
  )
}

export function Badge({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={cn(base, 'bg-[rgb(var(--bg-subtle))] text-muted ring-[rgb(var(--border))]', className)}>
      {children}
    </span>
  )
}
