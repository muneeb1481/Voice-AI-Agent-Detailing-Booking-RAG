export type Market = 'memphis' | 'nashville' | 'louisville'
export type BookingStatus = 'scheduled' | 'done' | 'rescheduled' | 'cancelled'

export const MARKETS: Market[] = ['memphis', 'nashville', 'louisville']
export const STATUSES: BookingStatus[] = ['scheduled', 'done', 'rescheduled', 'cancelled']

export interface Customer {
  id: string
  name: string
  phone: string
  email: string | null
}

export interface Booking {
  id: string
  market: Market
  detailer: string | null
  vehicle: string | null
  address: string | null
  notes: string | null
  starts_at: string
  ends_at: string
  status: BookingStatus
  source: string
  customer: Customer
}

export interface Document {
  id: string
  title: string
  filename: string
  content_type: string
  size_bytes: number
  chunk_count: number
  created_at: string
}

export interface Service {
  id: string
  name: string
  duration_minutes: number
  price_cents: number
  active: boolean
}

export interface Stats {
  bookings_today: number
  bookings_this_week: number
  upcoming: number
  cancelled_this_week: number
  documents: number
  chunks: number
  by_market: Record<string, number>
  by_status: Record<string, number>
}

export interface Slot {
  starts_at: string
  ends_at: string
  detailer: string | null
}

export interface AskResponse {
  answer: string
  grounded: boolean
  sources: {
    document_id: string
    document_title: string
    chunk_index: number
    content: string
    score: number
  }[]
}
