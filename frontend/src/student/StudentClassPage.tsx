import { useCallback, useEffect, useRef, useState } from 'react'
import {
  classSceneUrl,
  describeApiError,
  issueBootstrapToken,
  loadClassScenes,
  type ClassScene,
  type ClassSceneList,
} from '../api/client'
import { describePrincipal, useSession } from '../auth/session'
import { useInstitution } from '../institution'
import PageHeader from '../components/PageHeader'
import { Badge, Banner, BUTTON_SECONDARY, EmptyState } from '../components/ui'
import { Link, joinPath } from '../router'

/**
 * The student's view of a running class — `/student/{classId}` (V0-021).
 *
 * It is built for the device a student actually holds: the slide fills the
 * viewport ("fullscreen" is a real button as well as a layout, because a phone
 * browser still shows its own chrome otherwise), one tap moves a slide, and the
 * controls are ≥44px. The teacher's large-screen layout is untouched — this is a
 * separate page, not a compressed version of the studio.
 *
 * Two properties it must not overstate:
 *
 * * **The slide shown is the one *this student* is looking at, not the one the
 *   teacher is on.** Nothing on this page is live: the ordered per-class event
 *   stream that would carry "the teacher moved to slide 4" is `DEC-DATA-003`
 *   (its technology is `OPEN`, the live path is V1-002), so the page reads the
 *   class's pinned package and lets the student navigate it. It says so.
 * * **There is no teacher** — the narration is the deck's own authored text, in
 *   text form. No model wrote it, and it is not audio: no LLM exists in this
 *   slice and the voice provider is `DEC-TECH-007` (`OPEN`); what runs is a
 *   client-local timer over the deck's text.
 *
 * What *is* authoritative is the content: every scene comes from the package the
 * session pinned at start (`DEC-CONTENT-005`), so a correction published during
 * the lesson cannot change the slide under the student, and a tampered file is
 * refused rather than shown.
 */
