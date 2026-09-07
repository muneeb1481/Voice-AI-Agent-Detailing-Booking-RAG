import { useEffect, useState, type FormEvent } from 'react'
import { Trash2, UserPlus } from 'lucide-react'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Field'
import { EmptyState } from '@/components/ui/Skeleton'
import { useToast } from '@/components/ui/Toast'
import { api } from '@/lib/api'
import type { Detailer } from '@/lib/types'

interface Props {
  open: boolean
  onClose: () => void
  /** Called after any add/remove so callers holding their own detailer list can refresh. */
  onChanged: () => void
}

export function DetailerManagerModal({ open, onClose, onChanged }: Props) {
  const { notify } = useToast()
  const [detailers, setDetailers] = useState<Detailer[] | null>(null)
  const [name, setName] = useState('')
  const [adding, setAdding] = useState(false)

  const load = () => api.detailers().then(setDetailers).catch(() => setDetailers([]))

  useEffect(() => {
    if (open) load()
  }, [open])

  async function add(e: FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    setAdding(true)
    try {
      await api.createDetailer(name.trim())
      setName('')
      load()
      onChanged()
    } catch (err) {
      notify('error', err instanceof Error ? err.message : 'Could not add detailer')
    } finally {
      setAdding(false)
    }
  }

  async function remove(d: Detailer) {
    try {
      await api.deleteDetailer(d.id)
      notify('success', `${d.name} removed.`)
      load()
      onChanged()
    } catch (err) {
      notify('error', err instanceof Error ? err.message : 'Could not remove detailer')
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Manage detailers"
      description="Who shows up in the assign dropdown. Removing someone here doesn't change jobs already assigned to them."
      footer={
        <Button variant="ghost" onClick={onClose}>
          Close
        </Button>
      }
    >
      <form onSubmit={add} className="mb-4 flex gap-2">
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Detailer name"
          className="flex-1"
        />
        <Button type="submit" size="sm" loading={adding} disabled={!name.trim()}>
          <UserPlus className="h-3.5 w-3.5" /> Add
        </Button>
      </form>

      {detailers === null ? null : detailers.length === 0 ? (
        <EmptyState title="No detailers yet" description="Add one above." />
      ) : (
        <ul className="divide-y divide-[rgb(var(--border))]">
          {detailers.map((d) => (
            <li key={d.id} className="flex items-center justify-between py-2 text-sm">
              {d.name}
              <Button variant="ghost" size="icon" onClick={() => remove(d)} aria-label={`Remove ${d.name}`}>
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  )
}
