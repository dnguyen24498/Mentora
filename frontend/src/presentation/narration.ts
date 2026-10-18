import type { ReviewDraft, ReviewPackage, ReviewScene } from '../api/client'

/**
 * The narration a slide is taught with.
 *
 * This is **text-only teaching** and it is deliberately not a language model:
 * the text is *authored* — the teacher's newest draft revision for the section,
 * else the pinned package's lesson script, else the slide's speaker notes, else
 * the slide's own text — taken in a fixed precedence order, so the same deck
 * always narrates the same way. Nothing is generated, nothing is re-ordered and
 * nothing is dropped.
 *
 * There is no audio either. The voice capability is the provider-neutral speech
 * domain (`backend/app/speech/`), whose provider decision (`DEC-TECH-007`) is
 * still `OPEN`, so the text fallback path is the only one that runs here.
 */

export type NarrationSource =
  | 'draft-script'
  | 'lesson-script'
  | 'speaker-notes'
  | 'slide-text'
  | 'none'

export interface NarrationSegment {
  scene_id: string
  order: number
  /** The text narrated while this slide is on screen. */
  text: string
  source: NarrationSource
  words: number
  /** How long the slide stays on screen at the chosen pace. */
  durationMs: number
}

/** A slide never flashes past, and never holds the class hostage to one paragraph. */
export const MIN_DWELL_MS = 2_500
export const MAX_DWELL_MS = 30_000

export const DEFAULT_WPM = 160

export function countWords(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length
}

/** How long a passage takes to say at `wpm`, clamped to a readable band. */
export function dwellMs(words: number, wpm: number): number {
  const pace = wpm > 0 ? wpm : DEFAULT_WPM
  const raw = (words / pace) * 60_000
  return Math.round(Math.min(Math.max(raw, MIN_DWELL_MS), MAX_DWELL_MS))
}

/** The text for one slide: the teacher's script, else the speaker notes, else the slide's own text. */
export function narrationText(
  scene: ReviewScene,
  script: string | null,
  scriptSource: 'draft-script' | 'lesson-script' = 'lesson-script',
): { text: string; source: NarrationSource } {
  const authored = script?.trim()
  if (authored) return { text: authored, source: scriptSource }

  const notes = scene.notes?.trim()
  if (notes) return { text: notes, source: 'speaker-notes' }

  const text = scene.text.map((line) => line.trim()).filter(Boolean).join('\n')
  if (text) return { text, source: 'slide-text' }

  return { text: '', source: 'none' }
}

/** The whole deck's narration, one segment per scene, in deck order. */
export function buildNarration(
  review: ReviewPackage,
  wpm: number,
  /**
   * The teacher's newest draft revision, if there is one. It wins over the
   * package's own lesson script: the point of the feature is to hear the script
   * being written, and the source is labelled so it is never mistaken for the
   * published text.
   */
  draft: ReviewDraft | null = null,
): NarrationSegment[] {
  return review.scenes.map((scene) => {
    const draftScript = draft?.sections.find((entry) => entry.scene_id === scene.scene_id)?.script
    const lessonScript =
      review.lesson_order.find((entry) => entry.scene_id === scene.scene_id)?.script ?? null
    const { text, source } = draftScript?.trim()
      ? narrationText(scene, draftScript, 'draft-script')
      : narrationText(scene, lessonScript)
    const words = countWords(text)
    return {
      scene_id: scene.scene_id,
      order: scene.order,
      text,
      source,
      words,
      durationMs: dwellMs(words, wpm),
    }
  })
}

/** The segment for one scene, or `null` when the deck has no such scene. */
export function segmentForScene(
  segments: NarrationSegment[],
  sceneId: string,
): NarrationSegment | null {
  return segments.find((segment) => segment.scene_id === sceneId) ?? null
}

export function totalDurationMs(segments: NarrationSegment[]): number {
  return segments.reduce((total, segment) => total + segment.durationMs, 0)
}
