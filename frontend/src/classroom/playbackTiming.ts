import type { ClassScene } from '../api/client'

/**
 * How long a slide stays on screen during automatic play (V0-026).
 *
 * The deck's own words decide the dwell: the slide's text and notes, counted as
 * words, divided by the teacher's reading pace. A slide with nothing to read
 * still gets a minimum so the class does not race through blank slides, and a
 * long slide is capped so a single paragraph cannot hold the class for half a
 * minute. This is a client-local pacing decision, not a timeline: the server
 * has no scheduler (`DEC-TECH-003` is `OPEN`), so the teacher's classroom tab is
 * the clock, and closing it stops the play.
 */
export function dwellForScene(scene: ClassScene | null, wpm: number): number {
  if (!scene) return 0
  const words = (scene.text.join(' ') + ' ' + (scene.notes || ''))
    .trim()
    .split(/\s+/)
    .filter(Boolean).length
  if (words === 0) return 5000
  const ms = (words / wpm) * 60000
  return Math.min(30000, Math.max(5000, ms))
}