const BASE = import.meta.env.VITE_API_BASE ?? ''
const TOKEN_KEY = 'detailops.token'

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* private mode — session-only auth is an acceptable degradation */
  }
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message)
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }

  const res = await fetch(`${BASE}${path}`, { ...init, headers })

  if (res.status === 401) {
    setToken(null)
    window.dispatchEvent(new CustomEvent('auth:expired'))
    throw new ApiError('Session expired. Please sign in again.', 401)
  }

  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail)) detail = body.detail[0]?.msg ?? detail
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail, res.status)
  }

  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string; email: string }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<{ email: string }>('/api/auth/me'),

  stats: () => request<import('./types').Stats>('/api/stats'),
  services: () => request<import('./types').Service[]>('/api/services'),

  detailers: () => request<import('./types').Detailer[]>('/api/detailers'),
  createDetailer: (name: string) =>
    request<import('./types').Detailer>('/api/detailers', {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),
  deleteDetailer: (id: string) =>
    request<void>(`/api/detailers/${id}`, { method: 'DELETE' }),

  callTranscripts: () => request<import('./types').CallTranscript[]>('/api/call-transcripts'),

  bookings: (params: Record<string, string | undefined>) => {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v) as [string, string][],
    )
    return request<import('./types').Booking[]>(`/api/bookings?${q}`)
  },
  createBooking: (body: unknown) =>
    request<import('./types').Booking>('/api/bookings', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  reschedule: (id: string, starts_at: string) =>
    request<import('./types').Booking>(`/api/bookings/${id}/reschedule`, {
      method: 'PATCH',
      body: JSON.stringify({ starts_at }),
    }),
  setStatus: (id: string, status: string) =>
    request<import('./types').Booking>(`/api/bookings/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),
  setDetailer: (id: string, detailer: string | null) =>
    request<import('./types').Booking>(`/api/bookings/${id}/detailer`, {
      method: 'PATCH',
      body: JSON.stringify({ detailer }),
    }),
  parseJob: (text: string) =>
    request<import('./types').ParsedJob>('/api/parse-job', {
      method: 'POST',
      body: JSON.stringify({ text }),
    }),
  createParsedBooking: (body: unknown) =>
    request<import('./types').Booking>('/api/bookings/parsed', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  slots: (state: string, day: string, duration = 90) =>
    request<import('./types').Slot[]>(
      `/api/slots?state=${state}&day=${day}&duration_minutes=${duration}`,
    ),

  documents: () => request<import('./types').Document[]>('/api/documents'),
  uploadDocument: (file: File, title?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (title) form.append('title', title)
    return request<import('./types').Document>('/api/documents', {
      method: 'POST',
      body: form,
    })
  },
  deleteDocument: (id: string) =>
    request<void>(`/api/documents/${id}`, { method: 'DELETE' }),

  ask: (question: string) =>
    request<import('./types').AskResponse>('/api/vapi/ask', {
      method: 'POST',
      body: JSON.stringify({ question }),
    }),
}
