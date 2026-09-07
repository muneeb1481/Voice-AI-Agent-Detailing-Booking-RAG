import { useEffect, useState } from 'react'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Input, Label } from '@/components/ui/Field'
import { Skeleton } from '@/components/ui/Skeleton'
import { useToast } from '@/components/ui/Toast'
import { api } from '@/lib/api'
import type { Booking, Slot } from '@/lib/types'
import { cn, formatTime, toISODate } from '@/lib/utils'

interface Props {
  booking: Booking | null
  onClose: () => void
  onDone: () => void
}

export function RescheduleModal({ booking, onClose, onDone }: Props) {
  const { notify } = useToast()
  const [day, setDay] = useState('')
  const [slots, setSlots] = useState<Slot[] | null>(null)
  const [picked, setPicked] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!booking) return
    setDay(toISODate(new Date(booking.starts_at)))
    setPicked(null)
  }, [booking])

  useEffect(() => {
    if (!booking || !day || !booking.state) {
      setSlots(booking && !booking.state ? [] : null)
      return
    }
    setSlots(null)
    const minutes = Math.round(
      (new Date(booking.ends_at).getTime() - new Date(booking.starts_at).getTime()) / 60000,
    )
    api
      .slots(booking.state, `${day}T00:00:00Z`, minutes)
      .then(setSlots)
      .catch(() => setSlots([]))
  }, [booking, day])

  async function save() {
    if (!booking || !picked) return
    setSaving(true)
    try {
      await api.reschedule(booking.id, picked)
      notify('success', 'Appointment moved.')
      onDone()
    } catch (e) {
      notify('error', e instanceof Error ? e.message : 'Could not reschedule')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={!!booking}
      onClose={onClose}
      title="Reschedule appointment"
      description={
        booking
          ? `${booking.customer.name}${booking.state ? ` · ${booking.state}` : ''} · currently ${formatTime(booking.starts_at)}`
          : undefined
      }
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={save} loading={saving} disabled={!picked}>
            Move appointment
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div>
          <Label htmlFor="day">Day</Label>
          <Input id="day" type="date" value={day} onChange={(e) => setDay(e.target.value)} />
        </div>

        <div>
          <Label>Open slots</Label>
          {slots === null ? (
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="h-9" />
              ))}
            </div>
          ) : slots.length === 0 ? (
            <p className="rounded-lg border border-token bg-[rgb(var(--bg-subtle))] px-3 py-6 text-center text-xs text-muted">
              {booking && !booking.state
                ? 'This job has no state set, so slot availability cannot be checked. Pick a time directly with the customer.'
                : `Nothing open that day in ${booking?.state}. Try another date.`}
            </p>
          ) : (
            <div className="scroll-thin grid max-h-64 grid-cols-3 gap-2 overflow-y-auto sm:grid-cols-4">
              {slots.map((s) => (
                <button
                  key={s.starts_at}
                  type="button"
                  onClick={() => setPicked(s.starts_at)}
                  className={cn(
                    'rounded-lg border px-2 py-2 text-xs tabular-nums transition',
                    picked === s.starts_at
                      ? 'border-transparent bg-[rgb(var(--accent))] font-medium text-[rgb(var(--accent-fg))]'
                      : 'border-token text-muted hover:border-[rgb(var(--accent))] hover:text-fg',
                  )}
                >
                  {formatTime(s.starts_at)}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </Modal>
  )
}
