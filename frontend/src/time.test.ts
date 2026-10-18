import { describe, expect, it } from 'vitest'
import {
  describeSchedule,
  formatCountdown,
  formatInstant,
  fromDateTimeLocalValue,
  isDue,
  parseInstant,
  toDateTimeLocalValue,
} from './time'

describe('time — reading a scheduled instant', () => {
  it('parses an instant and refuses anything that is not one', () => {
    expect(parseInstant('2026-10-20T09:30:00Z')?.toISOString()).toBe('2026-10-20T09:30:00.000Z')
    expect(parseInstant(null)).toBeNull()
    expect(parseInstant(undefined)).toBeNull()
    expect(parseInstant('')).toBeNull()
    expect(parseInstant('half past nine')).toBeNull()
  })

  it('is due only once the instant has arrived', () => {
    const now = new Date('2026-10-20T09:30:00Z')
    expect(isDue('2026-10-20T09:29:59Z', now)).toBe(true)
    expect(isDue('2026-10-20T09:30:00Z', now)).toBe(true)
    expect(isDue('2026-10-20T09:30:01Z', now)).toBe(false)
    // Nothing to act on is never due, so a class without a time cannot fire.
    expect(isDue(null, now)).toBe(false)
    expect(isDue('half past nine', now)).toBe(false)
  })
})

describe('time — describing a countdown', () => {
  it('reads in both directions, because a time can pass unnoticed', () => {
    expect(formatCountdown(0)).toBe('due now')
    expect(formatCountdown(400)).toBe('due now')
    expect(formatCountdown(5_000)).toBe('in 5s')
    expect(formatCountdown(90_000)).toBe('in 1m 30s')
    expect(formatCountdown(3_600_000)).toBe('in 1h')
    expect(formatCountdown(90_000_000)).toBe('in 1d 1h')
    expect(formatCountdown(-5_000)).toBe('5s ago')
  })

  it('does not produce nonsense for a value that is not a duration', () => {
    expect(formatCountdown(Number.NaN)).toBe('')
    expect(formatCountdown(Number.POSITIVE_INFINITY)).toBe('')
  })
})

describe('time — the datetime-local value', () => {
  it('round-trips through the reader’s own timezone', () => {
    // Both directions read the wall clock, so the round trip holds in any zone.
    expect(toDateTimeLocalValue(fromDateTimeLocalValue('2026-10-20T09:30'))).toBe(
      '2026-10-20T09:30:00',
    )
    const iso = fromDateTimeLocalValue('2026-10-20T09:30')
    expect(iso).not.toBeNull()
    // The instant is the teacher's own 09:30, whatever the zone offset is.
    expect(new Date(iso as string).getHours()).toBe(9)
    expect(new Date(iso as string).getMinutes()).toBe(30)
  })

  it('is empty rather than invalid when there is no value', () => {
    expect(toDateTimeLocalValue(null)).toBe('')
    expect(toDateTimeLocalValue('')).toBe('')
    expect(toDateTimeLocalValue('half past nine')).toBe('')
    expect(fromDateTimeLocalValue('')).toBeNull()
    expect(fromDateTimeLocalValue(null)).toBeNull()
    expect(fromDateTimeLocalValue('half past nine')).toBeNull()
  })
})

describe('time — one line for a schedule', () => {
  it('names the instant and how far off it is, both ahead and behind', () => {
    const now = new Date('2026-10-20T09:30:00Z')
    expect(describeSchedule(null, now)).toBe('not scheduled')
    expect(describeSchedule('2026-10-20T09:40:00Z', now)).toBe(
      `${formatInstant('2026-10-20T09:40:00Z')} · in 10m`,
    )
    expect(describeSchedule('2026-10-20T09:25:00Z', now)).toContain('5m ago')
  })
})
