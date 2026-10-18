import { useEffect, useState } from 'react'

/**
 * A clock that ticks, and the formatting around scheduled instants.
 *
 * Scheduling in V0 is **client-local**. The backend records `scheduled_for` but
 * never acts on it: an automatic start would be a durable workflow/scheduler and
 * that technology decision (`DEC-TECH-003`) is `OPEN`. So anything that must
 * happen "at a time" happens in a page that is **open**, driven by this clock —
 * and every surface that uses it says so. Nothing here fakes a server timer.
 */

/**
 * A clock that re-renders the calling component on an interval.
 *
 * `enabled` is the point of the parameter: a page that is not counting anything
 * down runs no timer at all, so an idle page costs nothing and a test that never
 * schedules anything never has a pending interval.
 */
export function useNow(intervalMs = 1000, enabled = true): Date {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    if (!enabled) return undefined
    const timer = window.setInterval(() => setNow(new Date()), intervalMs)
    return () => window.clearInterval(timer)
  }, [enabled, intervalMs])

  return now
}

/** An ISO instant, or `null` when the value is absent or not a date. */
export function parseInstant(value: string | null | undefined): Date | null {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

/**
 * Whether a scheduled instant has arrived.
 *
 * An absent or unreadable value is never due: a class with no schedule, or a
 * corrupted one, must not fire.
 */
export function isDue(at: string | null | undefined, now: Date): boolean {
  const date = parseInstant(at)
  return date !== null && date.getTime() <= now.getTime()
}

/**
 * How far off an offset is, in words: `in 4m 20s`, `due now`, `5m ago`.
 *
 * The sign is the direction, so one function covers both waiting for a time and
 * reporting that it has passed.
 */
export function formatCountdown(ms: number): string {
  if (!Number.isFinite(ms)) return ''
  const totalSeconds = Math.round(Math.abs(ms) / 1000)
  if (totalSeconds < 1) return 'due now'
  const body = describeDuration(totalSeconds)
  return ms < 0 ? `${body} ago` : `in ${body}`
}

function describeDuration(totalSeconds: number): string {
  if (totalSeconds < 60) return `${totalSeconds}s`
  const minutes = Math.floor(totalSeconds / 60)
  if (minutes < 60) return joinParts(minutes, 'm', totalSeconds % 60, 's')
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return joinParts(hours, 'h', minutes % 60, 'm')
  const days = Math.floor(hours / 24)
  return joinParts(days, 'd', hours % 24, 'h')
}

function joinParts(major: number, majorUnit: string, minor: number, minorUnit: string): string {
  return minor === 0 ? `${major}${majorUnit}` : `${major}${majorUnit} ${minor}${minorUnit}`
}

/** An instant in the reader's own locale and timezone; `—` when there is none. */
export function formatInstant(value: string | null | undefined): string {
  const date = parseInstant(value)
  return date ? date.toLocaleString() : '—'
}

/**
 * One line for a scheduled instant: when it is, and how far off that is.
 *
 * `now` is passed in rather than read here so the whole page describes every
 * schedule against one tick of the clock, and so this stays a pure function.
 */
export function describeSchedule(at: string | null | undefined, now: Date): string {
  const date = parseInstant(at)
  if (!date) return 'not scheduled'
  return `${formatInstant(at)} · ${formatCountdown(date.getTime() - now.getTime())}`
}

/**
 * A `Date` (or instant) as the `YYYY-MM-DDTHH:mm:ss` value an
 * `<input type="datetime-local">` takes, in local time.
 */
export function toDateTimeLocalValue(value: string | Date | null | undefined): string {
  const date = value instanceof Date ? value : parseInstant(value)
  if (!date || Number.isNaN(date.getTime())) return ''
  const pad = (part: number) => String(part).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  )
}

/**
 * The reverse: an input value, read as *local* time, as an ISO instant.
 *
 * A `datetime-local` value carries no zone, and the browser reads it in the
 * viewer's zone; `new Date` does the same, so the instant is the one the teacher
 * meant on their own clock. Absent or unreadable input is `null`, never `NaN`.
 */
export function fromDateTimeLocalValue(value: string | null | undefined): string | null {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date.toISOString()
}
