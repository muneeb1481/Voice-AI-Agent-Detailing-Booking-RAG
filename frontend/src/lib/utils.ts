import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatMoney(cents: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(
    cents / 100,
  )
}

// Mirrors backend/app/services/timezones.py's STATE_TIMEZONES — a job's time
// must display in ITS state's local time, not the dashboard viewer's own
// timezone (a dispatcher can be anywhere; the customer and crew are in-state).
const STATE_TIMEZONES: Record<string, string> = {
  AL: 'America/Chicago', AK: 'America/Anchorage', AZ: 'America/Phoenix',
  AR: 'America/Chicago', CA: 'America/Los_Angeles', CO: 'America/Denver',
  CT: 'America/New_York', DE: 'America/New_York', FL: 'America/New_York',
  GA: 'America/New_York', HI: 'Pacific/Honolulu', ID: 'America/Boise',
  IL: 'America/Chicago', IN: 'America/Indiana/Indianapolis', IA: 'America/Chicago',
  KS: 'America/Chicago', KY: 'America/New_York', LA: 'America/Chicago',
  ME: 'America/New_York', MD: 'America/New_York', MA: 'America/New_York',
  MI: 'America/Detroit', MN: 'America/Chicago', MS: 'America/Chicago',
  MO: 'America/Chicago', MT: 'America/Denver', NE: 'America/Chicago',
  NV: 'America/Los_Angeles', NH: 'America/New_York', NJ: 'America/New_York',
  NM: 'America/Denver', NY: 'America/New_York', NC: 'America/New_York',
  ND: 'America/Chicago', OH: 'America/New_York', OK: 'America/Chicago',
  OR: 'America/Los_Angeles', PA: 'America/New_York', RI: 'America/New_York',
  SC: 'America/New_York', SD: 'America/Chicago', TN: 'America/Chicago',
  TX: 'America/Chicago', UT: 'America/Denver', VT: 'America/New_York',
  VA: 'America/New_York', WA: 'America/Los_Angeles', WV: 'America/New_York',
  WI: 'America/Chicago', WY: 'America/Denver', DC: 'America/New_York',
}
const DEFAULT_TIMEZONE = 'America/New_York'

export function timeZoneForState(state?: string | null) {
  return STATE_TIMEZONES[(state ?? '').toUpperCase()] ?? DEFAULT_TIMEZONE
}

/** e.g. "3:00 PM CDT" — always in the job's own state, never the viewer's zone. */
export function formatTime(iso: string | null, state?: string | null) {
  if (!iso) return 'No time yet'
  return new Date(iso).toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
    timeZone: timeZoneForState(state),
  })
}

/** Calendar date (YYYY-MM-DD) of an instant in the job's own state. */
export function localDateKey(iso: string, state?: string | null) {
  return new Intl.DateTimeFormat('en-CA', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    timeZone: timeZoneForState(state),
  }).format(new Date(iso))
}

/** "HH:MM" of an instant in the job's own state. */
export function localTimeKey(iso: string, state?: string | null) {
  return new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
    timeZone: timeZoneForState(state),
  }).format(new Date(iso))
}

/** A date + wall-clock time typed for a job in `state` -> UTC ISO string.
 * Uses the state's zone, not the browser's: an admin in any timezone typing
 * 10:00 for a Maryland job gets 10 AM Maryland time. */
export function stateWallClockToIso(date: string, time: string, state?: string | null) {
  const guess = new Date(`${date}T${time}:00Z`)
  // Offset of the state's zone at (roughly) that instant; re-check once for DST edges.
  const offsetAt = (d: Date) => {
    const asLocal = new Date(
      new Intl.DateTimeFormat('en-US', {
        timeZone: timeZoneForState(state),
        hourCycle: 'h23',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
        .format(d)
        .replace(/(\d+)\/(\d+)\/(\d+), (\d+):(\d+):(\d+)/, '$3-$1-$2T$4:$5:$6Z'),
    )
    return asLocal.getTime() - d.getTime()
  }
  let utc = guess.getTime() - offsetAt(guess)
  utc = guess.getTime() - offsetAt(new Date(utc))
  return new Date(utc).toISOString()
}

export function formatDate(iso: string | null, state?: string | null) {
  if (!iso) return 'No date yet'
  return new Date(iso).toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    timeZone: timeZoneForState(state),
  })
}

export function toISODate(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(
    d.getDate(),
  ).padStart(2, '0')}`
}

export function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
