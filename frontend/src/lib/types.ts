export type BookingStatus = 'scheduled' | 'done' | 'rescheduled' | 'cancelled'

export const STATUSES: BookingStatus[] = ['scheduled', 'done', 'rescheduled', 'cancelled']

export interface Customer {
  id: string
  name: string
  phone: string
  email: string | null
}

export type BookingSource = 'voice' | 'admin' | 'parser' | string

export interface BookingItem {
  id: string
  item_type: 'service' | 'addon' | string
  name: string
  price_cents: number
  duration_minutes: number
}

export interface Booking {
  id: string
  state: string | null
  zip_code: string | null
  detailer: string | null
  vehicle: string | null
  vehicle_category: string | null
  vehicle_length_ft: number | null
  address: string | null
  notes: string | null
  cancellation_reason: string | null
  price_cents: number | null
  original_price_cents: number | null
  discount_cents: number
  service_label: string | null
  items: BookingItem[]
  starts_at: string
  ends_at: string
  status: BookingStatus
  source: BookingSource
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

export interface ServicePrice {
  category: string
  price_cents: number
  min_price_cents: number | null
}

export interface Service {
  id: string
  name: string
  duration_minutes: number
  price_cents: number
  large_vehicle_surcharge_cents: number
  price_per_foot_cents: number | null
  prices: ServicePrice[]
  active: boolean
}

export interface Stats {
  bookings_today: number
  bookings_this_week: number
  upcoming: number
  cancelled_this_week: number
  documents: number
  chunks: number
  by_state: Record<string, number>
  by_status: Record<string, number>
}

export interface Slot {
  starts_at: string
  ends_at: string
  detailer: string | null
}

export interface AddOn {
  id: string
  name: string
  duration_minutes: number
  price_cents: number
  large_vehicle_surcharge_cents: number
  active: boolean
}

export interface Detailer {
  id: string
  name: string
  active: boolean
}

export interface ParsedJob {
  customer_name: string | null
  customer_phone: string | null
  vehicle: string | null
  state: string | null
  zip_code: string | null
  address: string | null
  service_label: string | null
  price_cents: number | null
  starts_at: string | null
  notes: string | null
}

export interface CallTranscript {
  id: string
  call_id: string | null
  phone: string | null
  customer_name: string | null
  transcript: string | null
  summary: string | null
  ended_reason: string | null
  duration_seconds: number | null
  created_at: string
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
