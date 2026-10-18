import { useCallback, useEffect, useState } from 'react'

/**
 * The app's client-side settings (V0).
 *
 * There is **no settings API**: the server's only configuration is its
 * environment (the home region, `MENTORA_HOME_REGION`) and the per-request
 * render mode. So these are *client preferences* — persisted in `localStorage`,
 * shared across tabs, and applied where the client chooses (which render mode
 * slide previews ask for, how fast text-only teaching narrates). They are never
 * authoritative: nothing here changes what the server stores, seals or
 * publishes.
 *
 * Accessibility preferences (reduced motion, high contrast) are deliberately
 * **not** here: they already have one owner, the classroom's persisted UI
 * preferences (`classroom/state/store.ts`), and the Settings page edits those
 * rather than keeping a second copy that could drift.
 */

export type RenderMode = 'faithful' | 'themed'

export interface AppSettings {
  /** The render mode slide previews ask the server for (V0-019). */
  renderMode: RenderMode
  /** Narration pacing for text-only teaching, in words per minute. */
  teachingWpm: number
  /** Start narrating as soon as a deck is opened on the learning page. */
  teachingAutoplay: boolean
  /** Show the caption line while narrating. */
  teachingCaptions: boolean
}

export const TEACHING_WPM_MIN = 80
export const TEACHING_WPM_MAX = 260

export const DEFAULT_SETTINGS: AppSettings = {
  renderMode: 'faithful',
  teachingWpm: 160,
  teachingAutoplay: false,
  teachingCaptions: true,
}

const STORAGE_KEY = 'mentora.settings'

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

/** Read the settings, ignoring anything unreadable or out of range. */
export function readSettings(): AppSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_SETTINGS
    const parsed = JSON.parse(raw) as Partial<AppSettings>
    return {
      renderMode: parsed.renderMode === 'themed' ? 'themed' : 'faithful',
      teachingWpm:
        typeof parsed.teachingWpm === 'number' && Number.isFinite(parsed.teachingWpm)
          ? clamp(Math.round(parsed.teachingWpm), TEACHING_WPM_MIN, TEACHING_WPM_MAX)
          : DEFAULT_SETTINGS.teachingWpm,
      teachingAutoplay: Boolean(parsed.teachingAutoplay),
      teachingCaptions:
        parsed.teachingCaptions === undefined
          ? DEFAULT_SETTINGS.teachingCaptions
          : Boolean(parsed.teachingCaptions),
    }
  } catch {
    // Storage can be disabled (private mode, hardened browser).
    return DEFAULT_SETTINGS
  }
}

export function writeSettings(settings: AppSettings): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
  } catch {
    // Non-fatal: the value still applies to the page that is open.
  }
}

/**
 * The settings, shared by every page.
 *
 * Like the tenant, they are kept in step across tabs through the `storage`
 * event: a settings change made while a learning page is open in another tab
 * reaches it.
 */
export function useSettings(): [AppSettings, (patch: Partial<AppSettings>) => void] {
  const [settings, setSettings] = useState<AppSettings>(readSettings)

  const update = useCallback((patch: Partial<AppSettings>) => {
    setSettings((current) => {
      const next = { ...current, ...patch }
      writeSettings(next)
      return next
    })
  }, [])

  useEffect(() => {
    function onStorage(event: StorageEvent) {
      if (event.key === STORAGE_KEY) setSettings(readSettings())
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  return [settings, update]
}