export default function StudentClassPage({ classId }: { classId: string }) {
  const session = useSession()
  const [, setInstitution] = useInstitution()
  const [listing, setListing] = useState<ClassSceneList | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [order, setOrder] = useState(0)
  const [slideUrl, setSlideUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(true)
  const stage = useRef<HTMLDivElement | null>(null)
  // The object URL currently on screen, so it can be released when it changes.
  const liveUrl = useRef<string | null>(null)

  useEffect(() => {
    document.title = 'Class — Mentora'
  }, [])

  useEffect(() => {
    if (session) setInstitution(session.principal.institution_id)
  }, [session, setInstitution])

  // Joining is what authorizes the read, so the credential is requested before
  // the class's slides are loaded. The credential itself is not stored: a
  // refresh asks for a fresh one, which the API issues idempotently.
  useEffect(() => {
    let cancelled = false
    void (async () => {
      setBusy(true)
      setError(null)
      try {
        const issued = await issueBootstrapToken(classId)
        const scenes = await loadClassScenes(classId)
        if (cancelled) return
        setToken(issued.token)
        setListing(scenes)
        setOrder(scenes.scenes[0]?.order ?? 0)
      } catch (cause) {
        if (!cancelled) setError(describeApiError(cause))
      } finally {
        if (!cancelled) setBusy(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [classId])

  // Load one slide's render. The previous object URL is revoked, so a student
  // paging through a deck does not grow the tab's memory.
  useEffect(() => {
    if (!listing) return
    let cancelled = false
    void (async () => {
      try {
        const url = await classSceneUrl(classId, order)
        if (cancelled) {
          URL.revokeObjectURL(url)
          return
        }
        if (liveUrl.current) URL.revokeObjectURL(liveUrl.current)
        liveUrl.current = url
        setSlideUrl(url)
      } catch (cause) {
        if (!cancelled) setError(describeApiError(cause))
      }
    })()
    return () => {
      cancelled = true
    }
  }, [classId, listing, order])

  useEffect(
    () => () => {
      if (liveUrl.current) URL.revokeObjectURL(liveUrl.current)
    },
    [],
  )

  const scenes = listing?.scenes ?? []
  const index = Math.max(
    0,
    scenes.findIndex((scene) => scene.order === order),
  )
  const scene: ClassScene | null = scenes[index] ?? null

  const go = useCallback(
    (delta: number) => {
      const next = scenes[index + delta]
      if (next) setOrder(next.order)
    },
    [index, scenes],
  )

  // Arrow keys are the fastest way through a deck on a laptop; on a phone the
  // buttons are. Both are offered.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === 'ArrowRight' || event.key === 'PageDown') go(1)
      if (event.key === 'ArrowLeft' || event.key === 'PageUp') go(-1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [go])

  async function enterFullscreen() {
    const element = stage.current
    if (!element) return
    try {
      await element.requestFullscreen()
    } catch {
      // A browser may refuse (no user gesture, or the API is absent). The slide
      // is already the page's whole content, so nothing is lost.
      setError('This browser would not enter fullscreen; the slide is already full-width.')
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-slate-900 text-slate-100">
      <div className="print:hidden" data-testid="student-chrome">
        <PageHeader
          nav="student"
          title="Class"
          subtitle={listing ? `${scenes.length} slides` : classId}
          classId={classId}
          institution={session?.principal.institution_id ?? ''}
          onInstitutionChange={() => undefined}
        />
      </div>

      <main className="flex flex-1 flex-col">
        {error && (
          <div className="p-3 sm:p-4">
            <Banner tone="bad">{error}</Banner>
            <p className="mt-2 text-sm text-slate-300">
              If you are not on this class's roster, ask your teacher to add you; then{' '}
              <Link to={joinPath(classId)} className="text-indigo-300 underline">
                open the join page
              </Link>
              .
            </p>
          </div>
        )}

        {busy && !listing && !error && <p className="p-4 text-sm text-slate-300">Joining…</p>}

        {listing && (
          <>
            <div ref={stage} className="flex flex-1 items-center justify-center bg-black p-0">
              {slideUrl ? (
                <img
                  src={slideUrl}
                  alt={scene ? `Slide ${scene.order + 1}` : 'Class slide'}
                  className="h-auto max-h-[85vh] w-full max-w-full object-contain"
                />
              ) : (
                <div className="p-6">
                  <EmptyState>Loading the slide…</EmptyState>
                </div>
              )}
            </div>

            <div className="border-t border-slate-700 bg-slate-900 px-3 py-2 sm:px-4">
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => go(-1)}
                  disabled={index === 0}
                  className={`${BUTTON_SECONDARY} disabled:opacity-30`}
                >
                  ← Previous
                </button>
                <span className="text-sm text-slate-300" data-testid="student-slide-counter">
                  Slide {index + 1} / {scenes.length}
                </span>
                <button
                  type="button"
                  onClick={() => go(1)}
                  disabled={index >= scenes.length - 1}
                  className={`${BUTTON_SECONDARY} disabled:opacity-30`}
                >
                  Next →
                </button>

                <button
                  type="button"
                  onClick={() => void enterFullscreen()}
                  className={BUTTON_SECONDARY}
                >
                  Fullscreen
                </button>

                {scene?.fidelity && (
                  <Badge tone={scene.fidelity === 'DEGRADED_RENDERED' ? 'warn' : 'neutral'}>
                    {scene.fidelity}
                  </Badge>
                )}
              </div>

              {/*
                The slide picker is on its own row and is explicitly allowed to
                shrink (`min-w-0` + `max-w-full`): a `<select>`'s intrinsic width
                is its longest option, so a long slide title would otherwise widen
                the whole page on a phone rather than being clipped.
              */}
              <label className="mt-2 block w-full min-w-0 max-w-full text-xs text-slate-400 lg:mt-0 lg:inline-block lg:w-auto lg:max-w-xs">
                <span className="sr-only">Slide</span>
                <select
                  aria-label="Slide"
                  value={order}
                  onChange={(event) => setOrder(Number(event.target.value))}
                  className="w-full min-w-0 max-w-full rounded-md border border-slate-600 bg-slate-800 px-2 py-2 text-base text-slate-100 lg:text-xs"
                >
                  {scenes.map((item, position) => (
                    <option key={item.scene_id} value={item.order}>
                      {position + 1}. {firstLine(item) || item.scene_id}
                    </option>
                  ))}
                </select>
              </label>
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
                <strong>Text only</strong>, and this deck's own words — no model wrote it and it is not
                audio. The slide shown is the one <em>you</em> are on: this page is not live (the ordered
                class event stream is still an open decision), so it does not follow the teacher.
                {session && ` Signed in as ${describePrincipal(session)}.`}
              </p>
            </section>
          </>
        )}

        {!listing && !busy && !error && (
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

/** The first line of a slide, for the slide picker. */
function firstLine(scene: ClassScene): string {
  const line = scene.text.find((value) => value.trim())
  return line ? line.trim().slice(0, 40) : ''
}
