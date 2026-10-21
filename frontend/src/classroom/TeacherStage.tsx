import { useCallback, useEffect, useState } from 'react'
import {
  describeApiError,
  endClass,
  loadClassScenes,
  navigateClassScene,
  reopenClass,
  type ClassScene,
  type ClassSceneList,
  type SessionSnapshot,
} from '../api/client'
import { Banner, BUTTON_SECONDARY, EmptyState } from '../components/ui'
import { resolveSceneOrder } from './scenePosition'
import { usePinnedSlide } from './usePinnedSlide'
import { dwellForScene } from './playbackTiming'
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
  /** When true the stage automatically advances pinned slides. The tab must stay open. */
  autoPlay?: boolean
  /** The teacher's reading pace (words per minute) used to compute slide dwell. */
  playbackWpm?: number
  /**
   * Speak each slide's pinned script while auto-playing (V0-013). Defaults to on;
   * the slide then advances when its narration has been heard, and falls back to
   * the text-paced dwell only when there is no audio (fallback, empty, error).
   */
  voice?: boolean
  /** Injectable audio output (tests); the default is an `<audio>` element. */
  createAudioSink?: () => AudioSink
}

const RUNNING_STATES = new Set(['ACTIVE', 'DEGRADED'])
const FINISHED_STATES = new Set(['COMPLETED', 'FAILED', 'ENDING'])

/**
 * The teacher's presentation surface (V0-025).
 *
 * When ``autoPlay`` is true and the class is running, the pinned slides advance
 * automatically one after another. The pause / play button toggles the clock.
 * The dwell time for each slide is computed from the slide's text and notes and
 * the teacher's ``playbackWpm`` pace. The teacher can close the tab at any time;
 * closing it stops the auto‑play; no background worker or media stream is started.
 *
 * A command is fenced with the ``state_version`` the page is showing. If another
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
  autoPlay,
  playbackWpm = 160,
  voice = true,
  createAudioSink,
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

  // Auto-play state. The timer is derived from the current slide: one timer is
  // armed at a time, and a new slide (or a pause) replaces it. Nothing runs in a
  // worker or on the server, so closing the tab stops the presentation.
  const [isPlaying, setIsPlaying] = useState(false)

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
          // A refused command means the class moved under this tab; stop playing
          // rather than retrying a stale target, and let the page resynchronise.
          setIsPlaying(false)
          onResync()
        }
      } catch (cause) {
        setError(describeApiError(cause))
        setIsPlaying(false)
        onResync()
      } finally {
        setPending(false)
      }
    },
    [classId, onResync, onSnapshot, pending, running, stateVersion],
  )

  const nextScene =
    index >= 0 && index < scenes.length - 1 ? scenes[index + 1] : null

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
    } catch (cause) {
      setError(describeApiError(cause))
      onResync()
    } finally {
      setIsPlaying(false)
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
        setIsPlaying(Boolean(autoPlay))
      } else if (outcome.result.duplicate) {
        onResync()
      }
    } catch (cause) {
      setError(describeApiError(cause))
      onResync()
    } finally {
      setLifecycle(null)
    }
  }, [autoPlay, classId, lifecycle, onResync, onSnapshot, pending, sessionState, stateVersion])

  // Seed the play flag from `?autoplay=1` once the session is running. A pause
  // made by the teacher survives later scene updates because this only depends
  // on the flag and the running state.
  useEffect(() => {
    setIsPlaying(Boolean(autoPlay) && running)
  }, [autoPlay, running])

  // Voice: narrate the current slide while auto-playing. The slide advances when
  // its narration has been heard; the last slide stops rather than looping.
  const narrating = voice && isPlaying && running && !pending && scene !== null
  const advanceAfterNarration = useCallback(() => {
    if (nextScene) void goTo(nextScene)
    else setIsPlaying(false)
  }, [goTo, nextScene])
  const narration = useNarrationPlayer({
    classId,
    order: scene?.order ?? null,
    enabled: narrating,
    expectedStateVersion: stateVersion,
    onComplete: advanceAfterNarration,
    createSink: createAudioSink,
  })
  // Without audio for this slide (voice off, text fallback, nothing authored, or
  // a failure) the text-paced dwell keeps the lesson moving (DEC-TURN-009).
  const paceByText =
    !voice ||
    narration.status === 'fallback' ||
    narration.status === 'empty' ||
    narration.status === 'error'

  // One timer per slide. When the slide changes (because the command succeeded),
  // the cleanup clears the previous timer and the effect arms the next one.
  useEffect(() => {
    if (!isPlaying || !running || pending) return
    // The scene list is still loading: leave the flag alone, the next render
    // (with a scene) will arm the timer.
    if (!scene) return
    if (!voice && !nextScene) {
      // The last slide has been reached: the lesson is fully presented, not looped.
      setIsPlaying(false)
      return
    }
    if (!paceByText) return
    const timer = window.setTimeout(() => {
      advanceAfterNarration()
    }, dwellForScene(scene, playbackWpm ?? 160))
    return () => window.clearTimeout(timer)
  }, [isPlaying, running, pending, scene, nextScene, playbackWpm, voice, paceByText, advanceAfterNarration])

  const toggleAutoPlay = useCallback(() => {
    setIsPlaying((playing) => !playing)
  }, [])

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
        {autoPlay && (
          <button
            type="button"
            onClick={toggleAutoPlay}
            disabled={!running}
            className={BUTTON_SECONDARY}
          >
            {isPlaying ? 'Pause' : 'Play'}
          </button>
        )}
      </div>

      {voice && autoPlay && running && (
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-600" data-testid="teacher-voice">
          <span>
            Voice: {describeNarration(narration.status, isPlaying)}
            {narration.provider === 'neutral-deterministic' &&
              ' · neutral-deterministic development mock (tones, not speech; DEC-TECH-007 is OPEN)'}
          </span>
          {narration.status === 'blocked' && (
            <button type="button" onClick={narration.enable} className={BUTTON_SECONDARY}>
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
          {!autoPlay && (
            <>
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
            </>
          )}

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
              ? 'This class has ended. Its lesson is locked for students until you reopen it.'
              : 'This class has ended. There is no live presentation to drive.'}
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
function describeNarration(status: string, playing: boolean): string {
  if (!playing) return 'paused'
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
      return 'unavailable; pacing by text'
    default:
      return 'idle'
  }
}
