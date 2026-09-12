import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  CalendarDays,
  ChevronDown,
  Copy,
  Filter,
  Plus,
  RotateCcw,
  Sparkles,
  Users,
} from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { SourceBadge, StateBadge, StatusBadge } from '@/components/ui/Badge'
import { Input, Label, Select } from '@/components/ui/Field'
import { EmptyState, Skeleton } from '@/components/ui/Skeleton'
import { useToast } from '@/components/ui/Toast'
import { NewBookingModal } from '@/components/NewBookingModal'
import { RescheduleModal } from '@/components/RescheduleModal'
import { ParseJobModal } from '@/components/ParseJobModal'
import { DetailerManagerModal } from '@/components/DetailerManagerModal'
import { api } from '@/lib/api'
import { STATUSES, type Booking, type BookingStatus, type Detailer } from '@/lib/types'
import { US_STATES } from '@/lib/usStates'
import { jobSummaryText } from '@/lib/jobSummary'
import { cn, formatDate, formatMoney, formatTime, toISODate } from '@/lib/utils'

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
  const [state, setState] = useState('')
  const [status, setStatus] = useState('')
  const [detailer, setDetailer] = useState('')
  const [creating, setCreating] = useState(false)
  const [parsing, setParsing] = useState(false)
  const [managingDetailers, setManagingDetailers] = useState(false)
  const [rescheduling, setRescheduling] = useState<Booking | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [detailers, setDetailers] = useState<Detailer[]>([])

  const loadDetailers = useCallback(() => {
    api.detailers().then(setDetailers).catch(() => setDetailers([]))
  }, [])

  useEffect(loadDetailers, [loadDetailers])

  const load = useCallback(() => {
    setBookings(null)
    api
      .bookings({
        date_from: from ? `${from}T00:00:00Z` : undefined,
        date_to: to ? `${to}T23:59:59Z` : undefined,
        state: state || undefined,
        status: status || undefined,
        detailer: detailer || undefined,
      })
      .then(setBookings)
      .catch((e) => {
        notify('error', e.message)
        setBookings([])
      })
  }, [from, to, state, status, detailer, notify])

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

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  async function changeStatus(b: Booking, next: BookingStatus) {
    try {
      await api.setStatus(b.id, next)
      notify('success', `Marked ${next}.`)
      load()
    } catch (e) {
      notify('error', e instanceof Error ? e.message : 'Update failed')
    }
  }

  async function copyJob(b: Booking) {
    try {
      await navigator.clipboard.writeText(jobSummaryText(b))
      notify('success', 'Job details copied.')
    } catch {
      notify('error', 'Could not copy — your browser blocked clipboard access.')
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
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="ghost" onClick={() => setManagingDetailers(true)}>
                <Users className="h-3.5 w-3.5" /> Detailers
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setParsing(true)}>
                <Sparkles className="h-3.5 w-3.5" /> Paste & parse
              </Button>
              <Button size="sm" onClick={() => setCreating(true)}>
                <Plus className="h-3.5 w-3.5" /> New booking
              </Button>
            </div>
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
            <Label htmlFor="state">State</Label>
            <Select id="state" value={state} onChange={(e) => setState(e.target.value)}>
              <option value="">All states</option>
              {US_STATES.map((s) => (
                <option key={s.code} value={s.code}>
                  {s.name}
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
              placeholder="Search by name"
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
                {list.map((b) => {
                  const isOpen = expanded.has(b.id)
                  return (
                    <li key={b.id}>
                      <button
                        type="button"
                        onClick={() => toggle(b.id)}
                        className="flex w-full flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3.5 text-left transition-colors hover:bg-[rgb(var(--bg-subtle))]"
                      >
                        <div className="w-24 shrink-0 tabular-nums">
                          <p className="text-sm font-medium">{formatTime(b.starts_at, b.state)}</p>
                          <p className="text-[11px] text-muted">{formatTime(b.ends_at, b.state)}</p>
                        </div>

                        <div className="min-w-[10rem] flex-1">
                          <p className="text-sm font-medium">{b.customer.name}</p>
                          <p className="text-xs text-muted">
                            {b.customer.phone}
                            {b.vehicle && ` · ${b.vehicle}`}
                          </p>
                        </div>

                        <div className="flex shrink-0 items-center gap-1.5">
                          <StateBadge state={b.state} />
                          <StatusBadge status={b.status} />
                          <SourceBadge source={b.source} />
                        </div>

                        <ChevronDown
                          className={cn(
                            'h-4 w-4 shrink-0 text-muted transition-transform',
                            isOpen && 'rotate-180',
                          )}
                        />
                      </button>

                      {isOpen && (
                        <BookingDetail
                          booking={b}
                          detailers={detailers}
                          onCopy={() => copyJob(b)}
                          onMove={() => setRescheduling(b)}
                          onStatusChange={(next) => changeStatus(b, next)}
                          onDetailerSaved={load}
                        />
                      )}
                    </li>
                  )
                })}
              </ul>
            </Card>
          ))}
        </div>
      )}

      <NewBookingModal
        open={creating}
        detailers={detailers}
        onClose={() => setCreating(false)}
        onCreated={() => {
          setCreating(false)
          load()
        }}
      />
      <ParseJobModal
        open={parsing}
        onClose={() => setParsing(false)}
        onCreated={() => {
          setParsing(false)
          load()
        }}
      />
      <DetailerManagerModal
        open={managingDetailers}
        onClose={() => setManagingDetailers(false)}
        onChanged={loadDetailers}
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

