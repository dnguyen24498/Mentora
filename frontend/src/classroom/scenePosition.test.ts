import { describe, expect, it } from 'vitest'
import type { ClassScene } from '../api/client'
import { resolveSceneOrder, sceneOrderFor } from './scenePosition'
import { makeSnapshot } from './state/testing'

const SCENES: ClassScene[] = [
  {
    order: 0,
    scene_id: 'slide1.xml',
    fidelity: 'STRUCTURAL_RENDERED',
    notes: null,
    text: ['One'],
    warnings: [],
    object_count: 1,
    step_count: 1,
  },
  {
    order: 1,
    scene_id: 'slide2.xml',
    fidelity: 'STRUCTURAL_RENDERED',
    notes: null,
    text: ['Two'],
    warnings: [],
    object_count: 1,
    step_count: 1,
  },
]

describe('sceneOrderFor', () => {
  it('uses the scene id before the section index', () => {
    expect(resolveSceneOrder(SCENES, 'slide2.xml', 0)).toBe(1)
  })

  it('falls back to the section index when the scene is not in the list', () => {
    expect(resolveSceneOrder(SCENES, 'missing.xml', 1)).toBe(1)
  })

  it('reads the authoritative lesson position from a snapshot', () => {
    const snapshot = makeSnapshot({ sceneId: 'slide2.xml', sectionIndex: 1 })
    expect(sceneOrderFor(SCENES, snapshot)).toBe(1)
  })

  it('returns null rather than guessing when nothing matches', () => {
    expect(resolveSceneOrder(SCENES, 'missing.xml', 99)).toBeNull()
    expect(sceneOrderFor([], makeSnapshot())).toBeNull()
    expect(sceneOrderFor(SCENES, null)).toBeNull()
  })
})
