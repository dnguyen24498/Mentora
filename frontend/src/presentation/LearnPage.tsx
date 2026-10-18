import { useCallback, useEffect, useMemo, useState } from 'react'
import SiteNav from '../components/SiteNav'
import SlideStage from './SlideStage'
import type { AnnotationStroke } from './TeachingCanvas'
import { useInstitution, writeSelectedArtifact } from '../institution'
import {
  ApiError,
  buildReviewPackage,
  fetchObjectUrl,
  loadArtifact,
  loadReviewPackage,
  type ArtifactSummary,
  type ReviewPackage,
} from '../api/client'

type Phase = 'loading' | 'building' | 'ready' | 'error'

export interface LearnPageProps {
  /** The deck being learnt (the `/learn/{artifactId}` route). */
  artifactId: string
  /** Injectable so page tests never need a server or a real blob URL. */
  loadRender?: (institutionId: string, path: string) => Promise<string>
}

function describe(cause: unknown): string {
  if (cause instanceof ApiError) {
    return cause.message ? `${cause.code}: ${cause.message}` : cause.code
  }
  return cause instanceof Error ? cause.message : String(cause)
}

/**
 * The learning page — `/learn/{artifactId}`.
 *
 * It is the slide, seen the way a learner sees it, plus the **teaching canvas**
 * the teacher draws on (`presentation/TeachingCanvas.tsx`). Navigation is
 * prev/next, a slide jump and the arrow keys, and the right-hand panel is the
 * teaching script that belongs to the slide (extracted text, speaker notes and
 * the section's lesson script from the pinned package).
 *
 * It reads the same built package as the Teacher Studio — it never re-renders a
 * stored one — so a deck is reviewed once and then taught from the same bytes
 * (`DEC-CONTENT-006`). Annotations are client-local; the event stream that would
 * carry them to students is `DEC-DATA-003` (OPEN) and V1-002's work.
 */
