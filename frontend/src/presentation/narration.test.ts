import { describe, expect, it } from 'vitest'
import {
  MAX_DWELL_MS,
  MIN_DWELL_MS,
  buildNarration,
  countWords,
  dwellMs,
  narrationText,
  segmentForScene,
  totalDurationMs,
} from './narration'
import { makePackage, makeScene } from '../test/fixtures'

describe('countWords', () => {
  it('counts words and ignores runs of whitespace', () => {
    expect(countWords('')).toBe(0)
    expect(countWords('   ')).toBe(0)
    expect(countWords('one')).toBe(1)
    expect(countWords('  one   two \n three ')).toBe(3)
  })
})

describe('dwellMs', () => {
  it('never flashes past and never holds the class for one paragraph', () => {
    // A slide with nothing to say still gets a beat.
    expect(dwellMs(0, 160)).toBe(MIN_DWELL_MS)
    expect(dwellMs(1, 160)).toBe(MIN_DWELL_MS)
    // A wall of text is capped rather than allowed to run away.
    expect(dwellMs(100_000, 160)).toBe(MAX_DWELL_MS)
  })

  it('scales with the passage and the pace', () => {
    // 160 words at 160 wpm is one minute — over the cap, so the cap is a sane
    // upper bound; a mid-length passage sits between the bounds.
    const sixtyWords = dwellMs(40, 160)
    expect(sixtyWords).toBeGreaterThan(MIN_DWELL_MS)
    expect(sixtyWords).toBeLessThan(MAX_DWELL_MS)

    // The same passage takes longer at a slower pace.
    expect(dwellMs(40, 80)).toBeGreaterThan(dwellMs(40, 200))
  })

  it('falls back to a sane pace rather than dividing by zero', () => {
    expect(dwellMs(40, 0)).toBe(dwellMs(40, 160))
  })
})

describe('narrationText', () => {
  it('prefers the authored lesson script', () => {
    expect(narrationText(makeScene(0), 'Explain slide 1')).toEqual({
      text: 'Explain slide 1',
      source: 'lesson-script',
    })
  })

  it('falls back to speaker notes, then to the slide text, then to nothing', () => {
    expect(narrationText(makeScene(0), null).source).toBe('speaker-notes')
    expect(narrationText(makeScene(0, { notes: null }), null)).toEqual({
      text: 'Slide 1 body',
      source: 'slide-text',
    })
    expect(narrationText(makeScene(0, { notes: null, text: [] }), null)).toEqual({
      text: '',
      source: 'none',
    })
  })

  it('ignores a blank script rather than narrating whitespace', () => {
    expect(narrationText(makeScene(0), '   ').source).toBe('speaker-notes')
  })
})

describe('buildNarration', () => {
  it('builds one segment per scene, in deck order, with its source', () => {
    const segments = buildNarration(makePackage(), 160)

    expect(segments.map((segment) => segment.scene_id)).toEqual([
      'ppt/slides/slide1.xml',
      'ppt/slides/slide2.xml',
    ])
    expect(segments[0].source).toBe('lesson-script')
    expect(segments[0].text).toBe('Explain slide 1')
    // The second section has no script in the fixture, so the notes carry it.
    expect(segments[1].source).toBe('speaker-notes')
    expect(segments[1].text).toBe('Notes for slide 2')
    expect(segments.every((segment) => segment.durationMs >= MIN_DWELL_MS)).toBe(true)
  })

  it('re-paces every segment when the pace changes — the words do not change', () => {
    const slow = buildNarration(makePackage(), 80)
    const fast = buildNarration(makePackage(), 240)

    expect(slow.map((segment) => segment.text)).toEqual(fast.map((segment) => segment.text))
    expect(totalDurationMs(slow)).toBeGreaterThanOrEqual(totalDurationMs(fast))
  })

  it('finds a segment by scene, and says so when there is none', () => {
    const segments = buildNarration(makePackage(), 160)
    expect(segmentForScene(segments, 'ppt/slides/slide2.xml')?.order).toBe(1)
    expect(segmentForScene(segments, 'ppt/slides/slide9.xml')).toBeNull()
  })

  it('prefers the teacher’s draft revision over the package’s own script', () => {
    const draft = {
      draft_id: 'draft-1',
      artifact_id: 'artifact-1',
      version_id: 'version-1',
      package_id: 'pkg-abc',
      content_package_version: 'cpv-abc',
      lesson_plan_version: 'lp-abc',
      revision: 2,
      sections: [
        {
          order: 0,
          section_id: 'sec-1',
          type: 'EXPLANATION',
          scene_id: 'ppt/slides/slide1.xml',
          scene_step_id: 'ppt/slides/slide1.xml#step-0',
          safe_markers: [],
          script: 'My rewritten opening',
        },
      ],
      edited_by: 'teacher@example.edu',
      created_at: '2026-10-16T11:00:00Z',
    }

    const segments = buildNarration(makePackage(), 160, draft)

    expect(segments[0]).toMatchObject({ text: 'My rewritten opening', source: 'draft-script' })
    // Scene 2 has no draft section, so the package/notes path still applies.
    expect(segments[1].source).toBe('speaker-notes')
  })

  it('ignores a blank draft script rather than narrating whitespace', () => {
    const segments = buildNarration(makePackage(), 160, {
      draft_id: 'draft-1',
      artifact_id: 'artifact-1',
      version_id: 'version-1',
      package_id: 'pkg-abc',
      content_package_version: 'cpv-abc',
      lesson_plan_version: 'lp-abc',
      revision: 3,
      sections: [
        {
          order: 0,
          section_id: 'sec-1',
          type: 'EXPLANATION',
          scene_id: 'ppt/slides/slide1.xml',
          scene_step_id: null,
          safe_markers: [],
          script: '   ',
        },
      ],
      edited_by: 'teacher@example.edu',
      created_at: '2026-10-16T11:00:00Z',
    })

    expect(segments[0]).toMatchObject({ text: 'Explain slide 1', source: 'lesson-script' })
  })
})
