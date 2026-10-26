import { useEffect, useRef, useState } from 'react'
import {
  ApiError,
  describeApiError,
  issueBootstrapToken,
  loadClass,
  loadClassScenes,
  loadSnapshot,
  type ClassScene,
  type ClassSceneList,
  type ClassView,
} from '../api/client'
import { describePrincipal, useSession } from '../auth/session'
import { useInstitution } from '../institution'
import PageHeader from '../components/PageHeader'
import { Badge, Banner, BUTTON_SECONDARY, EmptyState } from '../components/ui'
import { usePinnedSlide } from '../classroom/usePinnedSlide'
import { sceneOrderFor } from '../classroom/scenePosition'
import { useNarrationPlayer, type AudioSink } from '../audio/useNarrationPlayer'
import { CLASSROOM_PATH, Link, joinPath } from '../router'

type FollowPhase = 'loading' | 'waiting' | 'live' | 'ended' | 'error'

export interface StudentClassPageProps {
  classId: string
  /**
   * How often the page re-reads the authoritative snapshot while following.
   * Injectable for tests; the product interval is 1.5 s.
   */
  followPollMs?: number
  /**
   * How long the voice relay waits before attaching again when the teacher is
   * not speaking. Injectable for tests; the product interval is 750 ms.
   */
  narrationRetryMs?: number
  /** Injectable audio sink for component tests. */
  createAudioSink?: () => AudioSink
}

/**
 * The student's view of a running class — `/student/{classId}` (V0-021/V0-025).
 *
 * This is a **viewer**, not a second copy of the lesson. The teacher advances the
 * class's pinned slide; this page reads the same authoritative session snapshot
 * and shows the scene the snapshot names. It has no previous/next buttons, no
 * slide picker and no arrow-key navigation — a student cannot move the class, and
 * cannot fall out of step with it either.
 *
 * It is built for the device a student actually holds: the slide fills the
 * viewport, the read-only status is ≥44px where it is tappable, and the teacher's
 * large-screen layout is untouched.
 *
 * What it must not overstate:
 *
 * * **The update is a short poll, not a live stream.** The ordered per-class
 *   event stream that would carry "the teacher moved to slide 4" is
 *   `DEC-DATA-003` (technology `OPEN`; live path V1-002). This page re-reads the
 *   authoritative snapshot about every 1.5 seconds and says so.
 * * **Narration is the teacher's live generation, relayed over HTTP** (V0-013's
 *   synthesis + the V1-005 in-process bridge), not a per-student synthesis and
 *   not a transcript. The canonical shared-audio path is still the SFU
 *   (`DEC-TECH-004` `OPEN`), so this is a development relay: it is single-process
 *   and best-effort, and says so. The slide's own text stays behind a collapsed
 *   accessibility disclosure, never shown by default.
 *
 * What *is* authoritative is the content: every scene comes from the package the
 * session pinned at start (`DEC-CONTENT-005`), so a correction published during
 * the lesson cannot change the slide under the student, and a tampered file is
 * refused rather than shown. The page also refuses to start following a class
 * the student is not on the roster of — the server enforces that on every read.
 */