export default function LearnPage({ artifactId, loadRender = fetchObjectUrl }: LearnPageProps) {
  const [institution, setInstitution] = useInstitution()
  const [phase, setPhase] = useState<Phase>('loading')
  const [review, setReview] = useState<ReviewPackage | null>(null)
  const [artifact, setArtifact] = useState<ArtifactSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [index, setIndex] = useState(0)
  // Annotations are kept per scene, so walking back to a slide keeps its marks.
  const [annotations, setAnnotations] = useState<Record<string, AnnotationStroke[]>>({})

  const load = useCallback(async () => {
    setError(null)
    setPhase('loading')
    try {
      let loaded: ReviewPackage
      try {
        loaded = await loadReviewPackage(institution, artifactId)
      } catch (cause) {
        if (!(cause instanceof ApiError) || cause.code !== 'NOT_FOUND') throw cause
        // Nothing is built yet. Building renders every slide, so say so.
        setPhase('building')
        loaded = await buildReviewPackage(institution, artifactId)
      }
      setReview(loaded)
      setArtifact(await loadArtifact(institution, artifactId).catch(() => null))
      setPhase('ready')
    } catch (cause) {
      setError(describe(cause))
      setPhase('error')
    }
  }, [artifactId, institution])

  useEffect(() => {
    void load()
  }, [load])

  // The shared nav links back to this deck from the other pages.
  useEffect(() => {
    writeSelectedArtifact(artifactId)
  }, [artifactId])

  useEffect(() => {
    document.title = artifact ? `${artifact.filename} — Learning` : 'Learning — Mentora'
  }, [artifact])

  const scenes = useMemo(() => review?.scenes ?? [], [review])
  const count = scenes.length
  // A rebuilt package can be shorter than the slide the page was on, so the
  // position is clamped rather than trusted.
  const position = count > 0 ? Math.min(index, count - 1) : 0
  const current = scenes[position] ?? null

  useEffect(() => {
    setIndex((value) => Math.min(value, Math.max(0, count - 1)))
  }, [count])

  const go = useCallback(
    (next: number) => {
      setIndex(() => Math.min(Math.max(0, next), Math.max(0, count - 1)))
    },
    [count],
  )

  // Arrow keys move through the deck, unless the focus is in a control.
  useEffect(() => {
    if (phase !== 'ready' || count === 0) return
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null
      if (target && (target.closest('input, textarea, select') || target.isContentEditable)) return
      if (event.key === 'ArrowLeft') {
        event.preventDefault()
        setIndex((value) => Math.max(0, value - 1))
      } else if (event.key === 'ArrowRight') {
        event.preventDefault()
        setIndex((value) => Math.min(count - 1, value + 1))
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [count, phase])

  const sceneKey = current?.scene_id ?? ''
  const strokes = annotations[sceneKey] ?? []
  const setStrokes = useCallback(
    (next: AnnotationStroke[]) => {
      if (!sceneKey) return
      setAnnotations((previous) => ({ ...previous, [sceneKey]: next }))
    },
    [sceneKey],
  )

  const sectionScript = useMemo(() => {
    if (!current) return null
    const section = review?.lesson_order.find((entry) => entry.scene_id === current.scene_id)
    return section?.script ?? null
  }, [current, review])

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3">
          <SiteNav current="learn" artifactId={artifactId} />
          <h1 className="text-base font-semibold">Learning</h1>
          <span className="truncate text-sm text-slate-500">{artifact?.filename ?? 'loading…'}</span>

          <div className="ml-auto flex items-center gap-2">
            <label htmlFor="institution" className="text-[11px] font-medium text-slate-500">
              Institution
            </label>
            <input
              id="institution"
              value={institution}
              onChange={(event) => setInstitution(event.target.value)}
              className="w-40 rounded-md border border-slate-300 px-2 py-1 text-xs focus:border-indigo-500 focus:outline-none"
            />
          </div>
        </div>
      </header>

      <main className="px-4 py-4">
        {phase === 'loading' && (
          <p role="status" className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-500">
            Loading the deck…
          </p>
        )}

        {phase === 'building' && (
          <p role="status" className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-500">
            Rendering every slide and validating the package — this takes a few seconds for a real deck.
          </p>
        )}

        {phase === 'error' && (
          <div
            data-testid="learn-error"
            role="alert"
            className="rounded-xl border border-rose-200 bg-rose-50 p-5 text-rose-800"
          >
            <p className="text-sm font-semibold">The deck for this page could not be loaded.</p>
            <p className="mt-1 font-mono text-xs">{error}</p>
            <p className="mt-2 text-xs">
              Check the institution (the deck belongs to one tenant) and that the link names an uploaded
              artifact.
            </p>
          </div>
        )}

        {phase === 'ready' && current && (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => go(position - 1)}
                disabled={position <= 0}
                className="rounded-md border border-slate-300 px-2.5 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
              >
                ← Previous
              </button>
              <span data-testid="learn-slide-counter" className="text-xs font-medium text-slate-600">
                Slide {position + 1} / {count}
              </span>
              <button
                type="button"
                onClick={() => go(position + 1)}
                disabled={position >= count - 1}
                className="rounded-md border border-slate-300 px-2.5 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
              >
                Next →
              </button>
              <label className="ml-2 flex items-center gap-1 text-[11px] text-slate-500">
                Jump to
                <select
                  aria-label="Jump to slide"
                  value={position}
                  onChange={(event) => go(Number(event.target.value))}
                  className="rounded border border-slate-300 bg-white px-1 py-0.5 text-xs"
                >
                  {scenes.map((scene, position) => (
                    <option key={scene.scene_id} value={position}>
                      {position + 1}. {scene.scene_id.split('/').pop()}
                    </option>
                  ))}
                </select>
              </label>
              <span className="ml-auto text-[11px] text-slate-400">
                Use ← / → to move through the deck
              </span>
            </div>

            <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,1fr)]">
              <section aria-label="Learning surface">
                <SlideStage
                  institutionId={institution}
                  scene={current}
                  loadRender={loadRender}
                  strokes={strokes}
                  onStrokesChange={setStrokes}
                />
              </section>

              <aside className="space-y-3 self-start rounded-xl border border-slate-200 bg-white p-4">
                <h2 id="script-heading" className="text-sm font-semibold text-slate-700">
                  Teaching script
                </h2>
                <p className="text-[11px] text-slate-400">
                  From the pinned package&apos;s extracted content. Playback, captions and the timeline
                  arrive with V0-013.
                </p>

                <div>
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                    Speaker notes
                  </h3>
                  {current.notes ? (
                    <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{current.notes}</p>
                  ) : (
                    <p className="mt-1 text-sm text-slate-400">No speaker notes on this slide.</p>
                  )}
                </div>

                <div>
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                    On the slide
                  </h3>
                  {current.text.length > 0 ? (
                    <ul className="mt-1 space-y-1 text-sm text-slate-700">
                      {current.text.map((line, position) => (
                        <li key={`${position}-${line}`}>{line}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-1 text-sm text-slate-400">No text on this slide.</p>
                  )}
                </div>

                <div>
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                    Lesson script
                  </h3>
                  <p className="mt-1 text-sm text-slate-700">
                    {sectionScript ?? 'No script for this section — add a draft in the Teacher Studio.'}
                  </p>
                </div>

                <p className="border-t border-slate-100 pt-2 text-[11px] text-slate-400">
                  Annotations stay in this browser. Sharing them with students needs the ordered
                  per-class event stream (<span className="font-mono">DEC-DATA-003</span> is OPEN).
                </p>
              </aside>
            </div>
          </div>
        )}

        {phase === 'ready' && !current && (
          <p role="status" className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-500">
            This package has no scenes to learn from.
          </p>
        )}
      </main>
    </div>
  )
}
