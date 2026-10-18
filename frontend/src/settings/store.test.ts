import { beforeEach, describe, expect, it } from 'vitest'
import {
  DEFAULT_SETTINGS,
  TEACHING_WPM_MAX,
  TEACHING_WPM_MIN,
  readSettings,
  writeSettings,
} from './store'

describe('settings store', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('starts from the defaults', () => {
    expect(readSettings()).toEqual(DEFAULT_SETTINGS)
    expect(DEFAULT_SETTINGS.renderMode).toBe('faithful')
    expect(DEFAULT_SETTINGS.teachingAutoplay).toBe(false)
    // Nothing starts a class on its own until the teacher asks for it.
    expect(DEFAULT_SETTINGS.autoStartDueClasses).toBe(false)
  })

  it('round-trips what was written', () => {
    writeSettings({ ...DEFAULT_SETTINGS, renderMode: 'themed', teachingWpm: 120 })
    expect(readSettings()).toEqual({ ...DEFAULT_SETTINGS, renderMode: 'themed', teachingWpm: 120 })
  })

  it('survives unreadable storage instead of throwing', () => {
    localStorage.setItem('mentora.settings', '{not json')
    expect(readSettings()).toEqual(DEFAULT_SETTINGS)
  })

  it('ignores a value it cannot honour and keeps the rest', () => {
    localStorage.setItem(
      'mentora.settings',
      JSON.stringify({ renderMode: 'native-powerpoint', teachingWpm: 12, teachingAutoplay: true }),
    )
    const settings = readSettings()
    // An unknown mode is not a mode: the default stands.
    expect(settings.renderMode).toBe('faithful')
    // Out-of-range pacing is clamped into the readable band, not discarded.
    expect(settings.teachingWpm).toBe(TEACHING_WPM_MIN)
    expect(settings.teachingAutoplay).toBe(true)
  })

  it('clamps pacing from above too', () => {
    localStorage.setItem('mentora.settings', JSON.stringify({ teachingWpm: 9000 }))
    expect(readSettings().teachingWpm).toBe(TEACHING_WPM_MAX)
  })
})
