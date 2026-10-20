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
import { Link, joinPath, STUDENT_PATH } from '../router'

type FollowPhase = 'loading' | 'waiting' | 'live' | 'ended' | 'error'

export interface StudentClassPageProps {
  classId: string
  /**
   * How often the page re-reads the authoritative snapshot while following.
   * Injectable for tests; the product interval is 1.5 s.
   */
  followPollMs?: number
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
 * * **The narration is the deck's own authored text**, in text form. No model
 *   wrote it, and it is not audio: no LLM exists in this slice and the voice
 *   provider is `DEC-TECH-007` (`OPEN`).
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
  const stage = useRef<HTMLDivElement | null>(null)

  const institutionId = session?.principal.institution_id ?? ''
  const scenes = listing?.scenes ?? []
  const scene: ClassScene | null =
    (order === null ? null : scenes.find((item) => item.order === order)) ?? scenes[0] ?? null
  const index = scene ? scenes.findIndex((item) => item.order === scene.order) : -1
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
  // and load the snapshot that names the current slide. A class that is already
  // over can still be read (the snapshot and pinned slides outlive the session),
  // but it is not joined and has no live presentation.
  useEffect(() => {
    let cancelled = false
    let timer: number | undefined

    async function loadFinal(view: ClassView) {
      const scenes = await loadClassScenes(classId)
      if (cancelled) return
      const snapshot = await loadSnapshot(institutionId, classId)
      if (cancelled) return
      setClassView(view)
      setListing(scenes)
      setOrder(sceneOrderFor(scenes.scenes, snapshot) ?? scenes.scenes[0]?.order ?? null)
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
          await loadFinal(view)
          return
        }
        // SCHEDULED / PREPARING / RECOVERING / anything not yet runnable: the
        // teacher has not started the class, so there is nothing to join. Keep
        // checking; joining before the start is refused by the API as well.
        setPhase('waiting')
        timer = window.setTimeout(() => void tick(), followPollMs)
      } catch (cause) {
        if (cancelled) return
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
  }, [classId, followPollMs, institutionId])

  // While teaching, the snapshot is the only truth. Read it again on a short
  // interval and move the student to the scene the teacher is on. A failure does
  // not let the view drift silently: it says the sync is behind and keeps the last
  // authoritative scene visible while it retries.
  useEffect(() => {
    if (phase !== 'live' || !listing) return
    const sceneList = listing.scenes
    let cancelled = false
    let timer: number | undefined

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
        if (snapshot.state === 'COMPLETED' || snapshot.state === 'FAILED') {
          setPhase('ended')
          return
        }
      } catch (cause) {
        if (cancelled) return
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
              <Link to={STUDENT_PATH} className={BUTTON_SECONDARY}>
                My classes
              </Link>
              <Link to={joinPath(classId)} className={BUTTON_SECONDARY}>
                Open the join page
              </Link>
            </div>
          </div>
        )}

        {(phase === 'live' || phase === 'ended') && listing && (
          <>
            {phase === 'ended' && (
              <div className="p-3 sm:p-4">
                <Banner tone="neutral">
                  This class has ended. This is the last slide your teacher presented.
                </Banner>
              </div>
            )}

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

            <div ref={stage} className="flex flex-1 items-center justify-center bg-black p-0">
              {slideUrl ? (
                <img
                  src={slideUrl}
                  alt={scene ? `Slide ${index + 1}` : 'Class slide'}
                  className="h-auto max-h-[85vh] w-full max-w-full object-contain"
                />
              ) : (
                <div className="p-6">
                  <EmptyState>{slideError ? 'This slide cannot be shown.' : 'Loading the slide…'}</EmptyState>
                </div>
              )}
            </div>

            <div className="border-t border-slate-700 bg-slate-900 px-3 py-2 sm:px-4">
              <div className="flex flex-wrap items-center gap-2">
                <span
                  role="status"
                  aria-live="polite"
                  className="text-sm text-slate-200"
                  data-testid="student-slide-counter"
                >
                  {phase === 'ended' ? 'Last slide' : 'Following your teacher'} · Slide {index + 1}{' '}
                  / {scenes.length}
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
              <p className="mt-1 text-[11px] text-slate-500">
                {phase === 'live'
                  ? 'The slide moves when your teacher moves theirs. This page follows the class state by a short poll, not a pushed live stream (V1-002).'
                  : 'The class is over; there is no live slide to follow.'}
              </p>
            </div>

            <section className="border-t border-slate-700 bg-slate-800 px-3 py-3 sm:px-4">
              <h2 className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                This slide, in text
              </h2>
              {scene && (scene.text.length > 0 || scene.notes) ? (
                <div className="mt-2 space-y-2 text-sm text-slate-200">
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
              ) : (
                <EmptyState>This slide has no text of its own.</EmptyState>
              )}
              <p className="mt-2 text-[11px] text-slate-400">
                <strong>Text only</strong>, and this deck&apos;s own words — no model wrote it and it
                is not audio. The slide shown is the one your teacher is presenting; this page does
                not offer slide navigation.
                {session && ` Signed in as ${describePrincipal(session)}.`}
              </p>
            </section>
          </>
        )}

        {phase === 'ended' && !listing && (
          <div className="p-4">
            <EmptyState>This class has finished and has no slides to show.</EmptyState>
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

/** A refusal that means "not started yet" rather than "cannot join this class". */
function isNotStarted(cause: unknown): boolean {
  return (
    cause instanceof ApiError &&
    (cause.issueCode === 'NOT_STARTED' || cause.code === 'CLASS_NOT_READY')
  )
}
