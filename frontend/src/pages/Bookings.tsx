import { useCallback, useEffect, useMemo, useState } from 'react'
import { CalendarDays, Filter, Plus, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { MarketBadge, StatusBadge } from '@/components/ui/Badge'
import { Input, Label, Select } from '@/components/ui/Field'
import { EmptyState, Skeleton } from '@/components/ui/Skeleton'
import { useToast } from '@/components/ui/Toast'
import { NewBookingModal } from '@/components/NewBookingModal'
import { RescheduleModal } from '@/components/RescheduleModal'
import { api } from '@/lib/api'
import { MARKETS, STATUSES, type Booking, type BookingStatus } from '@/lib/types'
import { formatDate, formatTime, toISODate } from '@/lib/utils'

function startOfWeek(d: Date) {
  const copy = new Date(d)
  copy.setDate(copy.getDate() - ((copy.getDay() + 6) % 7))
  return copy
}

export function Bookings() {
  const { notify } = useToast()
  const [bookings, setBookings] = useState<Booking[] | null>(null)
  const [from, setFrom] = useState(toISODate(startOfWeek(new Date())))
  const [to, setTo] = useState(() => {
    const d = startOfWeek(new Date())
    d.setDate(d.getDate() + 13)
    return toISODate(d)
  })
  const [market, setMarket] = useState('')
  const [status, setStatus] = useState('')
  const [detailer, setDetailer] = useState('')
  const [creating, setCreating] = useState(false)
  const [rescheduling, setRescheduling] = useState<Booking | null>(null)

  const load = useCallback(() => {
    setBookings(null)
    api
      .bookings({
        date_from: from ? `${from}T00:00:00Z` : undefined,
        date_to: to ? `${to}T23:59:59Z` : undefined,
        market: market || undefined,
        status: status || undefined,
        detailer: detailer || undefined,
      })
      .then(setBookings)
      .catch((e) => {
        notify('error', e.message)
        setBookings([])
      })
  }, [from, to, market, status, detailer, notify])

  useEffect(load, [load])

  // Group by day so the list reads like a calendar rather than a flat table.
  const days = useMemo(() => {
    if (!bookings) return []
    const map = new Map<string, Booking[]>()
    for (const b of bookings) {
      const key = b.starts_at.slice(0, 10)
      map.set(key, [...(map.get(key) ?? []), b])
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [bookings])

  async function changeStatus(b: Booking, next: BookingStatus) {
    try {
      await api.setStatus(b.id, next)
      notify('success', `Marked ${next}.`)
      load()
    } catch (e) {
      notify('error', e instanceof Error ? e.message : 'Update failed')
    }
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader
          title={
            <span className="flex items-center gap-2">
              <Filter className="h-3.5 w-3.5" /> Filters
            </span>
          }
          action={
            <Button size="sm" onClick={() => setCreating(true)}>
              <Plus className="h-3.5 w-3.5" /> New booking
            </Button>
          }
        />
        <div className="grid gap-3 p-5 sm:grid-cols-2 lg:grid-cols-5">
          <div>
            <Label htmlFor="from">From</Label>
            <Input id="from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          </div>
          <div>
            <Label htmlFor="to">To</Label>
            <Input id="to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
          </div>
          <div>
            <Label htmlFor="market">Market</Label>
            <Select id="market" value={market} onChange={(e) => setMarket(e.target.value)}>
              <option value="">All markets</option>
              {MARKETS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label htmlFor="status">Status</Label>
            <Select id="status" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">Any status</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label htmlFor="detailer">Detailer</Label>
            <Input
              id="detailer"
              value={detailer}
              placeholder="Any"
              onChange={(e) => setDetailer(e.target.value)}
            />
          </div>
        </div>
      </Card>

      {bookings === null ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : days.length === 0 ? (
        <Card>
          <EmptyState
            icon={<CalendarDays className="h-6 w-6" />}
            title="No bookings in this range"
            description="Widen the date range, clear the filters, or add one manually."
            action={
              <Button size="sm" variant="secondary" onClick={() => setCreating(true)}>
                <Plus className="h-3.5 w-3.5" /> New booking
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="space-y-4">
          {days.map(([day, list]) => (
            <Card key={day} className="animate-fade-up overflow-hidden">
              <CardHeader
                title={formatDate(`${day}T12:00:00Z`)}
                subtitle={`${list.length} appointment${list.length === 1 ? '' : 's'}`}
              />
              <ul className="divide-y divide-[rgb(var(--border))]">
                {list.map((b) => (
                  <li
                    key={b.id}
                    className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3.5 transition-colors hover:bg-[rgb(var(--bg-subtle))]"
                  >
                    <div className="w-24 shrink-0 tabular-nums">
                      <p className="text-sm font-medium">{formatTime(b.starts_at)}</p>
                      <p className="text-[11px] text-muted">{formatTime(b.ends_at)}</p>
                    </div>

                    <div className="min-w-[10rem] flex-1">
                      <p className="text-sm font-medium">{b.customer.name}</p>
                      <p className="text-xs text-muted">
                        {b.customer.phone}
                        {b.vehicle && ` · ${b.vehicle}`}
                        {b.detailer && ` · ${b.detailer}`}
                      </p>
                    </div>

                    <div className="flex shrink-0 items-center gap-1.5">
                      <MarketBadge market={b.market} />
                      <StatusBadge status={b.status} />
                      {b.source === 'voice' && (
                        <span className="rounded-full bg-[rgb(var(--bg-subtle))] px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted ring-1 ring-inset ring-[rgb(var(--border))]">
                          voice
                        </span>
                      )}
                    </div>

                    <div className="flex shrink-0 items-center gap-1.5">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setRescheduling(b)}
                        disabled={b.status === 'cancelled'}
                      >
                        <RotateCcw className="h-3.5 w-3.5" /> Move
                      </Button>
                      <Select
                        aria-label="Change status"
                        className="h-8 w-[7.5rem] text-xs"
                        value={b.status}
                        onChange={(e) => changeStatus(b, e.target.value as BookingStatus)}
                      >
                        {STATUSES.map((s) => (
                          <option key={s} value={s}>
                            {s}
                          </option>
                        ))}
                      </Select>
                    </div>
                  </li>
                ))}
              </ul>
            </Card>
          ))}
        </div>
      )}

      <NewBookingModal
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={() => {
          setCreating(false)
          load()
        }}
      />
      <RescheduleModal
        booking={rescheduling}
        onClose={() => setRescheduling(null)}
        onDone={() => {
          setRescheduling(null)
          load()
        }}
      />
    </div>
  )
}
