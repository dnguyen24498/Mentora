import type { ClassroomSnapshotDocument, SessionSnapshot } from '../../api/client'
import type {
  ClassroomCommand,
  ClassroomEvent,
  ClassroomTransportCapabilities,
} from './types'
import type { ClassroomTransport } from './transport'

/**
 * Deterministic fixtures and a hand-driven transport for the classroom tests
 * (and for a local demo). Not production code: it stands in for the ordered
 * mechanism that V1-002 provides.
 */

export const TEST_INSTITUTION = 'university-001'
export const TEST_CLASS = 'class-1'

export interface SnapshotOverrides {
  sequence?: number
  stateVersion?: number
  epoch?: number
  state?: string
  sceneId?: string | null
  sectionIndex?: number | null
  stepId?: string | null
  checkpoint?: ClassroomSnapshotDocument['timeline']['checkpoint']
}

/** A valid `runtime-snapshot@1` document wrapped in its envelope. */
export function makeSnapshot(overrides: SnapshotOverrides = {}): SessionSnapshot {
  const epoch = overrides.epoch ?? 1
  const sequence = overrides.sequence ?? 1
  const stateVersion = overrides.stateVersion ?? sequence
  const sceneId = overrides.sceneId ?? 'ppt/slides/slide1.xml'
  const sectionIndex = overrides.sectionIndex ?? 0
  const stepId = overrides.stepId ?? null
  const document: ClassroomSnapshotDocument = {
    schema_version: 'runtime-snapshot@1',
    institution_id: TEST_INSTITUTION,
    course_id: 'course-1',
    class_id: TEST_CLASS,
    session_id: 'session-1',
    state: overrides.state ?? 'ACTIVE',
    actor_epoch: epoch,
    state_version: stateVersion,
    event_sequence: sequence,
    versions: {
      course_id: 'course-1',
      course_version: 1,
      version_id: 'version-1',
      publication_id: 'publication-1',
      package_id: 'package-1',
      content_package_version: 'cpv-1',
      content_digest: 'd'.repeat(64),
      lesson_plan_version: 'lpv-1',
      knowledge_index_version: 'unindexed',
      index_version_id: 'index-1',
      index_source_digest: 'd'.repeat(64),
      teaching_graph_version: null,
      assessment_version: null,
      model_routing_version: null,
      policy_version: 'runtime-policy@1',
      capability_version: 'local-structural-svg@3.1.0',
      region: 'local-1',
    },
    lesson: {
      lesson_plan_version: 'lpv-1',
      lesson_id: 'lesson-1',
      section_index: sectionIndex,
      section_id: sectionIndex === null ? null : `section-${sectionIndex}`,
      scene_id: sceneId,
      scene_step_id: stepId,
    },
    turn: { queue: [], floor: null, stt_reservation: null },
    timeline: { scene_id: sceneId, step_id: stepId, checkpoint: overrides.checkpoint ?? null },
    pending_effects: [],
  }
  return {
    snapshot_id: `snapshot-${sequence}`,
    class_id: TEST_CLASS,
    session_id: 'session-1',
    schema_version: 'runtime-snapshot@1',
    state: document.state,
    state_version: stateVersion,
    event_sequence: sequence,
    actor_epoch: epoch,
    checksum: 'c'.repeat(64),
    created_at: '2026-10-17T10:00:00Z',
    document,
  }
}

export function makeEvent(overrides: Partial<ClassroomEvent> & { sequence: number }): ClassroomEvent {
  return {
    event_id: `event-${overrides.sequence}`,
    type: 'classroom.scene.changed',
    state_version: overrides.sequence,
    actor_epoch: 1,
    occurred_at: '2026-10-17T10:00:00Z',
    payload: {},
    ...overrides,
  }
}

/** A `classroom.scene.changed` event, shaped exactly as V0-010 emits it. */
export function sceneChangedEvent(
  sequence: number,
  sceneId: string,
  sectionIndex: number,
): ClassroomEvent {
  return makeEvent({
    sequence,
    type: 'classroom.scene.changed',
    payload: {
      from: { section_index: sectionIndex - 1, scene_id: 'ppt/slides/slide1.xml', scene_step_id: null },
      to: {
        section_index: sectionIndex,
        section_id: `section-${sectionIndex}`,
        scene_id: sceneId,
        scene_step_id: null,
      },
    },
  })
}

/** A transport a test (or a local demo) drives by hand. */
export class ScriptedTransport implements ClassroomTransport {
  capabilities: ClassroomTransportCapabilities
  readonly sent: ClassroomCommand[] = []
  loadCount = 0
  current: SessionSnapshot
  failNext = 0
  hold = false
  private readonly handlers = new Set<(event: ClassroomEvent) => void>()
  private heldResolver: ((snapshot: SessionSnapshot) => void) | null = null

  constructor(options: {
    snapshot: SessionSnapshot
    capabilities?: ClassroomTransportCapabilities
  }) {
    this.current = options.snapshot
    this.capabilities = options.capabilities ?? { liveEvents: true, commands: true }
  }

  load = (): Promise<SessionSnapshot> => {
    this.loadCount += 1
    if (this.failNext > 0) {
      this.failNext -= 1
      return Promise.reject(new Error('scripted load failure'))
    }
    if (this.hold) {
      return new Promise<SessionSnapshot>((resolve) => {
        this.heldResolver = resolve
      })
    }
    return Promise.resolve(this.current)
  }

  subscribe = (handler: (event: ClassroomEvent) => void): (() => void) => {
    this.handlers.add(handler)
    return () => {
      this.handlers.delete(handler)
    }
  }

  send = (command: ClassroomCommand): void => {
    this.sent.push(command)
  }

  close = (): void => {
    this.handlers.clear()
  }

  emit(event: ClassroomEvent): void {
    for (const handler of this.handlers) handler(event)
  }

  /** Resolve a held `load()` (used to freeze the client mid-resync). */
  release(snapshot?: SessionSnapshot): void {
    const resolve = this.heldResolver
    this.heldResolver = null
    this.hold = false
    resolve?.(snapshot ?? this.current)
  }
}
