import { describe, expect, it } from 'vitest'
import { dwellForScene } from './playbackTiming'
import type { ClassScene } from '../api/client'

function scene(text: string[], notes: string | null = null): ClassScene {
  return {
    order: 0,
    scene_id: 'slide-1',
    fidelity: 'STRUCTURAL_RENDERED',
    notes,
    text,
    warnings: [],
    object_count: text.length,
    step_count: 0,
  }
}

/**
 * The dwell is the deck's own words at the teacher's pace, with a floor for an
 * empty slide and a ceiling so one paragraph cannot hold the room for minutes.
 */
describe('dwellForScene (V0-026)', () => {
  it('paces a slide by its text at the teacher’s reading speed', () => {
    // 160 words at 160 wpm is exactly one minute, capped at 30 s.
    expect(dwellForScene(scene(['word '.repeat(160).trim()]), 160)).toBe(30_000)
    // 80 words at 160 wpm is 30 s (also the cap).
    expect(dwellForScene(scene(['word '.repeat(80).trim()]), 160)).toBe(30_000)
    // 40 words at 160 wpm is 15 s: under the cap, above the floor.
    expect(dwellForScene(scene(['word '.repeat(40).trim()]), 160)).toBe(15_000)
  })

  it('has a floor so a blank slide does not flash past', () => {
    expect(dwellForScene(scene([]), 160)).toBe(5_000)
    expect(dwellForScene(scene(['one']), 600)).toBe(5_000)
  })

  it('counts the speaker notes as reading time too', () => {
    const words = 'word '.repeat(40).trim()
    expect(dwellForScene(scene([], words), 160)).toBe(15_000)
  })

  it('has no dwell when there is no scene', () => {
    expect(dwellForScene(null, 160)).toBe(0)
  })
})
