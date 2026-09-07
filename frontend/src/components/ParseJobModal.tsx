import { useState } from 'react'
import { Sparkles } from 'lucide-react'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Textarea, Label, Input } from '@/components/ui/Field'
import { useToast } from '@/components/ui/Toast'
import { api } from '@/lib/api'
import type { ParsedJob } from '@/lib/types'
import { formatMoney } from '@/lib/utils'
import { stateName } from '@/lib/usStates'

interface Props {
  open: boolean
  onClose: () => void
  onCreated: () => void
}

const EXAMPLE = `alex\n+1234567890\ntoyota corolla\n213 tn 38103\ninterior exterior\n$200`

export function ParseJobModal({ open, onClose, onCreated }: Props) {
  const { notify } = useToast()
  const [text, setText] = useState('')
  const [parsed, setParsed] = useState<ParsedJob | null>(null)
  const [parsing, setParsing] = useState(false)
  const [saving, setSaving] = useState(false)

  function reset() {
    setText('')
    setParsed(null)
  }

  function handleClose() {
    reset()
    onClose()
  }

  async function process() {
    setParsing(true)
    try {
      const result = await api.parseJob(text)
      setParsed(result)
    } catch (e) {
      notify('error', e instanceof Error ? e.message : 'Could not parse that text')
    } finally {
      setParsing(false)
    }
  }

  async function confirm() {
    if (!parsed) return
    setSaving(true)
    try {
      await api.createParsedBooking(parsed)
      notify('success', 'Job saved.')
      reset()
      onCreated()
    } catch (e) {
      notify('error', e instanceof Error ? e.message : 'Could not save job')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="Paste & parse a job"
      description="Paste a rough note from a call or walk-in — the assistant pulls out the structured fields."
      footer={
        parsed ? (
          <>
            <Button variant="ghost" onClick={reset}>
              Cancel
            </Button>
            <Button
              onClick={confirm}
              loading={saving}
              disabled={!parsed.customer_name?.trim() || !parsed.customer_phone?.trim()}
            >
              Done — save job
            </Button>
          </>
        ) : (
          <>
            <Button variant="ghost" onClick={handleClose}>
              Close
            </Button>
            <Button onClick={process} loading={parsing} disabled={!text.trim()}>
              <Sparkles className="h-3.5 w-3.5" /> Process job
            </Button>
          </>
        )
      }
    >
      {!parsed ? (
        <div>
          <Label htmlFor="raw">Raw note</Label>
          <Textarea
            id="raw"
            rows={7}
            placeholder={EXAMPLE}
            value={text}
            onChange={(e) => setText(e.target.value)}
            className="font-mono text-xs"
          />
        </div>
      ) : (
        <div className="space-y-4">
          <p className="text-xs text-muted">
            Here's what the assistant understood. Adjust anything before saving.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Name" value={parsed.customer_name} onChange={(v) => setParsed({ ...parsed, customer_name: v })} />
            <Field label="Contact" value={parsed.customer_phone} onChange={(v) => setParsed({ ...parsed, customer_phone: v })} />
            <Field label="Vehicle" value={parsed.vehicle} onChange={(v) => setParsed({ ...parsed, vehicle: v })} />
            <Field
              label="State"
              value={parsed.state ? stateName(parsed.state) : null}
              onChange={() => {}}
              readOnly
            />
            <Field label="ZIP" value={parsed.zip_code} onChange={(v) => setParsed({ ...parsed, zip_code: v })} />
            <Field label="Address" value={parsed.address} onChange={(v) => setParsed({ ...parsed, address: v })} />
            <Field label="Service" value={parsed.service_label} onChange={(v) => setParsed({ ...parsed, service_label: v })} />
            <div>
              <Label htmlFor="date">Date</Label>
              <Input
                id="date"
                type="date"
                value={parsed.starts_at ? parsed.starts_at.slice(0, 10) : ''}
                onChange={(e) => {
                  const time = parsed.starts_at ? parsed.starts_at.slice(11, 16) : '10:00'
                  setParsed({
                    ...parsed,
                    starts_at: e.target.value
                      ? new Date(`${e.target.value}T${time}:00`).toISOString()
                      : null,
                  })
                }}
              />
              <p className="mt-1 text-[11px] text-muted">
                {parsed.starts_at ? 'Detected/edited' : 'Not mentioned — leave blank to log without a scheduled time'}
              </p>
            </div>
            <div>
              <Label htmlFor="time">Time</Label>
              <Input
                id="time"
                type="time"
                disabled={!parsed.starts_at}
                value={parsed.starts_at ? parsed.starts_at.slice(11, 16) : ''}
                onChange={(e) => {
                  if (!parsed.starts_at) return
                  const date = parsed.starts_at.slice(0, 10)
                  setParsed({
                    ...parsed,
                    starts_at: new Date(`${date}T${e.target.value}:00`).toISOString(),
                  })
                }}
              />
            </div>
            <div>
              <Label htmlFor="price">Price</Label>
              <Input
                id="price"
                type="number"
                min={0}
                step={1}
                value={parsed.price_cents != null ? (parsed.price_cents / 100).toFixed(2) : ''}
                placeholder="Not detected"
                onChange={(e) =>
                  setParsed({
                    ...parsed,
                    price_cents: e.target.value === '' ? null : Math.round(Number(e.target.value) * 100),
                  })
                }
              />
              {parsed.price_cents != null && (
                <p className="mt-1 text-[11px] text-muted">{formatMoney(parsed.price_cents)}</p>
              )}
            </div>
          </div>
          {parsed.notes && (
            <div>
              <Label htmlFor="notes">Notes</Label>
              <Textarea
                id="notes"
                value={parsed.notes}
                onChange={(e) => setParsed({ ...parsed, notes: e.target.value })}
              />
            </div>
          )}
          {!parsed.customer_name || !parsed.customer_phone ? (
            <p className="rounded-lg bg-[rgb(var(--warn)/0.12)] px-3 py-2 text-xs text-[rgb(var(--warn))]">
              Name and contact are required to save — fill them in above.
            </p>
          ) : null}
        </div>
      )}
    </Modal>
  )
}

function Field({
  label,
  value,
  onChange,
  readOnly,
}: {
  label: string
  value: string | null
  onChange: (v: string) => void
  readOnly?: boolean
}) {
  return (
    <div>
      <Label htmlFor={label}>{label}</Label>
      <Input
        id={label}
        value={value ?? ''}
        readOnly={readOnly}
        placeholder="Not detected"
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}
