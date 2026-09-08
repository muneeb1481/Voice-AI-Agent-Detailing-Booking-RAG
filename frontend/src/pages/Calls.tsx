import { useEffect, useState } from 'react'
import { ChevronDown, PhoneCall } from 'lucide-react'
import { Card, CardHeader } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { EmptyState, Skeleton } from '@/components/ui/Skeleton'
import { useToast } from '@/components/ui/Toast'
import { api } from '@/lib/api'
import type { CallTranscript } from '@/lib/types'
import { cn, formatDate, formatTime } from '@/lib/utils'

function formatDuration(seconds: number | null) {
  if (seconds == null) return null
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}m ${s}s`
}

export function Calls() {
  const { notify } = useToast()
  const [calls, setCalls] = useState<CallTranscript[] | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  useEffect(() => {
    api
      .callTranscripts()
      .then(setCalls)
      .catch((e) => {
        notify('error', e.message)
        setCalls([])
      })
  }, [notify])

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader
          title="Call transcripts"
          subtitle="Every finished voice call, saved by Vapi's end-of-call webhook — exactly what the agent said, not just what it booked."
        />
        {calls === null ? (
          <div className="space-y-3 p-5">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-16" />
            ))}
          </div>
        ) : calls.length === 0 ? (
          <EmptyState
            icon={<PhoneCall className="h-6 w-6" />}
            title="No calls yet"
            description="Once your Vapi assistant's Server URL is set to /api/vapi/call-ended, finished calls will show up here."
          />
        ) : (
          <ul className="divide-y divide-[rgb(var(--border))]">
            {calls.map((c) => {
              const isOpen = expanded.has(c.id)
              return (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => toggle(c.id)}
                    className="flex w-full flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3.5 text-left transition-colors hover:bg-[rgb(var(--bg-subtle))]"
                  >
                    <div className="w-24 shrink-0 tabular-nums">
                      <p className="text-sm font-medium">{formatDate(c.created_at)}</p>
                      <p className="text-[11px] text-muted">{formatTime(c.created_at)}</p>
                    </div>

                    <div className="min-w-[10rem] flex-1">
                      <p className="text-sm font-medium">{c.customer_name || c.phone || 'Unknown caller'}</p>
                      <p className="truncate text-xs text-muted">
                        {c.summary || (c.transcript ? c.transcript.slice(0, 80) + '…' : 'No summary')}
                      </p>
                    </div>

                    <div className="flex shrink-0 items-center gap-1.5">
                      {formatDuration(c.duration_seconds) && (
                        <Badge>{formatDuration(c.duration_seconds)}</Badge>
                      )}
                      {c.ended_reason && <Badge>{c.ended_reason}</Badge>}
                    </div>

                    <ChevronDown
                      className={cn(
                        'h-4 w-4 shrink-0 text-muted transition-transform',
                        isOpen && 'rotate-180',
                      )}
                    />
                  </button>

                  {isOpen && (
                    <div className="border-t border-token bg-[rgb(var(--bg-subtle))] px-5 py-4">
                      {c.phone && (
                        <p className="mb-2 text-xs text-muted">
                          <span className="font-medium text-fg">Phone:</span> {c.phone}
                        </p>
                      )}
                      {c.summary && (
                        <p className="mb-3 rounded-lg bg-[rgb(var(--panel))] px-3 py-2 text-xs">
                          <span className="font-medium">Summary:</span> {c.summary}
                        </p>
                      )}
                      {c.transcript ? (
                        <pre className="scroll-thin max-h-96 overflow-y-auto whitespace-pre-wrap rounded-lg bg-[rgb(var(--panel))] p-3 text-xs leading-relaxed">
                          {c.transcript}
                        </pre>
                      ) : (
                        <p className="text-xs text-muted">No transcript text was captured for this call.</p>
                      )}
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </Card>
    </div>
  )
}
