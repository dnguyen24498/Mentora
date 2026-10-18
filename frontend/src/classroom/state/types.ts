import type {
  ClassroomCheckpoint,
  ClassroomRuntimeVersions,
  ClassroomSnapshotDocument,
  ClassroomTurn,
} from '../../api/client'

/**
 * The client-side classroom state (V0-011).
 *
 * The Classroom Actor (V0-010) is the single source of truth. Everything here is
 * a *projection*: it is rebuilt from the authoritative snapshot
 * (`GET /classes/{id}/snapshot`, the durable `runtime-snapshot@1` document) plus
 * contiguous ordered events. No value in this module is authoritative, and
 * nothing here is ever written back as truth.
 *
 * The state is deliberately split into separate slices (doc 15 —
 * `15_FRONTEND_CLASSROOM_AND_STUDIO.md`): the **event reducer**, the raw
 * **snapshot**, **media** state, **ephemeral UI** and **accessibility
 * preferences**. Keeping them apart means an event can never corrupt media or
 * UI, and a UI change can never be mistaken for classroom truth.
 */

export type {
  ClassroomCheckpoint,
  ClassroomRuntimeVersions,
  ClassroomSnapshotDocument,
  ClassroomTurn,
}

/** The consistency status of the client relative to the actor. */
export type ClassroomStatus =
  | 'idle' // constructed; no authoritative snapshot yet
  | 'live' // in sync with the actor at the current epoch
  | 'gap' // a sequence gap was seen; events are frozen pending resync
  | 'stale-epoch' // an event from a superseded epoch; frozen pending resync
  | 'resyncing' // reloading the authoritative snapshot
  | 'disconnected' // the authoritative snapshot could not be loaded

export interface ClassroomScene {
  sectionIndex: number | null
  sectionId: string | null
  sceneId: string | null
  stepId: string | null
}

/** Why the client is frozen (null while live). */
export type ClassroomFreezeReason = 'gap' | 'stale-epoch' | 'disconnected'

/** The verdict of one received event (mirrors the actor's own dedup rules). */
export type EventOutcome =
  | 'applied' // a contiguous event for the current epoch
  | 'ignored-duplicate' // already applied (same sequence)
  | 'ignored-stale' // older than the applied cursor
  | 'ignored-frozen' // skipped because the client is not live
  | 'gap' // sequence gap -> request resync
  | 'stale-epoch' // epoch mismatch -> discard and resync
  | 'no-snapshot' // an event arrived before any snapshot

/** The event-reducer slice: the only slice derived from the actor's stream. */
export interface ClassroomEventsState {
  status: ClassroomStatus
  freezeReason: ClassroomFreezeReason | null
  epoch: number | null
  lastSequence: number
  stateVersion: number
  sessionState: string | null
  scene: ClassroomScene
  checkpoint: ClassroomCheckpoint | null
  turn: ClassroomTurn | null
  versions: ClassroomRuntimeVersions | null
  lastOutcome: EventOutcome | null
}

export interface ClassroomTranscriptLine {
  id: string
  text: string
  /** A partial line is ephemeral and clearly marked (doc 18). */
  partial: boolean
}

/**
 * Media slice. V0-011 keeps this minimal and inert on purpose: group student
 * microphones stay unpublished (DEC-TURN-001), so nothing here activates audio.
 * Captions/transcript are populated by V0-013 and the voice path by V1.
 */
export interface ClassroomMediaState {
  teacherAudio: 'idle' | 'speaking' | 'cancelling'
  captionsEnabled: boolean
  transcript: ClassroomTranscriptLine[]
  studentMicActive: boolean
}

export interface ClassroomUiPreferences {
  reducedMotion: boolean
  highContrast: boolean
}

/** Ephemeral UI slice: never authority, never persisted as classroom state. */
export interface ClassroomUiState {
  focusScene: boolean
  preferences: ClassroomUiPreferences
}

export interface ClassroomState {
  snapshot: ClassroomSnapshotDocument | null
  events: ClassroomEventsState
  media: ClassroomMediaState
  ui: ClassroomUiState
}

/**
 * One ordered classroom event. This is the client's model of the event the
 * Classroom Actor emits (V0-010) and the shape the ordered per-class mechanism
 * will carry (`DEC-DATA-003` / V1-002): a stable id, the ordered `sequence`, the
 * `actor_epoch` fence and the `state_version`.
 */
export interface ClassroomEvent {
  event_id: string
  type: string
  sequence: number
  state_version: number
  actor_epoch: number
  occurred_at: string
  payload: Record<string, unknown>
}

export type ClassroomCommandType = 'NAVIGATE_NEXT' | 'NAVIGATE_PREVIOUS'

export interface ClassroomCommand {
  command_id: string
  type: ClassroomCommandType
  issued_at: string
}

export interface ClassroomTransportCapabilities {
  /** The transport can deliver ordered events (false until V1-002). */
  liveEvents: boolean
  /** The transport can send commands to the actor (false until V1-002). */
  commands: boolean
}
