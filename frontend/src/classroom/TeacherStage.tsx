import { useCallback, useEffect, useState } from 'react'
import {
  describeApiError,
  endClass,
  loadClassScenes,
  loadPresentation,
  navigateClassScene,
  pausePresentation,
  reopenClass,
  resumePresentation,
  type ClassScene,
  type ClassSceneList,
  type PresentationStatus,
  type SessionSnapshot,
} from '../api/client'
import { Banner, BUTTON_SECONDARY, EmptyState } from '../components/ui'
import { resolveSceneOrder } from './scenePosition'
import { usePinnedSlide } from './usePinnedSlide'
import { useNarrationPlayer, type AudioSink } from '../audio/useNarrationPlayer'

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
  /**
   * Hear the class presenter's narration on this page too (V0-028). Defaults to
   * on; the page attaches to the relay the server runner publishes, never to a
   * second synthesis of its own.
   */
  voice?: boolean
  /** Injectable audio output (tests); the default is an `<audio>` element. */
  createAudioSink?: () => AudioSink
}

const RUNNING_STATES = new Set(['ACTIVE', 'DEGRADED'])
const FINISHED_STATES = new Set(['COMPLETED', 'FAILED', 'ENDING'])

/**
 * The teacher's presentation surface (V0-025, V0-028).
 *
 * Since V0-028 the **class server** is the presentation clock: a started class
 * synthesizes and advances its pinned slides in the API process, so closing this
 * tab does not stop the lesson. This stage therefore follows the authoritative
 * snapshot (the page polls it quietly) and offers teacher controls over that
 * runner — Pause/Resume, manual previous/next/picker, and End/Reopen.
 *
 * A manual move is an ordinary fenced `NAVIGATE_SCENE`; the background runner
 * notices the new position and restarts its narration there. A command is fenced
 * with the `state_version` the page is showing, so a stale view is refused and the
 * page resynchronises rather than silently presenting the wrong slide.
 */
