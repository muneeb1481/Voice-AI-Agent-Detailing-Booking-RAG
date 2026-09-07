import { Navigate, Route, Routes } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { Shell } from '@/components/Shell'
import { Login } from '@/pages/Login'
import { Dashboard } from '@/pages/Dashboard'
import { Bookings } from '@/pages/Bookings'
import { Documents } from '@/pages/Documents'
import { Playground } from '@/pages/Playground'
import { useAuth } from '@/context/AuthContext'

export default function App() {
  const { email, ready } = useAuth()

  if (!ready) {
    return (
      <div className="grid min-h-screen place-items-center bg-app">
        <Loader2 className="h-5 w-5 animate-spin text-muted" />
      </div>
    )
  }

  if (!email) return <Login />

  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/bookings" element={<Bookings />} />
        <Route path="/documents" element={<Documents />} />
        <Route path="/playground" element={<Playground />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Shell>
  )
}
