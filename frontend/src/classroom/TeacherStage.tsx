import { useCallback, useEffect, useState } from 'react'
import {
  describeApiError,
  loadClassScenes,
  navigateClassScene,
  type ClassScene,
  type ClassSceneList,
  type SessionSnapshot,
} from '../api/client'
import { Banner, BUTTON_SECONDARY, EmptyState } from '../components/ui'
import { resolveSceneOrder } from './scenePosition'
import { usePinnedSlide } from './usePinnedSlide'

export interface TeacherStageProps {
  classId: string
  /** The authoritative session state from the client's snapshot projection. */
  sessionState: string | null
  /** The current lesson scene and section, from the same projection. */
  currentSceneId: string | null
  currentSectionIndex: number | null
  /** The version the teacher's view is based on; the command is fenced by it. */
  stateVersion: number
  /** Apply the snapshot the command returned (the parent owns the store). */
  onSnapshot: (snapshot: SessionSnapshot) => void
  /** Re-read the authoritative snapshot after a refusal or a lost race. */
  onResync: () => void
}

const RUNNING_STATES = new Set(['ACTIVE', 'DEGRADED'])
const FINISHED_STATES = new Set(['COMPLETED', 'FAILED', 'ENDING'])

/**
 * The teacher's presentation surface (V0-025).
 *
 * The teacher advances the **pinned package's** slides. The command is an HTTP
 * `NAVIGATE_SCENE` over the existing aggregate; it is not the ordered per-class
 * event stream (`DEC-DATA-003` is OPEN, V1-002). Students follow the resulting
 * snapshot by a short poll, so this stage never claims a realtime stream it does
 * not have.
 *
 * A command is fenced with the `state_version` the page is showing. If another
 * writer moved the class (or the class ended) the refusal is shown and the page
 * resynchronises rather than silently presenting the wrong slide.
 */
export default function TeacherStage({
  classId,
  sessionState,
  currentSceneId,
  currentSectionIndex,
  stateVersion,
  onSnapshot,
  onResync,
}: TeacherStageProps) {
  const [listing, setListing] = useState<ClassSceneList | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [pending, setPending] = useState(false)

  const running = sessionState !== null && RUNNING_STATES.has(sessionState)
  const finished = sessionState !== null && FINISHED_STATES.has(sessionState)
  const shouldLoad = running || finished

  useEffect(() => {
    if (!shouldLoad) {
      setListing(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    void (async () => {
      try {
        const next = await loadClassScenes(classId)
        if (!cancelled) setListing(next)
      } catch (cause) {
        if (!cancelled) setError(describeApiError(cause))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [classId, shouldLoad])

  const scenes = listing?.scenes ?? []
  const currentOrder =
    resolveSceneOrder(scenes, currentSceneId, currentSectionIndex) ?? scenes[0]?.order ?? null
  const index = currentOrder === null ? -1 : scenes.findIndex((scene) => scene.order === currentOrder)
  const scene = index >= 0 ? scenes[index] : null
  const { url, error: slideError } = usePinnedSlide(classId, scene?.order ?? null)

  const goTo = useCallback(
    async (target: ClassScene | undefined) => {
      if (!target || !running || pending) return
      setPending(true)
      setError(null)
      try {
        const outcome = await navigateClassScene(classId, {
          order: target.order,
          expected_state_version: stateVersion,
          command_id: newCommandId(),
        })
        if (outcome.snapshot) onSnapshot(outcome.snapshot)
        else if (!outcome.result.accepted) onResync()
      } catch (cause) {
        setError(describeApiError(cause))
        onResync()
      } finally {
        setPending(false)
      }
    },
    [classId, onResync, onSnapshot, pending, running, stateVersion],
  )

  if (sessionState === null) {
    return (
      <section
        data-testid="teacher-stage"
        className="mb-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
      >
        <h2 className="text-base font-semibold text-slate-800">Presenting</h2>
        <p className="mt-2 text-sm text-slate-600">
          This class has not started. Start it from class management; the running session then
          pins its slides and students can join.
        </p>
      </section>
    )
  }

  if (!shouldLoad) {
    return (
      <section
        data-testid="teacher-stage"
        className="mb-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
      >
        <h2 className="text-base font-semibold text-slate-800">Presenting</h2>
        <p className="mt-2 text-sm text-slate-600">
          This class is <span className="font-mono">{sessionState}</span>. Slides are presented
          while the session is running.
        </p>
      </section>
    )
  }

  return (
    <section
      data-testid="teacher-stage"
      className="mb-4 rounded-lg border border-slate-200 bg-white p-3 shadow-sm sm:p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold text-slate-800">Presenting</h2>
        <span className="text-sm text-slate-600" data-testid="teacher-slide-counter">
          {index >= 0 ? `Slide ${index + 1} of ${scenes.length}` : 'No slide'}
        </span>
      </div>

      {error && (
        <div className="mt-3">
          <Banner tone="bad">{error}</Banner>
        </div>
      )}
      {slideError && (
        <div className="mt-3">
          <Banner tone="bad">{slideError}</Banner>
        </div>
      )}

      <div className="mt-3 flex items-center justify-center bg-black">
        {url ? (
          <img
            src={url}
            alt={index >= 0 ? `Slide ${index + 1}` : 'Class slide'}
            className="h-auto max-h-[60vh] w-full object-contain"
          />
        ) : (
          <div className="p-6">
            <EmptyState>{loading ? 'Loading the slides…' : 'No slide to show yet.'}</EmptyState>
          </div>
        )}
      </div>

      {running ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void goTo(scenes[index - 1])}
            disabled={pending || index <= 0}
            className={BUTTON_SECONDARY}
          >
            ← Previous slide
          </button>
          <button
            type="button"
            onClick={() => void goTo(scenes[index + 1])}
            disabled={pending || index < 0 || index >= scenes.length - 1}
            className={BUTTON_SECONDARY}
          >
            Next slide →
          </button>

          <label className="block w-full min-w-0 max-w-full text-xs text-slate-500 sm:inline-block sm:w-auto sm:max-w-xs">
            <span className="sr-only">Slide</span>
            <select
              aria-label="Slide"
              value={currentOrder ?? ''}
              disabled={pending}
              onChange={(event) => {
                const target = scenes.find((item) => item.order === Number(event.target.value))
                void goTo(target)
              }}
              className="w-full min-w-0 max-w-full rounded-md border border-slate-300 bg-white px-2 py-2 text-base text-slate-800 lg:text-xs"
            >
              {scenes.map((item, position) => (
                <option key={item.scene_id} value={item.order}>
                  {position + 1}. {firstLine(item) || item.scene_id}
                </option>
              ))}
            </select>
          </label>

          {pending && (
            <span role="status" className="text-xs text-slate-500">
              Showing this slide to the class…
            </span>
          )}
        </div>
      ) : (
        <p role="status" className="mt-3 text-sm text-slate-600">
          This class has ended. Students keep the last slide; there is no live presentation to
          drive.
        </p>
      )}

      <p className="mt-2 text-[11px] text-slate-500">
        Students follow this slide automatically. The page polls the authoritative snapshot about
        every 1.5 seconds; the ordered per-class live stream is V1-002 (
        <span className="font-mono">DEC-DATA-003</span> is OPEN).
      </p>
    </section>
  )
}

/** A stable id for one command; the aggregate uses it for idempotency. */
function newCommandId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `cmd-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

/** The first line of a slide, for the teacher's slide picker. */
function firstLine(scene: ClassScene): string {
  const line = scene.text.find((value) => value.trim())
  return line ? line.trim().slice(0, 40) : ''
}
