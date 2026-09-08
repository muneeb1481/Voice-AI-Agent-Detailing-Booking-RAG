import { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import {
  CalendarDays,
  FileText,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquareText,
  Moon,
  PhoneCall,
  Sparkles,
  Sun,
  X,
} from 'lucide-react'
import { useAuth } from '@/context/AuthContext'
import { useTheme } from '@/context/ThemeContext'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'

const NAV = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/bookings', label: 'Bookings', icon: CalendarDays },
  { to: '/calls', label: 'Calls', icon: PhoneCall },
  { to: '/documents', label: 'Knowledge', icon: FileText },
  { to: '/playground', label: 'Agent test', icon: MessageSquareText },
]

export function Shell({ children }: { children: React.ReactNode }) {
  const { email, logout } = useAuth()
  const { theme, toggle } = useTheme()
  const [open, setOpen] = useState(false)
  const location = useLocation()

  const nav = (
    <nav className="flex flex-col gap-1">
      {NAV.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          onClick={() => setOpen(false)}
          className={({ isActive }) =>
            cn(
              'group flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
              isActive
                ? 'bg-[rgb(var(--accent)/0.12)] font-medium text-[rgb(var(--accent))]'
                : 'text-muted hover:bg-[rgb(var(--bg-subtle))] hover:text-fg',
            )
          }
        >
          <Icon className="h-4 w-4" />
          {label}
        </NavLink>
      ))}
    </nav>
  )

  return (
    <div className="aurora min-h-screen bg-app">
      {/* Sidebar — fixed on desktop, drawer on mobile */}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-token bg-panel px-4 py-5 transition-transform lg:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="mb-6 flex items-center justify-between px-1">
          <div className="flex items-center gap-2.5">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-[rgb(var(--accent))] text-[rgb(var(--accent-fg))]">
              <Sparkles className="h-4.5 w-4.5" />
            </div>
            <div className="leading-tight">
              <p className="text-sm font-semibold tracking-tight">ShinePro Detailing</p>
              <p className="text-[11px] text-muted">Voice agent console</p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={() => setOpen(false)}
            aria-label="Close menu"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        {nav}

        <div className="mt-auto space-y-3 pt-6">
          <div className="rounded-lg border border-token bg-[rgb(var(--bg-subtle))] px-3 py-2.5">
            <p className="truncate text-xs font-medium">{email}</p>
            <p className="text-[11px] text-muted">Administrator</p>
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" className="flex-1" onClick={toggle}>
              {theme === 'dark' ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
              {theme === 'dark' ? 'Light' : 'Dark'}
            </Button>
            <Button variant="ghost" size="sm" onClick={logout} aria-label="Sign out">
              <LogOut className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </aside>

      {open && (
        <div
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
          onClick={() => setOpen(false)}
          aria-hidden
        />
      )}

      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-token bg-[rgb(var(--bg)/0.8)] px-4 backdrop-blur-md lg:px-8">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={() => setOpen(true)}
            aria-label="Open menu"
          >
            <Menu className="h-4 w-4" />
          </Button>
          <h1 className="text-sm font-semibold">
            {NAV.find((n) => (n.end ? n.to === location.pathname : location.pathname.startsWith(n.to)))
              ?.label ?? 'ShinePro Detailing'}
          </h1>
        </header>
        <main className="relative z-10 mx-auto max-w-7xl px-4 py-6 lg:px-8">{children}</main>
      </div>
    </div>
  )
}
