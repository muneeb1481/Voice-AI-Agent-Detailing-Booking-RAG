import { useState, type FormEvent } from 'react'
import { Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input, Label } from '@/components/ui/Field'
import { useAuth } from '@/context/AuthContext'
import { useTheme } from '@/context/ThemeContext'
import { Moon, Sun } from 'lucide-react'

export function Login() {
  const { login } = useAuth()
  const { theme, toggle } = useTheme()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await login(email, password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign in failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="aurora grid min-h-screen place-items-center bg-app px-4">
      <Button
        variant="ghost"
        size="icon"
        onClick={toggle}
        className="absolute right-4 top-4"
        aria-label="Toggle theme"
      >
        {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
      </Button>

      <div className="relative z-10 w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="mb-3 grid h-12 w-12 place-items-center rounded-2xl bg-[rgb(var(--accent))] text-[rgb(var(--accent-fg))]">
            <Sparkles className="h-6 w-6" />
          </div>
          <h1 className="text-xl font-semibold tracking-tight">ShinePro Detailing</h1>
          <p className="mt-1 text-sm text-muted">
            Sign in to manage bookings and the agent's knowledge base.
          </p>
        </div>

        <form onSubmit={onSubmit} className="surface animate-fade-up space-y-4 p-6">
          <div>
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="admin@example.com"
            />
          </div>
          <div>
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
          </div>

          {error && (
            <p className="rounded-lg bg-[rgb(var(--danger)/0.12)] px-3 py-2 text-xs text-[rgb(var(--danger))]">
              {error}
            </p>
          )}

          <Button type="submit" loading={loading} className="w-full">
            Sign in
          </Button>
        </form>
      </div>
    </div>
  )
}
