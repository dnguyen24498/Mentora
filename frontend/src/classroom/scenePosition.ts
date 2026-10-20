import type { ClassScene, SessionSnapshot } from '../api/client'

/**
 * Resolve a slide order from a session snapshot.
 *
 * The runtime's authoritative position is the lesson `scene_id` (with the
 * timeline's `scene_id` as the same value's second home). The scene list is the
 * package's slide order, so the scene id is the stable join; `section_index` is a
 * fallback for a plan whose section order matches the slide order.
 */
export function sceneOrderFor(
  scenes: readonly ClassScene[],
  snapshot: Pick<SessionSnapshot, 'document'> | null,
): number | null {
  if (!snapshot || scenes.length === 0) return null
  const lesson = snapshot.document.lesson
  const timeline = snapshot.document.timeline
  return resolveSceneOrder(
    scenes,
    lesson.scene_id ?? timeline.scene_id ?? null,
    lesson.section_index ?? null,
  )
}

export function resolveSceneOrder(
  scenes: readonly ClassScene[],
  sceneId: string | null,
  sectionIndex: number | null,
): number | null {
  if (sceneId) {
    const match = scenes.find((scene) => scene.scene_id === sceneId)
    if (match) return match.order
  }
  if (
    typeof sectionIndex === 'number' &&
    Number.isInteger(sectionIndex) &&
    sectionIndex >= 0 &&
    sectionIndex < scenes.length
  ) {
    return scenes[sectionIndex].order
  }
  return null
}
