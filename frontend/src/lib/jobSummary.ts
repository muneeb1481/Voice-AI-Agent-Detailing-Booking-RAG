import type { Booking } from './types'
import { stateName } from './usStates'
import { formatDate, formatMoney, formatTime } from './utils'

export const BRAND_LINE = 'ShinePro Mobile Detailing'

/** Plain-text summary for pasting into a group chat or dispatch tool — same shape
 * for every job regardless of how it was created (voice, admin, or parser). */
export function jobSummaryText(b: Booking): string {
  const lines = [
    `Name: ${b.customer.name}`,
    `Contact: ${b.customer.phone}`,
    `Vehicle: ${b.vehicle ?? 'Not provided'}${b.vehicle_category ? ` (${b.vehicle_category})` : ''}`,
    `Address: ${[b.address, b.zip_code, b.state ? stateName(b.state) : null].filter(Boolean).join(', ') || 'Not provided'}`,
    `Service: ${b.service_label ?? 'Not specified'}`,
    `Price: ${b.price_cents != null ? formatMoney(b.price_cents) : 'Not set'}`,
    `Detailer: ${b.detailer ?? 'Unassigned'}`,
    `Date: ${formatDate(b.starts_at)} at ${formatTime(b.starts_at)}`,
    `Status: ${b.status}`,
    `Source: ${b.source}`,
    b.notes ? `Notes: ${b.notes}` : null,
    `Brand: ${BRAND_LINE}`,
  ]
  return lines.filter((l): l is string => l !== null).join('\n')
}
