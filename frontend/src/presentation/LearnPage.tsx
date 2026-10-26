import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import PageHeader from '../components/PageHeader'
import { BUTTON_SMALL, PAGE_PADDING } from '../components/ui'
import SlideStage from './SlideStage'
import type { AnnotationStroke } from './TeachingCanvas'
import { useInstitution, writeSelectedArtifact } from '../institution'
import { useSettings } from '../settings/store'
import { describeSchedule, fromDateTimeLocalValue, isDue, toDateTimeLocalValue, useNow } from '../time'
import { buildNarration, segmentForScene, type NarrationSegment } from './narration'
import { useNarrationTimer } from './useNarrationTimer'
import {
  ApiError,
  buildReviewPackage,
  fetchObjectUrl,
  loadArtifact,
  loadReviewPackage,
  loadReviewState,
  type ArtifactSummary,
  type ReviewDraft,
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
 * It also **teaches**. "Play" narrates the deck from its own authored script — the
 * teacher's newest draft revision, else the package's lesson script, else the
 * speaker notes, else the slide's own text — shows each passage as a caption and,
 * at the pace the teacher sets in Settings, moves to the next slide. A time can be
 * set and it will start narrating by itself when the clock reaches it, which is
 * client-local: the tab must stay open, because the authoritative timeline with
 * checkpoints and resume is V0-013/V1-002 and the server has no scheduler
 * (`DEC-TECH-003` is `OPEN`). It is text-only by construction: no model writes the teaching text
 * and no audio is produced (`DEC-TECH-007` is `OPEN`), so the deck teaches the
 * words its author wrote, at a fixed pace, reproducibly.
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
  const [draft, setDraft] = useState<ReviewDraft | null>(null)
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
      // The teacher's newest draft revision, if there is one: its scripts are
      // what is being written, so they are what gets narrated. A failure here is
      // not fatal — the package's own script is the fallback.
      setDraft(await loadReviewState(institution, artifactId).then(
        (state) => state.draft,
        () => null,
      ))
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

  const draftScript = useMemo(() => {
    if (!current) return null
    return (
      draft?.sections.find(
        (entry) => entry.scene_id === current.scene_id && entry.script?.trim(),
      )?.script ?? null
    )
  }, [current, draft])

  // -- automatic teaching (text only) -------------------------------------------
  const [settings] = useSettings()
  const [playing, setPlaying] = useState(false)
  const [finished, setFinished] = useState(false)
  const [transcript, setTranscript] = useState<NarrationSegment[]>([])
  const autoplayed = useRef(false)
  // Timed teaching: the instant the teacher asked for, and whether it has fired.
  const [teachAt, setTeachAt] = useState<string | null>(null)
  const [teachFired, setTeachFired] = useState(false)
  const teachTriggered = useRef(false)
  // The clock only runs while a time is set, so a page that schedules nothing
  // leaves no interval behind.
  const now = useNow(1000, teachAt !== null)

  const segments = useMemo(
    () => (review ? buildNarration(review, settings.teachingWpm, draft) : []),
    [draft, review, settings.teachingWpm],
  )
  const segment = sceneKey ? segmentForScene(segments, sceneKey) : null

  // A fresh deck (or a rebuilt one) starts from silence.
  useEffect(() => {
    setPlaying(false)
    setFinished(false)
    setTranscript([])
    autoplayed.current = false
    setTeachAt(null)
    setTeachFired(false)
    teachTriggered.current = false
  }, [artifactId])

  const remember = useCallback((next: NarrationSegment | null) => {
    if (!next) return
    setTranscript((previous) =>
      previous.some((entry) => entry.scene_id === next.scene_id) ? previous : [...previous, next],
    )
  }, [])

  useEffect(() => {
    if (playing) remember(segment)
  }, [playing, remember, segment])

  const play = useCallback(() => {
    // Replaying a finished deck starts over rather than resuming at the end.
    if (finished) {
      setTranscript([])
      setFinished(false)
      go(0)
    }
    setPlaying(true)
  }, [finished, go])

  const pause = useCallback(() => setPlaying(false), [])

  const stop = useCallback(() => {
    setPlaying(false)
    setFinished(false)
    setTranscript([])
    go(0)
  }, [go])

  const onElapsed = useCallback(() => {
    if (position >= count - 1) {
      setPlaying(false)
      setFinished(true)
      return
    }
    setIndex((value) => Math.min(value + 1, Math.max(0, count - 1)))
  }, [count, position])

  useNarrationTimer({
    playing: playing && phase === 'ready' && segment !== null,
    durationMs: segment?.durationMs ?? 0,
    segmentKey: segment?.scene_id ?? '',
    onElapsed,
  })

  useEffect(() => {
    if (autoplayed.current || phase !== 'ready' || count === 0) return
    if (!settings.teachingAutoplay) return
    autoplayed.current = true
    setPlaying(true)
  }, [count, phase, settings.teachingAutoplay])

  // Timed teaching: at the instant the teacher named, narration starts by itself.
  //
  // Like the scheduled start on the Classes page this is **client-local** — the
  // tab has to be open — because the authoritative timeline, with checkpoints and
  // resume, is V0-013/V1-002 rather than a browser timer. The teacher's own clock
  // is what waits, and the panel says so.
  useEffect(() => {
    if (!teachAt || phase !== 'ready' || count === 0) return
    if (teachTriggered.current || !isDue(teachAt, now)) return
    teachTriggered.current = true
    setTeachAt(null)
    setTeachFired(true)
    play()
  }, [count, now, phase, play, teachAt])

  return (
    <div className="min-h-screen bg-academic-canvas bg-academic-grid text-slate-900">
      <PageHeader
        nav="learn"
        title="Learning"
        subtitle={artifact?.filename ?? 'loading…'}
        meta={artifactId}
        artifactId={artifactId}
        institution={institution}
        onInstitutionChange={setInstitution}
      />

      <main className={PAGE_PADDING}>
        {phase === 'loading' && (
          <div role="status" className="flex items-center gap-3 rounded-xl border border-slate-200/80 bg-white/90 p-6 text-sm text-slate-600 shadow-sm backdrop-blur-sm">
            <svg className="animate-spin h-5 w-5 text-indigo-600 shrink-0" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <span>Loading the deck…</span>
          </div>
        )}

        {phase === 'building' && (
          <div role="status" className="flex items-center gap-3 rounded-xl border border-indigo-200/80 bg-indigo-50/70 p-6 text-sm text-indigo-900 shadow-sm backdrop-blur-sm">
            <svg className="animate-spin h-5 w-5 text-indigo-600 shrink-0" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <span>Rendering every slide and validating the package — this takes a few seconds for a real deck.</span>
          </div>
        )}

        {phase === 'error' && (
          <div
            data-testid="learn-error"
            role="alert"
            className="rounded-xl border border-rose-200 bg-rose-50/90 p-6 text-rose-900 shadow-sm"
          >
            <p className="text-sm font-semibold">The deck for this page could not be loaded.</p>
            <p className="mt-1 font-mono text-xs">{error}</p>
            <p className="mt-2 text-xs text-rose-700">
              Check the institution (the deck belongs to one tenant) and that the link names an uploaded
              artifact.
            </p>
          </div>
        )}

        {phase === 'ready' && current && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2.5 rounded-xl border border-slate-200/80 bg-white/95 p-3 shadow-sm">
              <button
                type="button"
                onClick={() => go(position - 1)}
                disabled={position <= 0}
                className={BUTTON_SMALL}
              >
                ← Previous
              </button>
              <span data-testid="learn-slide-counter" className="text-xs font-semibold text-slate-700">
                Slide {position + 1} / {count}
              </span>
              <button
                type="button"
                onClick={() => go(position + 1)}
                disabled={position >= count - 1}
                className={BUTTON_SMALL}
              >
                Next →
              </button>
              <label className="flex items-center gap-1.5 text-xs text-slate-600 sm:ml-2">
                Jump to
                <select
                  aria-label="Jump to slide"
                  value={position}
                  onChange={(event) => go(Number(event.target.value))}
                  className="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-800 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 lg:py-1"
                >
                  {scenes.map((scene, position) => (
                    <option key={scene.scene_id} value={position}>
                      {position + 1}. {scene.scene_id.split('/').pop()}
                    </option>
                  ))}
                </select>
              </label>
              {/* A keyboard hint is useless on a phone, where there is no keyboard. */}
              <span className="ml-auto hidden text-[11px] font-medium text-slate-400 sm:inline">
                Use ← / → to move through the deck
              </span>
            </div>

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,1fr)]">
              <section aria-label="Learning surface" className="space-y-3">
                <div className="overflow-hidden rounded-xl border border-slate-200/80 bg-white shadow-sm">
                  <SlideStage
                    institutionId={institution}
                    scene={current}
                    loadRender={loadRender}
                    strokes={strokes}
                    onStrokesChange={setStrokes}
                  />
                </div>
                {playing && settings.teachingCaptions && (
                  <p
                    data-testid="learn-caption"
                    role="status"
                    aria-live="polite"
                    className="rounded-xl border border-indigo-200/90 bg-gradient-to-r from-indigo-900 to-slate-900 px-4 py-3 text-sm text-indigo-50 shadow-md backdrop-blur-sm"
                  >
                    <span className="mr-2 inline-block h-2 w-2 rounded-full bg-emerald-400 animate-pulse-subtle" />
                    {segment?.text
                      ? segment.text
                      : 'This slide has no authored script, notes or text to narrate.'}
                  </p>
                )}
              </section>

              <aside className="space-y-3 self-start rounded-xl border border-slate-200 bg-white p-4">
                <div className="space-y-2 rounded-lg border border-indigo-200 bg-indigo-50/60 p-3">
                  <h2 className="text-sm font-semibold text-indigo-900">Automatic teaching</h2>
                  <p className="text-[11px] text-indigo-800">
                    Text only: this deck narrates its own authored script — your latest draft
                    revision, else the package&apos;s lesson script, else the speaker notes, else the
                    slide text. No model writes the words and no audio is produced (
                    <span className="font-mono">DEC-TECH-007</span> is OPEN).
                  </p>

                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={playing ? pause : play}
                      data-testid="learn-play"
                      className="inline-flex min-h-11 items-center justify-center rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white lg:min-h-0 lg:px-2.5 lg:py-1 lg:text-[11px]"
                    >
                      {playing ? 'Pause' : 'Play'}
                    </button>
                    <button
                      type="button"
                      onClick={stop}
                      data-testid="learn-stop"
                      disabled={!playing && transcript.length === 0}
                      className="inline-flex min-h-11 items-center justify-center rounded-md border border-indigo-300 px-3 py-2 text-sm font-medium text-indigo-800 hover:bg-indigo-100 disabled:opacity-40 lg:min-h-0 lg:px-2.5 lg:py-1 lg:text-[11px]"
                    >
                      Stop
                    </button>
                    {segment && (
                      <span className="text-[11px] text-indigo-800 sm:ml-auto">
                        {(segment.durationMs / 1000).toFixed(1)}s per slide at {settings.teachingWpm}{' '}
                        wpm
                      </span>
                    )}
                  </div>

                  <div className="space-y-1.5 border-t border-indigo-200 pt-2">
                    <label
                      htmlFor="learn-teach-at"
                      className="block text-[11px] font-medium text-indigo-800"
                    >
                      Teach at a time
                    </label>
                    <div className="flex flex-wrap items-center gap-2">
                      <input
                        id="learn-teach-at"
                        type="datetime-local"
                        value={toDateTimeLocalValue(teachAt)}
                        onChange={(event) => {
                          setTeachFired(false)
                          setTeachAt(fromDateTimeLocalValue(event.target.value))
                        }}
                        className="min-w-0 rounded-md border border-indigo-300 px-2 py-2 text-base lg:py-1 lg:text-[11px]"
                      />
                      {teachAt && (
                        <button
                          type="button"
                          data-testid="learn-teach-clear"
                          onClick={() => setTeachAt(null)}
                          className="inline-flex min-h-11 items-center justify-center rounded-md border border-indigo-300 px-3 py-2 text-sm font-medium text-indigo-800 hover:bg-indigo-100 lg:min-h-0 lg:px-2 lg:py-1 lg:text-[11px]"
                        >
                          Clear
                        </button>
                      )}
                    </div>

                    {teachAt && (
                      <p data-testid="learn-teach-when" className="text-[11px] text-indigo-800">
                        Starts teaching {describeSchedule(teachAt, now)}.
                      </p>
                    )}

                    {teachFired && !teachAt && (
                      <p
                        data-testid="learn-teach-fired"
                        role="status"
                        className="text-[11px] font-medium text-indigo-900"
                      >
                        The scheduled time arrived — teaching started.
                      </p>
                    )}

                    <p className="text-[10px] text-indigo-700">
                      This tab has to stay open: the server has no clock to wait on (
                      <span className="font-mono">DEC-TECH-003</span> is OPEN), and the durable
                      timeline with checkpoints and resume is V0-013.
                    </p>
                  </div>

                  {segment && (
                    <p className="text-[10px] uppercase tracking-wide text-indigo-700">
                      narration source: {segment.source}
                    </p>
                  )}

                  {finished && (
                    <p
                      data-testid="learn-finished"
                      role="status"
                      className="text-xs font-medium text-indigo-900"
                    >
                      The deck has been taught to the end.
                    </p>
                  )}

                  {transcript.length > 0 && (
                    <div>
                      <h3 className="text-[11px] font-semibold uppercase tracking-wide text-indigo-700">
                        Transcript
                      </h3>
                      <ol
                        data-testid="learn-transcript"
                        className="mt-1 max-h-56 space-y-1 overflow-y-auto text-xs text-indigo-900"
                      >
                        {transcript.map((entry) => (
                          <li key={entry.scene_id}>
                            <span className="font-mono text-[10px] text-indigo-600">
                              #{entry.order + 1}
                            </span>{' '}
                            {entry.text || <em>(no authored text)</em>}
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}
                </div>

                <h2 id="script-heading" className="text-sm font-semibold text-slate-700">
                  Teaching script
                </h2>
                <p className="text-[11px] text-slate-400">
                  From the pinned package&apos;s extracted content. The narration and captions above
                  run in this browser; the ordered per-class timeline, checkpoints and resume are
                  V0-013 and V1-002.
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
                  {draftScript ? (
                    <>
                      <p className="mt-1 text-sm text-slate-700">{draftScript}</p>
                      <p className="text-[10px] text-slate-400">
                        Your latest draft revision{draft ? ` (revision ${draft.revision})` : ''}; the
                        package itself holds {sectionScript ? 'a different script' : 'no script'} for
                        this section.
                      </p>
                    </>
                  ) : (
                    <p className="mt-1 text-sm text-slate-700">
                      {sectionScript ?? 'No script for this section — add a draft in the Teacher Studio.'}
                    </p>
                  )}
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
