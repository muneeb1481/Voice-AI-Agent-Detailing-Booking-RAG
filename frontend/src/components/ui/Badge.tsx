import { cn } from '@/lib/utils'
import type { BookingStatus, Market } from '@/lib/types'

const STATUS_STYLE: Record<BookingStatus, string> = {
  scheduled: 'bg-[rgb(var(--info)/0.14)] text-[rgb(var(--info))] ring-[rgb(var(--info)/0.3)]',
  done: 'bg-[rgb(var(--ok)/0.14)] text-[rgb(var(--ok))] ring-[rgb(var(--ok)/0.3)]',
  rescheduled: 'bg-[rgb(var(--warn)/0.14)] text-[rgb(var(--warn))] ring-[rgb(var(--warn)/0.3)]',
  cancelled: 'bg-[rgb(var(--danger)/0.14)] text-[rgb(var(--danger))] ring-[rgb(var(--danger)/0.3)]',
}

const MARKET_STYLE: Record<Market, string> = {
  memphis: 'bg-[rgb(var(--memphis)/0.14)] text-[rgb(var(--memphis))] ring-[rgb(var(--memphis)/0.3)]',
  nashville:
    'bg-[rgb(var(--nashville)/0.14)] text-[rgb(var(--nashville))] ring-[rgb(var(--nashville)/0.3)]',
  louisville:
    'bg-[rgb(var(--louisville)/0.14)] text-[rgb(var(--louisville))] ring-[rgb(var(--louisville)/0.3)]',
}

const base =
  'inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium capitalize ring-1 ring-inset'

export function StatusBadge({ status }: { status: BookingStatus }) {
  return <span className={cn(base, STATUS_STYLE[status])}>{status}</span>
}

export function MarketBadge({ market }: { market: Market }) {
  return <span className={cn(base, MARKET_STYLE[market])}>{market}</span>
}

export function Badge({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={cn(base, 'bg-[rgb(var(--bg-subtle))] text-muted ring-[rgb(var(--border))]', className)}>
      {children}
    </span>
  )
}
