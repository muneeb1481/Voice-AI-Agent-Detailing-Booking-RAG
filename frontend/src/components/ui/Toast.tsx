import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { AlertCircle, CheckCircle2, X } from 'lucide-react'
import { cn } from '@/lib/utils'

type Kind = 'success' | 'error'
interface Toast {
  id: number
  kind: Kind
  message: string
}

const ToastContext = createContext<{
  notify: (kind: Kind, message: string) => void
}>({ notify: () => {} })

export const useToast = () => useContext(ToastContext)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const notify = useCallback((kind: Kind, message: string) => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t, { id, kind, message }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500)
  }, [])

  return (
    <ToastContext.Provider value={{ notify }}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-full max-w-sm flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            className={cn(
              'surface animate-fade-up pointer-events-auto flex items-start gap-3 px-4 py-3 text-sm',
              t.kind === 'error' && 'border-[rgb(var(--danger)/0.4)]',
            )}
          >
            {t.kind === 'success' ? (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[rgb(var(--ok))]" />
            ) : (
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-[rgb(var(--danger))]" />
            )}
            <span className="flex-1">{t.message}</span>
            <button
              onClick={() => setToasts((all) => all.filter((x) => x.id !== t.id))}
              className="text-muted hover:text-fg"
              aria-label="Dismiss"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
