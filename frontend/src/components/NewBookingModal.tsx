import { useEffect, useState, type FormEvent } from 'react'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Input, Label, Select, Textarea } from '@/components/ui/Field'
import { useToast } from '@/components/ui/Toast'
import { api } from '@/lib/api'
import { MARKETS, type Service } from '@/lib/types'
import { formatMoney } from '@/lib/utils'

interface Props {
  open: boolean
  onClose: () => void
  onCreated: () => void
}

const EMPTY = {
  customer_name: '',
  customer_phone: '',
  market: 'memphis',
  date: '',
  time: '10:00',
  service_id: '',
  duration_minutes: 90,
  detailer: '',
  vehicle: '',
  address: '',
  notes: '',
}

export function NewBookingModal({ open, onClose, onCreated }: Props) {
  const { notify } = useToast()
  const [form, setForm] = useState(EMPTY)
  const [services, setServices] = useState<Service[]>([])
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) {
      setForm(EMPTY)
      api.services().then(setServices).catch(() => setServices([]))
    }
  }, [open])

  function set<K extends keyof typeof EMPTY>(key: K, value: (typeof EMPTY)[K]) {
    setForm((f) => ({ ...f, [key]: value }))
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      // The local wall-clock the admin typed, sent as an explicit instant.
      const startsAt = new Date(`${form.date}T${form.time}:00`).toISOString()
      await api.createBooking({
        customer_name: form.customer_name,
        customer_phone: form.customer_phone,
        market: form.market,
        starts_at: startsAt,
        service_id: form.service_id || null,
        duration_minutes: Number(form.duration_minutes),
        detailer: form.detailer || null,
        vehicle: form.vehicle || null,
        address: form.address || null,
        notes: form.notes || null,
      })
      notify('success', 'Booking created.')
      onCreated()
    } catch (err) {
      notify('error', err instanceof Error ? err.message : 'Could not create booking')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New booking"
      description="Written through the same validation the voice agent uses."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button form="new-booking" type="submit" loading={saving}>
            Create booking
          </Button>
        </>
      }
    >
      <form id="new-booking" onSubmit={submit} className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <Label htmlFor="name">Customer name</Label>
            <Input
              id="name"
              required
              value={form.customer_name}
              onChange={(e) => set('customer_name', e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="phone">Phone</Label>
            <Input
              id="phone"
              required
              placeholder="+19015550142"
              value={form.customer_phone}
              onChange={(e) => set('customer_phone', e.target.value)}
            />
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <div>
            <Label htmlFor="m">Market</Label>
            <Select id="m" value={form.market} onChange={(e) => set('market', e.target.value)}>
              {MARKETS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label htmlFor="d">Date</Label>
            <Input
              id="d"
              type="date"
              required
              value={form.date}
              onChange={(e) => set('date', e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="t">Start time</Label>
            <Input
              id="t"
              type="time"
              required
              value={form.time}
              onChange={(e) => set('time', e.target.value)}
            />
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <Label htmlFor="svc">Service</Label>
            <Select
              id="svc"
              value={form.service_id}
              onChange={(e) => set('service_id', e.target.value)}
            >
              <option value="">Custom / not specified</option>
              {services.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} — {formatMoney(s.price_cents)}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label htmlFor="dur">Duration (minutes)</Label>
            <Input
              id="dur"
              type="number"
              min={15}
              max={600}
              step={15}
              disabled={!!form.service_id}
              value={form.duration_minutes}
              onChange={(e) => set('duration_minutes', Number(e.target.value))}
            />
            {form.service_id && (
              <p className="mt-1 text-[11px] text-muted">
                Taken from the selected service.
              </p>
            )}
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <Label htmlFor="veh">Vehicle</Label>
            <Input
              id="veh"
              placeholder="2019 Tacoma"
              value={form.vehicle}
              onChange={(e) => set('vehicle', e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="det">Detailer</Label>
            <Input
              id="det"
              placeholder="Unassigned"
              value={form.detailer}
              onChange={(e) => set('detailer', e.target.value)}
            />
          </div>
        </div>

        <div>
          <Label htmlFor="addr">Service address</Label>
          <Input
            id="addr"
            value={form.address}
            onChange={(e) => set('address', e.target.value)}
          />
        </div>

        <div>
          <Label htmlFor="notes">Notes</Label>
          <Textarea
            id="notes"
            value={form.notes}
            onChange={(e) => set('notes', e.target.value)}
          />
        </div>
      </form>
    </Modal>
  )
}
