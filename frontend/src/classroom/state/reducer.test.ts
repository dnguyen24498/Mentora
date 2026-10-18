import { describe, expect, it } from 'vitest'
import { applySnapshotToEvents, emptyEventsState, reduceEvent } from './reducer'
import { makeEvent, makeSnapshot, sceneChangedEvent } from './testing'

/**
 * The reducer is pure, so these are the acceptance criteria of V0-011 in their
 * most direct form: refresh restores scene and state, duplicate/stale events are
 * ignored, and a sequence gap is reported rather than applied.
 */
describe('classroom event reducer', () => {
  it('rebuilds the scene, session and versions from the authoritative snapshot', () => {
    const state = applySnapshotToEvents(
      makeSnapshot({ sceneId: 'ppt/slides/slide2.xml', sectionIndex: 1, sequence: 3 }).document,
    )
    expect(state.status).toBe('live')
    expect(state.epoch).toBe(1)
    expect(state.lastSequence).toBe(3)
    expect(state.stateVersion).toBe(3)
    expect(state.sessionState).toBe('ACTIVE')
    expect(state.versions?.version_id).toBe('version-1')
    expect(state.scene).toEqual({
      sectionIndex: 1,
      sectionId: 'section-1',
      sceneId: 'ppt/slides/slide2.xml',
      stepId: null,
    })
  })

  it('applies a contiguous event for the current epoch', () => {
    const base = applySnapshotToEvents(makeSnapshot().document)
    const { next, outcome } = reduceEvent(base, sceneChangedEvent(2, 'ppt/slides/slide2.xml', 1))
    expect(outcome).toBe('applied')
    expect(next.lastSequence).toBe(2)
    expect(next.scene.sceneId).toBe('ppt/slides/slide2.xml')
    expect(next.scene.sectionIndex).toBe(1)
  })

  it('ignores a duplicate event (same sequence) without changing state', () => {
    const base = applySnapshotToEvents(makeSnapshot({ sequence: 2 }).document)
    const { next, outcome } = reduceEvent(base, sceneChangedEvent(2, 'ppt/slides/slide9.xml', 8))
    expect(outcome).toBe('ignored-duplicate')
    expect(next).toBe(base)
    expect(next.scene.sceneId).toBe('ppt/slides/slide1.xml')
  })

  it('ignores a stale event (older sequence) without changing state', () => {
    const base = applySnapshotToEvents(makeSnapshot({ sequence: 5 }).document)
    const { next, outcome } = reduceEvent(base, sceneChangedEvent(3, 'ppt/slides/slide3.xml', 2))
    expect(outcome).toBe('ignored-stale')
    expect(next).toBe(base)
  })

  it('reports a sequence gap and does not apply the out-of-order event', () => {
    const base = applySnapshotToEvents(
      makeSnapshot({ sequence: 2, sceneId: 'ppt/slides/slide2.xml', sectionIndex: 1 }).document,
    )
    const { next, outcome } = reduceEvent(base, sceneChangedEvent(4, 'ppt/slides/slide4.xml', 3))
    expect(outcome).toBe('gap')
    expect(next).toBe(base)
    expect(next.scene.sceneId).toBe('ppt/slides/slide2.xml')
  })

  it('discards an effect from a superseded epoch', () => {
    const base = applySnapshotToEvents(makeSnapshot().document)
    const { next, outcome } = reduceEvent(
      base,
      makeEvent({ sequence: 2, actor_epoch: 2, payload: {} }),
    )
    expect(outcome).toBe('stale-epoch')
    expect(next).toBe(base)
  })

  it('ignores an event that arrives before any snapshot', () => {
    const base = emptyEventsState()
    const { next, outcome } = reduceEvent(base, sceneChangedEvent(2, 'ppt/slides/slide2.xml', 1))
    expect(outcome).toBe('no-snapshot')
    expect(next).toBe(base)
  })

  it('freezes while a gap or stale epoch is unresolved', () => {
    const base = { ...applySnapshotToEvents(makeSnapshot().document), status: 'gap' as const }
    expect(reduceEvent(base, sceneChangedEvent(2, 'ppt/slides/slide2.xml', 1)).outcome).toBe(
      'ignored-frozen',
    )
  })

  it('advances the cursor for an unknown event type without mutating the domain', () => {
    const base = applySnapshotToEvents(makeSnapshot().document)
    const { next, outcome } = reduceEvent(
      base,
      makeEvent({ sequence: 2, type: 'classroom.future.thing', payload: {} }),
    )
    expect(outcome).toBe('applied')
    expect(next.lastSequence).toBe(2)
    expect(next.scene).toEqual(base.scene)
  })

  it('tracks a checkpoint and a session end', () => {
    let state = applySnapshotToEvents(makeSnapshot().document)
    state = reduceEvent(
      state,
      makeEvent({
        sequence: 2,
        type: 'classroom.checkpoint.recorded',
        payload: {
          checkpoint: {
            checkpoint_id: 'cp-1',
            scene_id: 'ppt/slides/slide1.xml',
            step_id: null,
            label: 'pause',
            final: false,
            created_at: '2026-10-17T10:00:00Z',
          },
        },
      }),
    ).next
    expect(state.checkpoint?.checkpoint_id).toBe('cp-1')
    state = reduceEvent(
      state,
      makeEvent({
        sequence: 3,
        type: 'classroom.session.ended',
        payload: {
          final_checkpoint: {
            checkpoint_id: 'cp-2',
            scene_id: 'ppt/slides/slide1.xml',
            step_id: null,
            label: 'class-ended',
            final: true,
            created_at: '2026-10-17T10:00:00Z',
          },
        },
      }),
    ).next
    expect(state.sessionState).toBe('COMPLETED')
    expect(state.checkpoint?.final).toBe(true)
  })
})