export default function TeacherStage({
  classId,
  sessionState,
  currentSceneId,
  currentSectionIndex,
  stateVersion,
  onSnapshot,
  onResync,
  voice = true,
  createAudioSink,
}: TeacherStageProps) {
  const [listing, setListing] = useState<ClassSceneList | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [pending, setPending] = useState(false)
  const [presentation, setPresentation] = useState<PresentationStatus | null>(null)
  const [presentationError, setPresentationError] = useState<string | null>(null)
  const [presentationRevision, setPresentationRevision] = useState(0)
  const [control, setControl] = useState<'pause' | 'resume' | null>(null)

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

  // Read the runner's status (and re-read it after a control, or every few
  // seconds) so Pause/Resume is truthful after a reload and after an API restart.
  // A status failure does not hide the slides: the page remains a review surface.
  useEffect(() => {
    if (!shouldLoad) {
      setPresentation(null)
      setPresentationError(null)
      return
    }
    let cancelled = false
    void (async () => {
      try {
        const next = await loadPresentation(classId)
        if (!cancelled) {
          setPresentation(next)
          setPresentationError(null)
        }
      } catch (cause) {
        if (!cancelled) {
          setPresentation(null)
          setPresentationError(describeApiError(cause))
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [classId, presentationRevision, shouldLoad])

  useEffect(() => {
    if (!running || !shouldLoad) return
    const timer = window.setInterval(
      () => setPresentationRevision((value) => value + 1),
      3000,
    )
    return () => window.clearInterval(timer)
  }, [running, shouldLoad])

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
        else if (!outcome.result.accepted) {
          // A refused command means the class moved under this tab; ask the page
          // to re-read the authoritative snapshot rather than retrying a stale
          // target. The server runner restarts at the corrected position.
          onResync()
        }
      } catch (cause) {
        setError(describeApiError(cause))
        onResync()
      } finally {
        setPending(false)
      }
    },
    [classId, onResync, onSnapshot, pending, running, stateVersion],
  )

  // End and reopen are lifecycle commands, not slide moves: they are fenced by
  // the same state version and applied through the same snapshot the page holds.
  const [lifecycle, setLifecycle] = useState<'end' | 'reopen' | null>(null)

  const endNow = useCallback(async () => {
    if (!running || pending || lifecycle !== null) return
    if (
      typeof window !== 'undefined' &&
      typeof window.confirm === 'function' &&
      !window.confirm(
        'End this class? Students will not be able to open the lesson until you reopen it.',
      )
    ) {
      return
    }
    setLifecycle('end')
    setError(null)
    try {
      const outcome = await endClass(classId, {
        expected_state_version: stateVersion,
        command_id: newCommandId(),
      })
      if (outcome.snapshot) onSnapshot(outcome.snapshot)
      else if (outcome.result.duplicate) onResync()
      setPresentationRevision((value) => value + 1)
    } catch (cause) {
      setError(describeApiError(cause))
      onResync()
    } finally {
      setLifecycle(null)
    }
  }, [classId, lifecycle, onResync, onSnapshot, pending, running, stateVersion])

  const reopenNow = useCallback(async () => {
    if (sessionState !== 'COMPLETED' || pending || lifecycle !== null) return
    setLifecycle('reopen')
    setError(null)
    try {
      const outcome = await reopenClass(classId, {
        expected_state_version: stateVersion,
        command_id: newCommandId(),
      })
      if (outcome.snapshot) {
        onSnapshot(outcome.snapshot)
        setPresentationRevision((value) => value + 1)
      } else if (outcome.result.duplicate) {
        onResync()
      }
    } catch (cause) {
      setError(describeApiError(cause))
      onResync()
    } finally {
      setLifecycle(null)
    }
  }, [classId, lifecycle, onResync, onSnapshot, pending, sessionState, stateVersion])

  const canControl =
    Boolean(presentation?.available) && running && Boolean(presentation?.running) && !presentation?.at_end
  const canStart =
    Boolean(presentation?.available) && running && presentation?.running === false

  const togglePresentation = useCallback(async () => {
    if (!presentation?.available || !running || control !== null) return
    const action = presentation.paused || !presentation.running ? 'resume' : 'pause'
    setControl(action)
    setError(null)
    try {
      const next =
        action === 'pause'
          ? await pausePresentation(classId)
          : await resumePresentation(classId)
      setPresentation(next)
      setPresentationError(null)
      if (!next.running) onResync()
    } catch (cause) {
      setError(describeApiError(cause))
      // The runner may have ended between the read and the click; re-read the
      // authoritative status and snapshot rather than guessing.
      setPresentationRevision((value) => value + 1)
      onResync()
    } finally {
      setControl(null)
    }
  }, [classId, control, onResync, presentation, running])

  // Hear the server runner's generation on this page. This is relay mode: it
  // starts no synthesis, so an open teacher tab costs no extra provider work.
  const narration = useNarrationPlayer({
    classId,
    enabled:
      voice &&
      running &&
      scene !== null &&
      Boolean(presentation?.available) &&
      !presentation?.paused,
    mode: 'relay',
    expectedSceneId: scene?.scene_id,
    createSink: createAudioSink,
    retryMs: 750,
  })

  if (sessionState === null) {
    return (
      <section
        data-testid="teacher-stage"
        className="mb-6 rounded-2xl border border-slate-200/85 bg-white p-5 sm:p-6 shadow-[0_1px_3px_rgba(0,0,0,0.03),0_6px_16px_rgba(0,0,0,0.02)]"
      >
        <div className="flex items-center gap-2 border-b border-slate-100 pb-2.5">
          <span className="flex h-2.5 w-2.5 rounded-full bg-slate-300" />
          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-700">Presenting</h2>
        </div>
        <p className="mt-3 text-sm text-slate-600">
          This class has not started. Start it from class management; once running, the class
          server presents its pinned slides automatically and students can join.
        </p>
      </section>
    )
  }

  if (!shouldLoad) {
    return (
      <section
        data-testid="teacher-stage"
        className="mb-6 rounded-2xl border border-slate-200/85 bg-white p-5 sm:p-6 shadow-[0_1px_3px_rgba(0,0,0,0.03),0_6px_16px_rgba(0,0,0,0.02)]"
      >
        <div className="flex items-center gap-2 border-b border-slate-100 pb-2.5">
          <span className="flex h-2.5 w-2.5 rounded-full bg-amber-400" />
          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-700">Presenting</h2>
        </div>
        <p className="mt-3 text-sm text-slate-600">
          This class is <span className="font-mono font-semibold text-slate-800">{sessionState}</span>. The class server presents
          the pinned slides while the session is running.
        </p>
      </section>
    )
  }

  return (
    <section
      data-testid="teacher-stage"
      className="mb-6 rounded-2xl border border-slate-200/85 bg-white p-4 sm:p-6 shadow-[0_1px_3px_rgba(0,0,0,0.03),0_6px_16px_rgba(0,0,0,0.02)]"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
        <div className="flex items-center gap-2.5">
          <span className="flex h-2 w-2 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
          </span>
          <h2 className="text-base font-bold tracking-tight text-slate-900">Presenting</h2>
          <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-semibold text-slate-700" data-testid="teacher-slide-counter">
            {index >= 0 ? `Slide ${index + 1} of ${scenes.length}` : 'No slide'}
          </span>
        </div>
        <div className="flex items-center gap-2 ml-auto">
          <span className="text-xs text-slate-500 font-medium" data-testid="presentation-status">
            {describePresentation(presentation, presentationError, running)}
          </span>
          {canControl && (
            <button
              type="button"
              onClick={() => void togglePresentation()}
              disabled={control !== null}
              className={BUTTON_SECONDARY}
            >
              {control === 'pause' ? 'Pausing…' : presentation?.paused ? 'Resume' : 'Pause'}
            </button>
          )}
          {canStart && (
            <button
              type="button"
              onClick={() => void togglePresentation()}
              disabled={control !== null}
              className={BUTTON_SECONDARY}
            >
              {control === 'resume' ? 'Starting…' : 'Start presentation'}
            </button>
          )}
        </div>
      </div>

      {presentation?.available && running && (
        <div
          className="mt-3 flex flex-wrap items-center gap-2 rounded-xl bg-slate-50 p-2.5 text-xs text-slate-600 border border-slate-200/80"
          data-testid="teacher-voice"
        >
          <div className="flex items-center gap-0.5 h-3 px-0.5" aria-hidden="true">
            <span className="w-0.5 bg-indigo-500 rounded-full animate-wave-1" />
            <span className="w-0.5 bg-indigo-500 rounded-full animate-wave-2" />
            <span className="w-0.5 bg-indigo-500 rounded-full animate-wave-3" />
          </div>
          <span className="font-medium">
            Voice: {describeNarration(narration.status, Boolean(presentation.paused))}
            {narration.provider === 'neutral-deterministic' &&
              ' · neutral-deterministic development mock (tones, not speech; DEC-TECH-007 is OPEN)'}
            {narration.provider === 'omnivoice' &&
              ' · OmniVoice local prototype (not a decided provider; DEC-TECH-007 is OPEN)'}
          </span>
          {narration.status === 'blocked' && (
            <button type="button" onClick={narration.enable} className={`${BUTTON_SECONDARY} ml-auto`}>
              Enable sound
            </button>
          )}
        </div>
      )}
      {voice && narration.fallbackText && (
        <div className="mt-3" data-testid="teacher-voice-fallback">
          <Banner tone="neutral">
            Speech is unavailable for this slide, so its script is shown instead:{' '}
            {narration.fallbackText}
          </Banner>
        </div>
      )}
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

      <div className="mt-4 flex items-center justify-center rounded-2xl bg-slate-950 p-2 sm:p-4 shadow-inner ring-1 ring-white/10">
        {url ? (
          <img
            src={url}
            alt={index >= 0 ? `Slide ${index + 1}` : 'Class slide'}
            className="h-auto max-h-[62vh] w-full object-contain rounded-lg shadow-2xl"
          />
        ) : (
          <div className="p-8 text-center">
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

          <button
            type="button"
            onClick={() => void endNow()}
            disabled={pending || lifecycle !== null}
            className={BUTTON_SECONDARY}
          >
            {lifecycle === 'end' ? 'Ending…' : 'End class'}
          </button>
        </div>
      ) : (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <p role="status" className="min-w-0 flex-1 text-sm text-slate-600">
            {sessionState === 'COMPLETED'
              ? 'This class has ended. The class server stopped presenting, and students are locked out until you reopen it.'
              : 'This class has ended. There is no background presentation to drive.'}
          </p>
          {sessionState === 'COMPLETED' && (
            <button
              type="button"
              onClick={() => void reopenNow()}
              disabled={pending || lifecycle !== null}
              className={BUTTON_SECONDARY}
            >
              {lifecycle === 'reopen' ? 'Reopening…' : 'Reopen class'}
            </button>
          )}
        </div>
      )}
    </section>
  )
}

/** The first line of a slide, for the teacher's slide picker. */
function firstLine(scene: ClassScene): string {
  const line = scene.text.find((value) => value.trim())
  return line ? line.trim().slice(0, 40) : ''
}

/** A stable id for one command; the aggregate uses it for idempotency. */
function newCommandId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `cmd-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function describePresentation(
  status: PresentationStatus | null,
  error: string | null,
  running: boolean,
): string {
  if (!running) return 'Presentation stopped'
  if (error) return 'Presentation status unavailable'
  if (!status) return 'Connecting to the class presenter…'
  if (!status.available) return 'Background presentation is disabled'
  if (status.paused) return 'Paused'
  if (!status.running) return 'Not presenting'
  if (status.at_end) return 'At the last slide'
  return 'Auto-presenting'
}

function describeNarration(status: string, paused: boolean): string {
  if (paused) return 'paused with the class'
  switch (status) {
    case 'loading':
      return 'preparing…'
    case 'playing':
      return 'speaking'
    case 'blocked':
      return 'the browser blocked sound until you allow it'
    case 'completed':
      return 'slide narrated'
    case 'fallback':
      return 'text fallback (speech unavailable)'
    case 'empty':
      return 'this slide has no script'
    case 'error':
      return 'unavailable'
    default:
      return 'waiting for the class presenter'
  }
}
