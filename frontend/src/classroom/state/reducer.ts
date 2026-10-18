import type { ClassroomSnapshotDocument } from '../../api/client'
import type {
  ClassroomCheckpoint,
  ClassroomEvent,
  ClassroomEventsState,
  ClassroomScene,
  EventOutcome,
} from './types'

/**
 * The pure classroom event reducer (doc 15: "Apply contiguous events for current
 * epoch; duplicates/stale ignored; gaps require resync").
 *
 * It is a pure function of the last state and one event, so it is exhaustively
 * unit-testable and depends on nothing but its inputs — no React, no network, no
 * storage. The event names are the Classroom Actor's (V0-010); the wire event
 * schemas are V1-002's.
 */

export const EVENT_SESSION_STARTED = 'classroom.session.started'
export const EVENT_SCENE_CHANGED = 'classroom.scene.changed'
export const EVENT_CHECKPOINT_RECORDED = 'classroom.checkpoint.recorded'
export const EVENT_SESSION_ENDED = 'classroom.session.ended'

export function emptyScene(): ClassroomScene {
  return { sectionIndex: null, sectionId: null, sceneId: null, stepId: null }
}

export function emptyEventsState(): ClassroomEventsState {
  return {
    status: 'idle',
    freezeReason: null,
    epoch: null,
    lastSequence: 0,
    stateVersion: 0,
    sessionState: null,
    scene: emptyScene(),
    checkpoint: null,
    turn: null,
    versions: null,
    lastOutcome: null,
  }
}

/**
 * Rebuild the reducer state from the authoritative snapshot.
 *
 * This is the whole recovery story (DEC-RUNTIME-004): a refresh or a reconnect
 * starts from this document, and the ordered events continue from its
 * `event_sequence`, not from wherever the client happened to be.
 */
export function applySnapshotToEvents(document: ClassroomSnapshotDocument): ClassroomEventsState {
  const lesson = document.lesson
  const timeline = document.timeline
  return {
    status: 'live',
    freezeReason: null,
    epoch: document.actor_epoch,
    lastSequence: document.event_sequence,
    stateVersion: document.state_version,
    sessionState: document.state,
    scene: {
      sectionIndex: lesson.section_index ?? null,
      sectionId: lesson.section_id ?? null,
      sceneId: lesson.scene_id ?? timeline.scene_id ?? null,
      stepId: lesson.scene_step_id ?? timeline.step_id ?? null,
    },
    checkpoint: timeline.checkpoint ?? null,
    turn: document.turn,
    versions: document.versions,
    lastOutcome: null,
  }
}

export interface ReduceResult {
  next: ClassroomEventsState
  outcome: EventOutcome
}

/** Apply one received event; never mutates the input state. */
export function reduceEvent(state: ClassroomEventsState, event: ClassroomEvent): ReduceResult {
  if (state.epoch === null) return { next: state, outcome: 'no-snapshot' }
  // While not live we are frozen: a gap or a stale epoch is resolved by a
  // resync, never by guessing at the missing events (PROTOCOL: "gaps freeze
  // unsafe controls and request resync").
  if (state.status !== 'live') return { next: state, outcome: 'ignored-frozen' }
  // DEC-RUNTIME-007: an effect from a superseded epoch is discarded.
  if (event.actor_epoch !== state.epoch) return { next: state, outcome: 'stale-epoch' }
  // DEC-RUNTIME-003: a duplicate or an older event is ignored.
  if (event.sequence <= state.lastSequence) {
    return {
      next: state,
      outcome: event.sequence === state.lastSequence ? 'ignored-duplicate' : 'ignored-stale',
    }
  }
  // A hole in the ordered stream: freeze and resync rather than apply out of order.
  if (event.sequence > state.lastSequence + 1) return { next: state, outcome: 'gap' }
  return { next: applyEventPayload(state, event), outcome: 'applied' }
}

function applyEventPayload(state: ClassroomEventsState, event: ClassroomEvent): ClassroomEventsState {
  const base: ClassroomEventsState = {
    ...state,
    lastSequence: event.sequence,
    stateVersion: Math.max(state.stateVersion, event.state_version),
  }
  const payload = event.payload ?? {}
  switch (event.type) {
    case EVENT_SESSION_STARTED:
      return { ...base, sessionState: asString(payload.state) ?? 'ACTIVE' }
    case EVENT_SCENE_CHANGED: {
      const to = asRecord(payload.to)
      if (!to) return base
      return { ...base, scene: sceneFromPayload(to) }
    }
    case EVENT_CHECKPOINT_RECORDED:
      return { ...base, checkpoint: asCheckpoint(payload.checkpoint) ?? state.checkpoint }
    case EVENT_SESSION_ENDED:
      return {
        ...base,
        sessionState: 'COMPLETED',
        checkpoint: asCheckpoint(payload.final_checkpoint) ?? state.checkpoint,
      }
    default:
      // An unknown event still advances the cursor — its sequence is real even
      // though this client does not know the domain mutation it carries.
      return base
  }
}

function sceneFromPayload(to: Record<string, unknown>): ClassroomScene {
  return {
    sectionIndex: asNumber(to.section_index),
    sectionId: asString(to.section_id),
    sceneId: asString(to.scene_id),
    stepId: asString(to.scene_step_id),
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : null
}

function asString(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' ? value : null
}

function asCheckpoint(value: unknown): ClassroomCheckpoint | null {
  const record = asRecord(value)
  if (!record || typeof record.checkpoint_id !== 'string') return null
  return record as unknown as ClassroomCheckpoint
}
