import type { SessionSnapshot } from '../../api/client'
import { applySnapshotToEvents, emptyEventsState, reduceEvent } from './reducer'
import type {
  ClassroomEvent,
  ClassroomMediaState,
  ClassroomState,
  ClassroomStatus,
  ClassroomUiPreferences,
  ClassroomUiState,
  EventOutcome,
} from './types'

const PREFERENCES_KEY = 'mentora.classroom.prefs'

function readPreferences(): ClassroomUiPreferences {
  try {
    const raw = localStorage.getItem(PREFERENCES_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<ClassroomUiPreferences>
      return {
        reducedMotion: Boolean(parsed.reducedMotion),
        highContrast: Boolean(parsed.highContrast),
      }
    }
  } catch {
    // Storage can be disabled (private mode, hardened browser).
  }
  return { reducedMotion: false, highContrast: false }
}

function writePreferences(preferences: ClassroomUiPreferences): void {
  try {
    localStorage.setItem(PREFERENCES_KEY, JSON.stringify(preferences))
  } catch {
    // Non-fatal: the value still applies to the page that is open.
  }
}

/**
 * The classroom's persisted accessibility preferences.
 *
 * Exported so the Settings page edits the **same record** the classroom reads,
 * instead of keeping a second copy of the same two booleans that could drift.
 * The classroom store remains the owner of the storage key.
 */
export function readClassroomPreferences(): ClassroomUiPreferences {
  return readPreferences()
}

export function updateClassroomPreferences(
  patch: Partial<ClassroomUiPreferences>,
): ClassroomUiPreferences {
  const next = { ...readPreferences(), ...patch }
  writePreferences(next)
  return next
}

export function emptyMediaState(): ClassroomMediaState {
  return { teacherAudio: 'idle', captionsEnabled: true, transcript: [], studentMicActive: false }
}

function initialState(): ClassroomState {
  return {
    snapshot: null,
    events: emptyEventsState(),
    media: emptyMediaState(),
    ui: { focusScene: false, preferences: readPreferences() },
  }
}

/**
 * The classroom store: four separate slices (snapshot, events/reducer, media,
 * ephemeral UI) behind one subscription.
 *
 * Only the event slice is ever derived from the actor; media and UI are
 * client-only. `applySnapshot` is the single truthful write — everything else is
 * a projection of it or a purely local concern.
 */
export class ClassroomStore {
  private state: ClassroomState = initialState()
  private readonly listeners = new Set<() => void>()

  getState = (): ClassroomState => this.state

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
    }
  }

  /** Rebuild from the authoritative snapshot (a first load, a refresh or a resync). */
  applySnapshot(snapshot: SessionSnapshot): void {
    this.state = {
      ...this.state,
      snapshot: snapshot.document,
      events: applySnapshotToEvents(snapshot.document),
    }
    this.emit()
  }

  setStatus(status: ClassroomStatus): void {
    const freezeReason =
      status === 'disconnected' ? 'disconnected' : this.state.events.freezeReason
    this.state = { ...this.state, events: { ...this.state.events, status, freezeReason } }
    this.emit()
  }

  /** Apply one received event; returns the reducer's verdict. */
  applyEvent(event: ClassroomEvent): EventOutcome {
    const { next, outcome } = reduceEvent(this.state.events, event)
    const status: ClassroomStatus =
      outcome === 'gap' ? 'gap' : outcome === 'stale-epoch' ? 'stale-epoch' : next.status
    const freezeReason =
      outcome === 'gap' || outcome === 'stale-epoch' ? outcome : next.freezeReason
    this.state = { ...this.state, events: { ...next, status, freezeReason, lastOutcome: outcome } }
    this.emit()
    return outcome
  }

  setMedia(patch: Partial<ClassroomMediaState>): void {
    this.state = { ...this.state, media: { ...this.state.media, ...patch } }
    this.emit()
  }

  setUi(patch: Partial<Omit<ClassroomUiState, 'preferences'>>): void {
    this.state = { ...this.state, ui: { ...this.state.ui, ...patch } }
    this.emit()
  }

  updatePreferences(patch: Partial<ClassroomUiPreferences>): void {
    const preferences = { ...this.state.ui.preferences, ...patch }
    writePreferences(preferences)
    this.state = { ...this.state, ui: { ...this.state.ui, preferences } }
    this.emit()
  }

  private emit(): void {
    for (const listener of this.listeners) listener()
  }
}
