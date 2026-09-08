import { useEffect, useState, type FormEvent } from 'react'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Input, Label, Select, Textarea } from '@/components/ui/Field'
import { useToast } from '@/components/ui/Toast'
import { api } from '@/lib/api'
import type { AddOn, Detailer, Service } from '@/lib/types'
import { US_STATES } from '@/lib/usStates'
import { formatMoney } from '@/lib/utils'

interface Props {
  open: boolean
  detailers: Detailer[]
  onClose: () => void
  onCreated: () => void
}

const EMPTY = {
  customer_name: '',
  customer_phone: '',
  state: 'TN',
  zip_code: '',
  date: '',
  time: '10:00',
  service_id: '',
  duration_minutes: 90,
  vehicle_length_ft: '',
  discount_dollars: '',
  detailer: '',
  vehicle: '',
  address: '',
  notes: '',
}

export function NewBookingModal({ open, detailers, onClose, onCreated }: Props) {
  const { notify } = useToast()
  const [form, setForm] = useState(EMPTY)
  const [services, setServices] = useState<Service[]>([])
  const [addons, setAddons] = useState<AddOn[]>([])
  const [selectedAddonIds, setSelectedAddonIds] = useState<string[]>([])
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) {
      setForm(EMPTY)
      setSelectedAddonIds([])
      api.services().then(setServices).catch(() => setServices([]))
      api.addons().then(setAddons).catch(() => setAddons([]))
    }
  }, [open])

  function set<K extends keyof typeof EMPTY>(key: K, value: (typeof EMPTY)[K]) {
    setForm((f) => ({ ...f, [key]: value }))
  }

  function toggleAddon(id: string) {
    setSelectedAddonIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  }

  const selectedService = services.find((s) => s.id === form.service_id)
  const isLengthBased = selectedService?.price_per_foot_cents != null

  async function submit(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      // The local wall-clock the admin typed, sent as an explicit instant.
      const startsAt = new Date(`${form.date}T${form.time}:00`).toISOString()
      await api.createBooking({
        customer_name: form.customer_name,
        customer_phone: form.customer_phone,
        state: form.state,
        zip_code: form.zip_code,
        starts_at: startsAt,
        service_id: form.service_id || null,
        duration_minutes: Number(form.duration_minutes),
        addon_ids: selectedAddonIds,
        vehicle_length_ft: form.vehicle_length_ft ? Number(form.vehicle_length_ft) : null,
        discount_cents: form.discount_dollars ? Math.round(Number(form.discount_dollars) * 100) : null,
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

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <Label htmlFor="st">State</Label>
            <Select id="st" value={form.state} onChange={(e) => set('state', e.target.value)}>
              {US_STATES.map((s) => (
                <option key={s.code} value={s.code}>
                  {s.name}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label htmlFor="zip">ZIP code</Label>
            <Input
              id="zip"
              required
              placeholder="38103"
              pattern="\d{5}(-\d{4})?"
              value={form.zip_code}
              onChange={(e) => set('zip_code', e.target.value)}
            />
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
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
                  {s.name}
                </option>
              ))}
            </Select>
            <p className="mt-1 text-[11px] text-muted">
              Price depends on vehicle type — computed automatically when saved.
            </p>
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

        {isLengthBased && (
          <div>
            <Label htmlFor="length">Vehicle length (feet)</Label>
            <Input
              id="length"
              type="number"
              min={1}
              step={1}
              required
              placeholder="30"
              value={form.vehicle_length_ft}
              onChange={(e) => set('vehicle_length_ft', e.target.value)}
            />
            <p className="mt-1 text-[11px] text-muted">
              {selectedService?.name} is priced per foot — required to compute the price.
            </p>
          </div>
        )}

        {addons.length > 0 && (
          <div>
            <Label>Add-ons</Label>
            <div className="grid gap-2 sm:grid-cols-2">
              {addons.map((a) => (
                <label
                  key={a.id}
                  className="flex items-center gap-2 rounded-lg border border-token bg-[rgb(var(--bg-subtle))] px-3 py-2 text-xs"
                >
                  <input
                    type="checkbox"
                    checked={selectedAddonIds.includes(a.id)}
                    onChange={() => toggleAddon(a.id)}
                    className="h-3.5 w-3.5"
                  />
                  <span className="flex-1">{a.name}</span>
                  <span className="text-muted">{formatMoney(a.price_cents)}</span>
                </label>
              ))}
            </div>
          </div>
        )}

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
            <Select id="det" value={form.detailer} onChange={(e) => set('detailer', e.target.value)}>
              <option value="">Unassigned</option>
              {detailers.map((d) => (
                <option key={d.id} value={d.name}>
                  {d.name}
                </option>
              ))}
            </Select>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <Label htmlFor="addr">Service address</Label>
            <Input
              id="addr"
              value={form.address}
              onChange={(e) => set('address', e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="discount">Discount ($)</Label>
            <Input
              id="discount"
              type="number"
              min={0}
              step={1}
              placeholder="0"
              value={form.discount_dollars}
              onChange={(e) => set('discount_dollars', e.target.value)}
            />
            <p className="mt-1 text-[11px] text-muted">
              Clamped server-side to the service's price floor.
            </p>
          </div>
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
