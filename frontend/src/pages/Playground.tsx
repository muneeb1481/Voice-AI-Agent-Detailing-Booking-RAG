import { useState, type FormEvent } from 'react'
import { AlertTriangle, CheckCircle2, Send } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Card, CardBody, CardHeader } from '@/components/ui/Card'
import { Input } from '@/components/ui/Field'
import { useToast } from '@/components/ui/Toast'
import { api } from '@/lib/api'
import type { AskResponse } from '@/lib/types'

const SAMPLES = [
  'How much is a ceramic coating?',
  'Do you come to my house?',
  'How long does a full interior detail take?',
  'Do you serve customers in Texas?',
]

export function Playground() {
  const { notify } = useToast()
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState<AskResponse | null>(null)
  const [loading, setLoading] = useState(false)

  async function ask(q: string) {
    if (!q.trim()) return
    setLoading(true)
    setResult(null)
    try {
      setResult(await api.ask(q))
    } catch (e) {
      notify('error', e instanceof Error ? e.message : 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    ask(question)
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <Card>
        <CardHeader
          title="Ask the agent"
          subtitle="Hits the same retrieval endpoint the phone agent calls. Use it to check what callers will actually hear."
        />
        <CardBody className="space-y-4">
          <form onSubmit={submit} className="flex gap-2">
            <Input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="How much is a ceramic coating on an SUV?"
              className="flex-1"
            />
            <Button type="submit" loading={loading}>
              <Send className="h-4 w-4" /> Ask
            </Button>
          </form>

          <div className="flex flex-wrap gap-2">
            {SAMPLES.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => {
                  setQuestion(s)
                  ask(s)
                }}
                className="rounded-full border border-token px-3 py-1 text-xs text-muted transition hover:border-[rgb(var(--accent))] hover:text-fg"
              >
                {s}
              </button>
            ))}
          </div>
        </CardBody>
      </Card>

      {result && (
        <Card className="animate-fade-up">
          <CardHeader
            title="Answer"
            action={
              result.grounded ? (
                <span className="inline-flex items-center gap-1.5 text-xs text-[rgb(var(--ok))]">
                  <CheckCircle2 className="h-3.5 w-3.5" /> Grounded
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 text-xs text-[rgb(var(--warn))]">
                  <AlertTriangle className="h-3.5 w-3.5" /> No match — refused to guess
                </span>
              )
            }
          />
          <CardBody className="space-y-4">
            <p className="text-sm leading-relaxed">{result.answer}</p>

            {result.sources.length > 0 && (
              <div>
                <p className="mb-2 text-xs font-medium text-muted">
                  Retrieved context ({result.sources.length})
                </p>
                <ul className="space-y-2">
                  {result.sources.map((s) => (
                    <li
                      key={`${s.document_id}-${s.chunk_index}`}
                      className="rounded-lg border border-token bg-[rgb(var(--bg-subtle))] p-3"
                    >
                      <div className="mb-1.5 flex items-center justify-between gap-2">
                        <span className="truncate text-xs font-medium">{s.document_title}</span>
                        <span className="shrink-0 text-[11px] tabular-nums text-muted">
                          chunk {s.chunk_index} · score {s.score.toFixed(3)}
                        </span>
                      </div>
                      <p className="line-clamp-3 text-xs leading-relaxed text-muted">
                        {s.content}
                      </p>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardBody>
        </Card>
      )}
    </div>
  )
}
