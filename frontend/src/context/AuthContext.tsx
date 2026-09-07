import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, getToken, setToken } from '@/lib/api'

interface AuthValue {
  email: string | null
  ready: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthValue>({
  email: null,
  ready: false,
  login: async () => {},
  logout: () => {},
})

export const useAuth = () => useContext(AuthContext)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [email, setEmail] = useState<string | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (!getToken()) {
      setReady(true)
      return
    }
    api
      .me()
      .then((u) => setEmail(u.email))
      .catch(() => setToken(null))
      .finally(() => setReady(true))
  }, [])

  useEffect(() => {
    const onExpired = () => setEmail(null)
    window.addEventListener('auth:expired', onExpired)
    return () => window.removeEventListener('auth:expired', onExpired)
  }, [])

  const login = useCallback(async (e: string, password: string) => {
    const res = await api.login(e, password)
    setToken(res.access_token)
    setEmail(res.email)
  }, [])

  const logout = useCallback(() => {
    setToken(null)
    setEmail(null)
  }, [])

  return (
    <AuthContext.Provider value={{ email, ready, login, logout }}>{children}</AuthContext.Provider>
  )
}