export default function StudentClassPage({
  classId,
  followPollMs = 1500,
  narrationRetryMs = 750,
  createAudioSink,
}: StudentClassPageProps) {
  const session = useSession()
  const [, setInstitution] = useInstitution()
  const [classView, setClassView] = useState<ClassView | null>(null)
  const [listing, setListing] = useState<ClassSceneList | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [order, setOrder] = useState<number | null>(null)
  const [phase, setPhase] = useState<FollowPhase>('loading')
  const [error, setError] = useState<string | null>(null)
  const [syncError, setSyncError] = useState<string | null>(null)
  const [followKey, setFollowKey] = useState(0)
  const stage = useRef<HTMLDivElement | null>(null)

  const institutionId = session?.principal.institution_id ?? ''
  const scenes = listing?.scenes ?? []
  const scene: ClassScene | null =
    (order === null ? null : scenes.find((item) => item.order === order)) ?? scenes[0] ?? null
  const index = scene ? scenes.findIndex((item) => item.order === scene.order) : -1
  const narration = useNarrationPlayer({
    classId,
    enabled: phase === 'live' && listing !== null,
    mode: 'relay',
    expectedSceneId: scene?.scene_id,
    retryMs: narrationRetryMs,
    createSink: createAudioSink,
  })
  const { url: slideUrl, error: slideError } = usePinnedSlide(
    classId,
    listing && scene ? scene.order : null,
  )

  useEffect(() => {
    document.title = 'Class — Mentora'
  }, [])

  useEffect(() => {
    if (session) setInstitution(session.principal.institution_id)
  }, [session, setInstitution])

  // The lifecycle: wait for the teacher to start, join once the class is running,
  // and show the ended lock screen after it ends. A student may see *that* the
  // class ended, but the lesson itself — the snapshot and the pinned slides — is
  // refused by the server until a teacher reopens it. This page keeps checking the
  // class metadata (not its content) so a reopen joins by itself.
  useEffect(() => {
    let cancelled = false
    let timer: number | undefined

    function markEnded(view: ClassView | null) {
      if (view) setClassView(view)
      setListing(null)
      setOrder(null)
      setToken(null)
      setSyncError(null)
      setError(null)
      setPhase('ended')
    }

    async function join(view: ClassView) {
      const issued = await issueBootstrapToken(classId)
      if (cancelled) return
      const scenes = await loadClassScenes(classId)
      if (cancelled) return
      const snapshot = await loadSnapshot(institutionId, classId)
      if (cancelled) return
      setClassView(view)
      setToken(issued.token)
      setListing(scenes)
      setOrder(sceneOrderFor(scenes.scenes, snapshot) ?? scenes.scenes[0]?.order ?? null)
      setPhase('live')
    }

    async function tick() {
      try {
        const view = await loadClass(institutionId, classId)
        if (cancelled) return
        setClassView(view)
        const state = view.class.state
        if (state === 'ACTIVE' || state === 'DEGRADED') {
          await join(view)
          return
        }
        if (state === 'COMPLETED' || state === 'FAILED' || state === 'ENDING') {
          markEnded(view)
          // Keep watching the metadata: a reopened class returns to ACTIVE and
          // the student joins the new epoch without a manual refresh.
          timer = window.setTimeout(() => void tick(), followPollMs)
          return
        }
        // SCHEDULED / PREPARING / RECOVERING / anything not yet runnable: the
        // teacher has not started the class, so there is nothing to join. Keep
        // checking; joining before the start is refused by the API as well.
        setPhase('waiting')
        timer = window.setTimeout(() => void tick(), followPollMs)
      } catch (cause) {
        if (cancelled) return
        if (isEnded(cause)) {
          markEnded(null)
          timer = window.setTimeout(() => void tick(), followPollMs)
          return
        }
        if (isNotStarted(cause)) {
          setPhase('waiting')
          timer = window.setTimeout(() => void tick(), followPollMs)
          return
        }
        setError(describeApiError(cause))
        setPhase('error')
      }
    }

    void tick()
    return () => {
      cancelled = true
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [classId, followKey, followPollMs, institutionId])

  // While teaching, the snapshot is the only truth. Read it again on a short
  // interval and move the student to the scene the teacher is on. A failure does
  // not let the view drift silently: it says the sync is behind and keeps the last
  // authoritative scene visible while it retries.
  useEffect(() => {
    if (phase !== 'live' || !listing) return
    const sceneList = listing.scenes
    let cancelled = false
    let timer: number | undefined

    function markEnded() {
      setListing(null)
      setOrder(null)
      setToken(null)
      setSyncError(null)
      setPhase('ended')
      // Re-arm the lifecycle effect, which now watches the metadata for a reopen.
      setFollowKey((value) => value + 1)
    }

    // One poll at a time: a slow request must not overlap the next one and let an
    // older snapshot arrive last and move the slide backwards.
    async function poll() {
      try {
        const snapshot = await loadSnapshot(institutionId, classId)
        if (cancelled) return
        const next = sceneOrderFor(sceneList, snapshot)
        if (next !== null) {
          setOrder(next)
          setSyncError(null)
        } else {
          setSyncError('The class is on a slide this package does not list.')
        }
        if (
          snapshot.state === 'COMPLETED' ||
          snapshot.state === 'FAILED' ||
          snapshot.state === 'ENDING'
        ) {
          markEnded()
          return
        }
      } catch (cause) {
        if (cancelled) return
        if (isEnded(cause)) {
          markEnded()
          return
        }
        setSyncError(describeApiError(cause))
      }
      if (!cancelled) timer = window.setTimeout(() => void poll(), followPollMs)
    }

    timer = window.setTimeout(() => void poll(), followPollMs)
    return () => {
      cancelled = true
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [classId, followPollMs, institutionId, listing, phase])

  async function enterFullscreen() {
    const element = stage.current
    if (!element) return
    try {
      await element.requestFullscreen()
    } catch {
      // A browser may refuse (no user gesture, or the API is absent). The slide
      // is already the page's whole content, so nothing is lost.
    }
  }

  const title = classView?.class.title ?? 'Class'
  const subtitle = classView
    ? `${classView.class.title} · ${phase === 'live' ? 'following your teacher' : phase}`
    : classId

  return (
    <div className="flex min-h-screen flex-col bg-slate-900 text-slate-100">
      <div className="print:hidden" data-testid="student-chrome">
        <PageHeader
          nav="student"
          title="Class"
          subtitle={subtitle}
          classId={classId}
          institution={institutionId}
          onInstitutionChange={() => undefined}
        />
      </div>

      <main className="flex flex-1 flex-col">
        {error && (
          <div className="p-3 sm:p-4">
            <Banner tone="bad">{error}</Banner>
            <p className="mt-2 text-sm text-slate-300">
              If you are not on this class&apos;s roster, ask your teacher to add you; then{' '}
              <Link to={joinPath(classId)} className="text-indigo-300 underline">
                open the join page
              </Link>
              .
            </p>
          </div>
        )}

        {phase === 'loading' && !error && (
          <p className="p-4 text-sm text-slate-300">Opening the class…</p>
        )}

        {phase === 'waiting' && (
          <div className="mx-auto mt-6 max-w-2xl p-3 sm:p-4">
            <Banner tone="info">
              <strong>{title}</strong> has not started yet. Waiting for your teacher to start the
              class…
            </Banner>
            <p className="mt-3 text-sm text-slate-300">
              This page checks again every {Math.round(followPollMs / 1000) || 1} second
              {followPollMs >= 2000 ? 's' : ''}. It will join by itself when the teacher starts;
              you do not need to refresh.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Link to={CLASSROOM_PATH} className={BUTTON_SECONDARY}>
                Classroom
              </Link>
              <Link to={joinPath(classId)} className={BUTTON_SECONDARY}>
                Open the join page
              </Link>
            </div>
          </div>
        )}

        {phase === 'live' && listing && (
          <>
            {syncError && (
              <div className="px-3 pt-3 sm:px-4">
                <Banner tone="warn">
                  The class view is behind: {syncError} The last slide from the class is still
                  shown while the page retries.
                </Banner>
              </div>
            )}

            {slideError && (
              <div className="px-3 pt-3 sm:px-4">
                <Banner tone="bad">{slideError}</Banner>
              </div>
            )}

            <div ref={stage} className="relative flex flex-1 items-center justify-center bg-slate-950 p-2 sm:p-4">
              {slideUrl ? (
                <div className="relative overflow-hidden rounded-xl bg-black shadow-2xl ring-1 ring-white/10">
                  <img
                    src={slideUrl}
                    alt={scene ? `Slide ${index + 1}` : 'Class slide'}
                    className="h-auto max-h-[82vh] w-full max-w-full object-contain"
                  />
                </div>
              ) : (
                <div className="p-8 text-center">
                  <EmptyState>{slideError ? 'This slide cannot be shown.' : 'Loading the slide…'}</EmptyState>
                </div>
              )}
            </div>

            <div className="border-t border-slate-800 bg-slate-900/95 px-4 py-3 sm:px-6 shadow-xs backdrop-blur-md">
              <div className="flex flex-wrap items-center gap-2.5">
                <span className="flex h-2 w-2 relative">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                </span>
                <span
                  role="status"
                  aria-live="polite"
                  className="text-sm font-semibold text-slate-100"
                  data-testid="student-slide-counter"
                >
                  Following your teacher · Slide {index + 1} / {scenes.length}
                </span>
                {scene?.fidelity && (
                  <Badge tone={scene.fidelity === 'DEGRADED_RENDERED' ? 'warn' : 'neutral'}>
                    {scene.fidelity}
                  </Badge>
                )}
                <button
                  type="button"
                  onClick={() => void enterFullscreen()}
                  className={`${BUTTON_SECONDARY} ml-auto`}
                >
                  Fullscreen
                </button>
              </div>
              <p className="mt-1 text-[11px] text-slate-400">
                The slide moves when your teacher moves theirs. This page follows the class state
                by a short poll, not a pushed live stream (V1-002).
              </p>
            </div>

            <section className="border-t border-slate-800 bg-slate-900 px-4 py-3.5 sm:px-6">
              <div
                className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 text-sm text-slate-200"
                data-testid="student-voice"
              >
                {/* Audio visualizer */}
                <div className="flex items-center gap-0.5 h-4 px-1" aria-hidden="true">
                  <span className="w-1 bg-indigo-400 rounded-full animate-wave-1" />
                  <span className="w-1 bg-indigo-400 rounded-full animate-wave-2" />
                  <span className="w-1 bg-indigo-400 rounded-full animate-wave-3" />
                  <span className="w-1 bg-indigo-400 rounded-full animate-wave-4" />
                </div>
                <span className="font-medium">Voice: {describeRelayNarration(narration.status)}</span>
                {narration.provider === 'neutral-deterministic' && (
                  <span className="text-[11px] text-slate-400 bg-slate-800 px-2 py-0.5 rounded">
                    neutral-deterministic development mock (tones, not speech; DEC-TECH-007 is
                    OPEN)
                  </span>
                )}
                {narration.provider === 'omnivoice' && (
                  <span className="text-[11px] text-slate-400 bg-slate-800 px-2 py-0.5 rounded">
                    OmniVoice local prototype (not a decided provider; DEC-TECH-007 is OPEN)
                  </span>
                )}
                {narration.status === 'blocked' && (
                  <button
                    type="button"
                    onClick={narration.enable}
                    className={BUTTON_SECONDARY}
                  >
                    Enable sound
                  </button>
                )}
              </div>
              {(narration.error || narration.fallbackText) && (
                <div className="mt-2">
                  <Banner tone={narration.error ? 'bad' : 'neutral'}>
                    {narration.error
                      ? `The live voice is unavailable: ${narration.error}`
                      : 'The live voice is unavailable for this slide; its text is in the accessibility disclosure below.'}
                  </Banner>
                </div>
              )}
              <p className="mt-1 text-[11px] text-slate-400" data-testid="student-voice-note">
                Your teacher&apos;s narration is relayed to this page while the class runs. A
                slide you join mid-way is replayed from its start; the teacher&apos;s next slide
                replaces it. This is the development HTTP relay, not the SFU media plane (V1-005;
                DEC-TECH-004 is OPEN). The slide shown is the one being presented and this page
                does not offer slide navigation.
                {session && ` Signed in as ${describePrincipal(session)}.`}
              </p>
              {scene && (scene.text.length > 0 || scene.notes) && (
                <details className="mt-2 text-sm text-slate-200" data-testid="student-slide-text">
                  <summary className="cursor-pointer text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                    Show slide text (accessibility)
                  </summary>
                  <div className="mt-2 space-y-2">
                    <ul className="list-disc space-y-1 pl-5">
                      {scene.text.map((line, position) => (
                        <li key={`${position}-${line}`}>{line}</li>
                      ))}
                    </ul>
                    {scene.notes && (
                      <p className="rounded-lg bg-slate-900 px-3 py-2 text-slate-300">
                        <span className="text-[11px] uppercase tracking-wide text-slate-500">Notes · </span>
                        {scene.notes}
                      </p>
                    )}
                  </div>
                </details>
              )}
            </section>
          </>
        )}

        {phase === 'ended' && !listing && (
          <div className="mx-auto mt-6 max-w-2xl p-3 sm:p-4">
            <Banner tone="neutral">
              <strong>{title}</strong> has ended. The lesson is locked until your teacher reopens
              it.
            </Banner>
            <p className="mt-3 text-sm text-slate-300">
              There is no slide or text to show while the class is closed. This page checks again
              automatically; when your teacher reopens the class it will join by itself.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Link to={CLASSROOM_PATH} className={BUTTON_SECONDARY}>
                Classroom
              </Link>
            </div>
          </div>
        )}

        {!error && phase !== 'loading' && phase !== 'waiting' && phase !== 'ended' && !listing && (
          <div className="p-4">
            <EmptyState>No slides.</EmptyState>
          </div>
        )}
      </main>

      {/* A quiet footer: which class this is, and whether the join succeeded. */}
      <footer className="border-t border-slate-800 px-3 py-2 text-[11px] text-slate-500 sm:px-4">
        Class <span className="font-mono">{classId}</span>
        {token && ' · joined (credential held in memory only)'}
      </footer>
    </div>
  )
}

/** The student-facing words for the relay's state. */
function describeRelayNarration(status: string): string {
  switch (status) {
    case 'waiting':
      return 'waiting for your teacher to speak'
    case 'loading':
      return 'connecting to your teacher'
    case 'playing':
      return 'live'
    case 'blocked':
      return 'the browser blocked sound until you allow it'
    case 'completed':
      return 'this slide has been narrated'
    case 'fallback':
      return 'speech is unavailable; the slide text is available below'
    case 'empty':
      return 'this slide has no narration'
    case 'error':
      return 'unavailable'
    default:
      return 'off'
  }
}

/** A refusal that means the class has ended and its lesson is locked. */
function isEnded(cause: unknown): boolean {
  return cause instanceof ApiError && cause.issueCode === 'CLASS_ENDED'
}

/** A refusal that means "not started yet" rather than "cannot join this class". */
function isNotStarted(cause: unknown): boolean {
  return (
    cause instanceof ApiError &&
    !isEnded(cause) &&
    (cause.issueCode === 'NOT_STARTED' || cause.code === 'CLASS_NOT_READY')
  )
}