function BookingDetail({
  booking: b,
  detailers,
  onCopy,
  onMove,
  onStatusChange,
  onDetailerSaved,
}: {
  booking: Booking
  detailers: Detailer[]
  onCopy: () => void
  onMove: () => void
  onStatusChange: (next: BookingStatus) => void
  onDetailerSaved: () => void
}) {
  const { notify } = useToast()
  const [detailer, setDetailerValue] = useState(b.detailer ?? '')
  const [savingDetailer, setSavingDetailer] = useState(false)

  async function saveDetailer() {
    setSavingDetailer(true)
    try {
      await api.setDetailer(b.id, detailer || null)
      notify('success', 'Detailer assigned.')
      onDetailerSaved()
    } catch (e) {
      notify('error', e instanceof Error ? e.message : 'Could not assign detailer')
    } finally {
      setSavingDetailer(false)
    }
  }

  return (
    <div className="border-t border-token bg-[rgb(var(--bg-subtle))] px-5 py-4">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <DetailField
          label="Vehicle"
          value={b.vehicle ?? '—'}
          sub={
            b.vehicle_length_ft
              ? `${b.vehicle_category ?? ''} · ${b.vehicle_length_ft} ft`.trim()
              : (b.vehicle_category ?? undefined)
          }
        />
        <DetailField label="Service" value={b.service_label ?? '—'} />
        <DetailField
          label="Price"
          value={b.price_cents != null ? formatMoney(b.price_cents) : 'Not set'}
          sub={
            b.discount_cents > 0
              ? `${formatMoney(b.original_price_cents ?? 0)} − ${formatMoney(b.discount_cents)} discount`
              : undefined
          }
        />
        <DetailField label="Address" value={b.address ?? '—'} sub={b.zip_code ?? undefined} />
      </div>

      {b.items.length > 0 && (
        <div className="mt-3 rounded-lg bg-[rgb(var(--panel))] px-3 py-2 text-xs">
          <p className="mb-1 font-medium text-muted">Extra services / add-ons</p>
          <ul className="space-y-0.5">
            {b.items.map((i) => (
              <li key={i.id} className="flex justify-between">
                <span className="capitalize">
                  {i.name}
                  <span className="text-muted"> ({i.item_type})</span>
                </span>
                <span className="tabular-nums">{formatMoney(i.price_cents)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {b.notes && (
        <p className="mt-3 rounded-lg bg-[rgb(var(--panel))] px-3 py-2 text-xs text-muted">
          {b.notes}
        </p>
      )}

      {b.status === 'cancelled' && b.cancellation_reason && (
        <p className="mt-3 rounded-lg bg-[rgb(var(--danger)/0.1)] px-3 py-2 text-xs text-[rgb(var(--danger))]">
          <span className="font-medium">Cancellation reason:</span> {b.cancellation_reason}
        </p>
      )}

      <div className="mt-4 flex flex-wrap items-end gap-3">
        <div className="w-48">
          <Label htmlFor={`detailer-${b.id}`}>Detailer</Label>
          <Select
            id={`detailer-${b.id}`}
            value={detailer}
            onChange={(e) => setDetailerValue(e.target.value)}
          >
            <option value="">Unassigned</option>
            {b.detailer && !detailers.some((d) => d.name === b.detailer) && (
              <option value={b.detailer}>{b.detailer} (removed)</option>
            )}
            {detailers.map((d) => (
              <option key={d.id} value={d.name}>
                {d.name}
              </option>
            ))}
          </Select>
        </div>
        <Button size="sm" variant="secondary" loading={savingDetailer} onClick={saveDetailer}>
          Assign
        </Button>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" onClick={onMove} disabled={b.status === 'cancelled'}>
            <RotateCcw className="h-3.5 w-3.5" /> Move
          </Button>
          <Select
            aria-label="Change status"
            className="h-8 w-[7.5rem] text-xs"
            value={b.status}
            onChange={(e) => onStatusChange(e.target.value as BookingStatus)}
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
          <Button size="sm" variant="outline" onClick={onCopy}>
            <Copy className="h-3.5 w-3.5" /> Copy
          </Button>
        </div>
      </div>
    </div>
  )
}

function DetailField({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div>
      <p className="text-[11px] font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-0.5 text-sm">{value}</p>
      {sub && <p className="text-[11px] capitalize text-muted">{sub}</p>}
    </div>
  )
}
