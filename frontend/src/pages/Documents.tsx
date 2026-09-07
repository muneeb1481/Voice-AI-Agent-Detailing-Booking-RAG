import { useCallback, useEffect, useRef, useState } from 'react'
import { FileText, Trash2, Upload } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Modal } from '@/components/ui/Modal'
import { EmptyState, Skeleton } from '@/components/ui/Skeleton'
import { useToast } from '@/components/ui/Toast'
import { api } from '@/lib/api'
import type { Document } from '@/lib/types'
import { cn, formatBytes, formatDate } from '@/lib/utils'

export function Documents() {
  const { notify } = useToast()
  const [docs, setDocs] = useState<Document[] | null>(null)
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<Document | null>(null)
  const [deleting, setDeleting] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const load = useCallback(() => {
    api
      .documents()
      .then(setDocs)
      .catch((e) => {
        notify('error', e.message)
        setDocs([])
      })
  }, [notify])

  useEffect(load, [load])

  const upload = useCallback(
    async (files: FileList | null) => {
      if (!files?.length) return
      setUploading(true)
      try {
        for (const file of Array.from(files)) {
          const doc = await api.uploadDocument(file)
          notify('success', `${doc.title} indexed into ${doc.chunk_count} chunks.`)
        }
        load()
      } catch (e) {
        notify('error', e instanceof Error ? e.message : 'Upload failed')
      } finally {
        setUploading(false)
        if (inputRef.current) inputRef.current.value = ''
      }
    },
    [load, notify],
  )

  async function confirmDelete() {
    if (!pendingDelete) return
    setDeleting(true)
    try {
      await api.deleteDocument(pendingDelete.id)
      notify('success', 'Document and its embeddings removed.')
      setPendingDelete(null)
      load()
    } catch (e) {
      notify('error', e instanceof Error ? e.message : 'Delete failed')
    } finally {
      setDeleting(false)
    }
  }

  const totalChunks = docs?.reduce((sum, d) => sum + d.chunk_count, 0) ?? 0

  return (
    <div className="space-y-5">
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          upload(e.dataTransfer.files)
        }}
        className={cn(
          'surface flex flex-col items-center justify-center gap-2 border-dashed px-6 py-10 text-center transition-colors',
          dragging && 'border-[rgb(var(--accent))] bg-[rgb(var(--accent)/0.06)]',
        )}
      >
        <div className="grid h-10 w-10 place-items-center rounded-xl bg-[rgb(var(--bg-subtle))] text-muted">
          <Upload className="h-5 w-5" />
        </div>
        <p className="text-sm font-medium">Drop pricing, promo, or policy docs here</p>
        <p className="max-w-md text-xs text-muted">
          PDF or plain text, up to 5 MB. Each file is chunked with overlap, embedded, and
          stored in pgvector — the agent answers callers only from what lives here.
        </p>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.txt,.md,text/plain,application/pdf"
          multiple
          className="hidden"
          onChange={(e) => upload(e.target.files)}
        />
        <Button
          className="mt-2"
          size="sm"
          loading={uploading}
          onClick={() => inputRef.current?.click()}
        >
          Choose files
        </Button>
      </div>

      <Card>
        <CardHeader
          title="Knowledge base"
          subtitle={
            docs
              ? `${docs.length} document${docs.length === 1 ? '' : 's'} · ${totalChunks} embedded chunks`
              : 'Loading…'
          }
        />
        {docs === null ? (
          <div className="space-y-3 p-5">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-12" />
            ))}
          </div>
        ) : docs.length === 0 ? (
          <EmptyState
            icon={<FileText className="h-6 w-6" />}
            title="Nothing indexed yet"
            description="With an empty knowledge base the agent will tell callers it does not know, rather than guess a price."
          />
        ) : (
          <ul className="divide-y divide-[rgb(var(--border))]">
            {docs.map((d) => (
              <li
                key={d.id}
                className="flex items-center gap-4 px-5 py-3.5 transition-colors hover:bg-[rgb(var(--bg-subtle))]"
              >
                <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[rgb(var(--bg-subtle))] text-muted">
                  <FileText className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{d.title}</p>
                  <p className="truncate text-xs text-muted">
                    {d.filename} · {formatBytes(d.size_bytes)} · added {formatDate(d.created_at)}
                  </p>
                </div>
                <Badge>{d.chunk_count} chunks</Badge>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Delete ${d.title}`}
                  onClick={() => setPendingDelete(d)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Modal
        open={!!pendingDelete}
        onClose={() => setPendingDelete(null)}
        title="Delete document?"
        footer={
          <>
            <Button variant="ghost" onClick={() => setPendingDelete(null)}>
              Cancel
            </Button>
            <Button variant="danger" loading={deleting} onClick={confirmDelete}>
              Delete permanently
            </Button>
          </>
        }
      >
        <p className="text-sm">
          <span className="font-medium">{pendingDelete?.title}</span> and its{' '}
          {pendingDelete?.chunk_count} embedded chunks will be removed together, so the agent
          stops quoting anything in it. This cannot be undone.
        </p>
      </Modal>
    </div>
  )
}
