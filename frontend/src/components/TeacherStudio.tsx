import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from 'react'
import {
  fetchObjectUrl,
  type ReviewDecisionInput,
  type ReviewDraft,
  type ReviewPackage,
  type ReviewScene,
  type ReviewState,
} from '../api/client'

const STATE_STYLE: Record<string, string> = {
  READY: 'bg-emerald-100 text-emerald-700',
  REVIEW_REQUIRED: 'bg-amber-100 text-amber-700',
  BLOCKED: 'bg-rose-100 text-rose-700',
}

const FIDELITY_STYLE: Record<string, string> = {
  NATIVE_RENDERED: 'bg-emerald-100 text-emerald-700',
  COMPATIBLE_RENDERED: 'bg-sky-100 text-sky-700',
  // V0-019 v5: the default mode keeps the deck's own layout, drawing anything it
  // cannot reproduce in the platform look in place.
  STRUCTURAL_RENDERED: 'bg-slate-100 text-slate-600',
  // The opt-in mode re-lays the content out entirely; it is not a rank on the
  // fidelity-to-source ladder, so it gets its own colour.
  THEMED_RENDERED: 'bg-indigo-100 text-indigo-700',
  DEGRADED_RENDERED: 'bg-amber-100 text-amber-700',
}

const VERSION_STATUS_STYLE: Record<string, string> = {
  DRAFT: 'bg-slate-100 text-slate-600',
  PROCESSING: 'bg-sky-100 text-sky-700',
  REVIEW_REQUIRED: 'bg-amber-100 text-amber-700',
  APPROVED: 'bg-emerald-100 text-emerald-700',
  PUBLISHED: 'bg-emerald-200 text-emerald-800',
  ARCHIVED: 'bg-slate-200 text-slate-600',
}

/** One lesson-order entry while it is being edited (order is the array position). */
interface EditableSection {
  section_id: string
  type: string
  scene_id: string | null
  scene_step_id: string | null
  safe_markers: string[]
  script: string
  requires_review: boolean
  scene_fidelity: string | null
}

export interface TeacherStudioProps {
  institutionId: string
  /** The package projection: what is under review. */
  review: ReviewPackage
  /** The mutable overlay: current decision, newest draft, blocking picture. */
  reviewState?: ReviewState | null
  /** A request is in flight. */
  busy?: boolean
  /** A success message from the last action. */
  notice?: string | null
  /** The last action failed. */
  error?: string | null
  onDecide: (input: ReviewDecisionInput) => void | Promise<void>
  onSaveDraft: (sections: { section_id: string; script: string }[]) => void | Promise<void>
  /** Injectable so component tests never need a server or a real blob URL. */
  loadRender?: (institutionId: string, path: string) => Promise<string>
}

function editableFromReview(review: ReviewPackage): EditableSection[] {
  return review.lesson_order.map((section) => ({
    section_id: section.section_id,
    type: section.type,
    scene_id: section.scene_id,
    scene_step_id: section.scene_step_id,
    safe_markers: section.safe_markers,
    script: section.script ?? '',
    requires_review: section.requires_review,
    scene_fidelity: section.scene_fidelity,
  }))
}

function editableFromDraft(draft: ReviewDraft, review: ReviewPackage): EditableSection[] {
  const scenes = new Map(review.scenes.map((scene) => [scene.scene_id, scene]))
  return draft.sections.map((section) => {
    const scene = section.scene_id ? scenes.get(section.scene_id) : undefined
    return {
      section_id: section.section_id,
      type: section.type,
      scene_id: section.scene_id,
      scene_step_id: section.scene_step_id,
      safe_markers: section.safe_markers,
      script: section.script ?? '',
      requires_review: scene?.requires_review ?? false,
      scene_fidelity: scene?.fidelity ?? null,
    }
  })
}

function isSameOrder(left: EditableSection[], right: EditableSection[]): boolean {
  return (
    left.length === right.length &&
    left.every(
      (section, index) =>
        section.section_id === right[index].section_id &&
        section.script.trim() === right[index].script.trim(),
    )
  )
}

function isTextEntry(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null
  if (!element) return false
  const tag = element.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || element.isContentEditable
}

function Badge({ label, value, style }: { label?: string; value: string; style?: string }) {
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
        style ?? 'bg-slate-100 text-slate-600'
      }`}
    >
      {label ? `${label} ` : ''}
      {value}
    </span>
  )
}

function KeyValue({ term, children }: { term: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-slate-500">{term}</dt>
      <dd className="truncate text-xs">{children}</dd>
    </>
  )
}

/**
 * Fullscreen for the slide region, where the browser implements it.
 *
 * jsdom (component tests) has no Fullscreen API, so `supported` stays false and
 * the control is simply not offered rather than being a button that does
 * nothing.
 */
function useSlideFullscreen() {
  const ref = useRef<HTMLElement>(null)
  const [active, setActive] = useState(false)
  const [supported, setSupported] = useState(false)

  useEffect(() => {
    setSupported(typeof document !== 'undefined' && document.fullscreenEnabled === true)
    function onChange() {
      setActive(document.fullscreenElement === ref.current)
    }
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [])

  const toggle = useCallback(() => {
    const element = ref.current
    if (!element) return
    // A rejected request (e.g. denied by the browser) is not an app error: the
    // page is exactly as it was before the click.
    const request =
      document.fullscreenElement === element
        ? document.exitFullscreen()
        : element.requestFullscreen()
    request.catch(() => {})
  }, [])

  return { ref, active, supported, toggle }
}

/** The rendered slide, loaded through the tenant-scoped API and shown as a blob URL. */
function SlideFrame({
  institutionId,
  scene,
  loadRender,
  large = false,
}: {
  institutionId: string
  scene: ReviewScene
  loadRender: (institutionId: string, path: string) => Promise<string>
  /** Give the slide the viewport (the standalone Teacher Studio page). */
  large?: boolean
}) {
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  // `<img src>` cannot send the X-Institution-Id header, so the SVG is fetched
  // by the client and handed to the browser as an object URL.
  useEffect(() => {
    setUrl(null)
    setError(null)
    if (!scene.render_url) {
      setError('This scene has no render: the render stage reported a failure.')
      return
    }
    let cancelled = false
    let created: string | null = null
    setLoading(true)
    loadRender(institutionId, scene.render_url)
      .then((objectUrl) => {
        if (cancelled) {
          URL.revokeObjectURL(objectUrl)
          return
        }
        created = objectUrl
        setUrl(objectUrl)
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : String(cause))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
      if (created) URL.revokeObjectURL(created)
    }
  }, [institutionId, scene.render_url, loadRender])

  return (
    <figure className="space-y-2">
      <div className="flex min-h-[280px] items-center justify-center overflow-hidden rounded-xl border border-slate-200 bg-white p-2">
        {loading && <p className="text-sm text-slate-400">Loading slide…</p>}
        {error && (
          <p className="max-w-md px-4 text-center text-sm text-rose-700">
            Could not load this slide's render. {error}
          </p>
        )}
        {url && !error && (
          <img
            src={url}
            alt={`Fallback render of slide ${scene.order + 1} (structural placeholder)`}
            className={`w-full object-contain ${large ? 'max-h-[85vh]' : 'max-h-[60vh]'}`}
          />
        )}
      </div>
      <figcaption className="text-[11px] text-slate-500">
        Slide {scene.order + 1} · {scene.scene_id} · {scene.object_count} object(s) ·{' '}
        {scene.step_count} reveal step(s)
      </figcaption>
    </figure>
  )
}

/**
 * Teacher Studio course-version review page (V0-007).
 *
 * Two halves, deliberately kept apart:
 *
 * * the **package projection** (`review`) — render, extracted text, notes,
 *   warnings/fidelity and the lesson order. Read-only: it is a pure function of
 *   the stored bytes;
 * * the **review overlay** (`reviewState`) — approve/reject and draft revisions.
 *   Everything the teacher changes here is *data about* the package; the package
 *   itself is never rewritten, so an edit can be discarded without undoing
 *   anything (acceptance criterion: edits create draft data).
 *
 * Approving a document with a blocking failure is impossible twice over: a
 * blocked document is never built into a package, and the Approve button is
 * disabled with a described reason when the projection is not publishable.
 */
export default function TeacherStudio({
  institutionId,
  review,
  reviewState = null,
  busy = false,
  notice = null,
  error = null,
  onDecide,
  onSaveDraft,
  loadRender = fetchObjectUrl,
}: TeacherStudioProps) {
  const renderLoader = useCallback(
    (id: string, path: string) => loadRender(id, path),
    [loadRender],
  )

  // The lesson order the editor starts from: the newest draft if one exists,
  // otherwise the package's own fallback lesson order.
  const savedSections = useMemo(
    () => (reviewState?.draft ? editableFromDraft(reviewState.draft, review) : editableFromReview(review)),
    [review, reviewState],
  )
  const sourceKey = reviewState?.draft
    ? `draft:${reviewState.draft.draft_id}`
    : `package:${review.package_id}`

  const [order, setOrder] = useState<EditableSection[]>(savedSections)
  const [selectedSceneId, setSelectedSceneId] = useState<string | null>(
    () => review.scenes[0]?.scene_id ?? null,
  )
  const [rejectReason, setRejectReason] = useState('')
  const [reviewer, setReviewer] = useState('')
  const [actionError, setActionError] = useState<string | null>(null)
  const [announcement, setAnnouncement] = useState<string | null>(null)
  // Presentation comfort: this page can be opened on its own, large, so the
  // slide can be given the full width and the whole monitor.
  const [focus, setFocus] = useState(false)
  const fullscreen = useSlideFullscreen()
  const appliedSource = useRef(sourceKey)

  // Reload the editor only when the *saved* source changes (a new revision, a new
  // package); unsaved local edits survive an unrelated re-render.
  useEffect(() => {
    if (appliedSource.current === sourceKey) return
    appliedSource.current = sourceKey
    setOrder(savedSections)
    setAnnouncement(null)
  }, [savedSections, sourceKey])

  // Keep the slide selection valid when the reviewed package changes.
  useEffect(() => {
    setSelectedSceneId((previous) =>
      previous && review.scenes.some((scene) => scene.scene_id === previous)
        ? previous
        : (review.scenes[0]?.scene_id ?? null),
    )
  }, [review])

  const scene = useMemo(
    () => review.scenes.find((candidate) => candidate.scene_id === selectedSceneId) ?? null,
    [review.scenes, selectedSceneId],
  )
  const sceneIndex = scene ? review.scenes.findIndex((c) => c.scene_id === scene.scene_id) : -1
  const previousScene = sceneIndex > 0 ? review.scenes[sceneIndex - 1] : null
  const nextScene =
    sceneIndex >= 0 && sceneIndex < review.scenes.length - 1 ? review.scenes[sceneIndex + 1] : null

  const dirty = useMemo(() => !isSameOrder(order, savedSections), [order, savedSections])
  const blockedScenes = useMemo(
    () => review.scenes.filter((candidate) => candidate.render_status !== 'RENDERED'),
    [review.scenes],
  )
  const blocked = !review.publishable
  const reviewNotices = review.scenes.filter((candidate) => candidate.requires_review)
  const approved = reviewState?.decision?.decision === 'APPROVE'
  const rejected = reviewState?.decision?.decision === 'REJECT'

  function move(index: number, delta: number) {
    const target = index + delta
    if (target < 0 || target >= order.length) return
    const next = [...order]
    const [moved] = next.splice(index, 1)
    next.splice(target, 0, moved)
    setOrder(next)
    setAnnouncement(
      `Moved section ${index + 1} (${moved.type.toLowerCase()}) to position ${target + 1} of ${order.length}.`,
    )
  }

  function editScript(index: number, value: string) {
    setOrder((previous) =>
      previous.map((section, position) =>
        position === index ? { ...section, script: value } : section,
      ),
    )
  }

  function discard() {
    setOrder(savedSections)
    setActionError(null)
    setAnnouncement('Discarded local changes; the editor shows the saved revision.')
  }

  function save() {
    setActionError(null)
    setAnnouncement(null)
    void onSaveDraft(order.map((section) => ({ section_id: section.section_id, script: section.script })))
  }

  function approve() {
    setActionError(null)
    void onDecide({ decision: 'APPROVE', reviewer: reviewer.trim() || undefined })
  }

  function reject() {
    const reason = rejectReason.trim()
    if (!reason) {
      setActionError('A rejection must record a reason, so the decision is auditable.')
      return
    }
    setActionError(null)
    void onDecide({
      decision: 'REJECT',
      reason,
      reviewer: reviewer.trim() || undefined,
    })
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (isTextEntry(event.target)) return
    if (event.key === 'ArrowLeft' && previousScene) {
      event.preventDefault()
      setSelectedSceneId(previousScene.scene_id)
    } else if (event.key === 'ArrowRight' && nextScene) {
      event.preventDefault()
      setSelectedSceneId(nextScene.scene_id)
    }
  }

  return (
    <div className="space-y-4" data-testid="teacher-studio">
      <section
        className="rounded-xl border border-slate-200 bg-white p-3"
        aria-labelledby="studio-heading"
      >
        <div className="flex flex-wrap items-center gap-2">
          <h2 id="studio-heading" className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            Teacher Studio — course version {review.course_version}
          </h2>
          <Badge value={review.state} style={STATE_STYLE[review.state]} />
          {reviewState && (
            <Badge
              label="version"
              value={reviewState.version_status}
              style={VERSION_STATUS_STYLE[reviewState.version_status]}
            />
          )}
          {review.requires_review && <Badge value="requires review" style="bg-amber-100 text-amber-700" />}
          {review.publishable && <Badge value="publishable" style="bg-emerald-100 text-emerald-700" />}
          <span className="ml-auto text-[11px] text-slate-400">
            {review.scene_count} slides · {review.file_count} package files
          </span>
        </div>

        {/* DEC-TECH-005 is OPEN: the notice (from the server) says exactly how the
            slides were produced — the deck's own layout with the platform's look
            where a component cannot be reproduced, or a full platform re-layout —
            and never implies a native render. */}
        <p className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-2 py-1.5 text-[11px] text-amber-800">
          {review.placeholder_notice}
          {review.renderer && (
            <>
              {' '}
              Renderer: <span className="font-mono">{review.renderer.name}</span>@
              {review.renderer.version} (engine <span className="font-mono">{review.renderer.engine}</span>)
            </>
          )}
        </p>

        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
          <KeyValue term="Package">{review.package_id}</KeyValue>
          <KeyValue term="Content version">{review.content_package_version}</KeyValue>
          <KeyValue term="Lesson plan">{review.lesson_plan_version ?? '—'}</KeyValue>
          <KeyValue term="Knowledge index">{review.knowledge_index_version}</KeyValue>
          <KeyValue term="Teaching Graph">{review.teaching_graph_version ?? 'none (baseline, AI-free)'}</KeyValue>
        </dl>
      </section>

      {/* Blocking status: the first thing a teacher must know. */}
      <section aria-labelledby="status-heading" className="rounded-xl border border-slate-200 bg-white p-3">
        <h2 id="status-heading" className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Warnings &amp; blocking status
        </h2>
        {blocked ? (
          <div
            id="approve-blocked-reason"
            role="alert"
            className="mt-2 rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-800"
          >
            <p className="font-semibold">Publication is blocked — this document cannot be approved.</p>
            <p className="mt-1 text-xs">
              {blockedScenes.length > 0
                ? `${blockedScenes.length} slide(s) failed to render (slide ${blockedScenes
                    .map((item) => item.order + 1)
                    .join(', ')}).`
                : 'The render stage reported a blocking fidelity failure.'}{' '}
              Fix the source and re-render before reviewing: approving it is refused by the server with
              <span className="font-mono"> PUBLICATION_BLOCKED</span>.
            </p>
          </div>
        ) : (
          <p className="mt-2 text-sm text-slate-700" role="status">
            No blocking failure. {reviewNotices.length === 0
              ? 'Every slide rendered within the renderer’s capabilities.'
              : `${reviewNotices.length} of ${review.scene_count} slide(s) need a human look before this lesson is delivered.`}
          </p>
        )}
        {reviewNotices.length > 0 && (
          <ul className="mt-2 space-y-0.5">
            {reviewNotices.map((candidate) => (
              <li key={candidate.scene_id} className="text-[11px] text-amber-800">
                Slide {candidate.order + 1}: {candidate.fidelity ?? 'unknown fidelity'}
                {candidate.missing_fonts.length > 0
                  ? ` — missing font(s) ${candidate.missing_fonts.join(', ')}`
                  : ''}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Reviewer actions. */}
      <section aria-labelledby="decision-heading" className="rounded-xl border border-slate-200 bg-white p-3">
        <h2 id="decision-heading" className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Review decision
        </h2>

        {reviewState?.decision ? (
          <p className="mt-2 text-sm text-slate-700">
            <span className="font-semibold" data-testid="current-decision">
              {reviewState.decision.decision === 'APPROVE' ? 'Approved' : 'Rejected'}
            </span>{' '}
            by <span className="font-mono text-xs">{reviewState.decision.reviewer}</span> for content{' '}
            <span className="font-mono text-xs">{reviewState.decision.content_package_version}</span>
            {reviewState.stale && (
              <span className="ml-1 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800">
                stale — the stored content changed
              </span>
            )}
            {reviewState.decision.reason && (
              <span className="mt-1 block text-xs text-slate-500">Reason: {reviewState.decision.reason}</span>
            )}
          </p>
        ) : (
          <p className="mt-2 text-sm text-slate-500">Not reviewed yet.</p>
        )}

        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <div>
            <label htmlFor="reviewer" className="block text-xs font-medium text-slate-700">
              Reviewer (optional)
            </label>
            <input
              id="reviewer"
              value={reviewer}
              onChange={(event) => setReviewer(event.target.value)}
              placeholder="Your name"
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            />
            <p className="mt-1 text-[11px] text-slate-400">
              Attribution only — identity and roles are not implemented yet, so it defaults to the tenant id.
            </p>
          </div>
          <div>
            <label htmlFor="reject-reason" className="block text-xs font-medium text-slate-700">
              Rejection reason (required to reject)
            </label>
            <textarea
              id="reject-reason"
              value={rejectReason}
              onChange={(event) => setRejectReason(event.target.value)}
              rows={3}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            />
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={approve}
            disabled={busy || blocked}
            aria-describedby={blocked ? 'approve-blocked-reason' : undefined}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            {approved ? 'Approve again' : 'Approve'}
          </button>
          <button
            type="button"
            onClick={reject}
            disabled={busy}
            className="rounded-lg border border-rose-300 bg-white px-4 py-2 text-sm font-semibold text-rose-700 disabled:opacity-40"
          >
            {rejected ? 'Reject again' : 'Reject'}
          </button>
          {blocked && (
            <span className="text-[11px] text-rose-700">
              Approve is unavailable: see the blocking status above.
            </span>
          )}
        </div>

        {actionError && (
          <p role="alert" className="mt-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
            {actionError}
          </p>
        )}
        {error && (
          <p role="alert" className="mt-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
            {error}
          </p>
        )}
        {notice && (
          <p role="status" className="mt-2 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-xs text-indigo-800">
            {notice}
          </p>
        )}
      </section>

      <div className={`grid gap-4 ${focus ? '' : 'lg:grid-cols-[320px_minmax(0,1fr)]'}`}>
        {/* Lesson-order editor. Hidden in focus mode, where the slide comes first;
            kept mounted so unsaved edits survive toggling. */}
        <section
          aria-labelledby="lesson-order-heading"
          hidden={focus}
          className="space-y-2 self-start rounded-xl border border-slate-200 bg-white p-3"
        >
          <div className="flex flex-wrap items-baseline gap-2">
            <h2 id="lesson-order-heading" className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Lesson order
            </h2>
            {reviewState?.draft && (
              <Badge
                value={`draft rev ${reviewState.draft.revision}`}
                style="bg-indigo-100 text-indigo-700"
              />
            )}
            {dirty && <Badge value="unsaved changes" style="bg-amber-100 text-amber-700" />}
          </div>
          <p className="text-[11px] text-slate-400">
            Reorder with the buttons, edit a script below. Saving records a <em>draft</em> — the built
            package is never modified.
          </p>

          <ol className="space-y-1.5" data-testid="lesson-order">
            {order.map((section, index) => {
              const active = section.scene_id === selectedSceneId
              const scriptId = `script-${section.section_id}`
              return (
                <li
                  key={section.section_id}
                  className={`rounded-lg border px-2 py-1.5 ${
                    active ? 'border-indigo-400 bg-indigo-50' : 'border-slate-200'
                  }`}
                >
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => section.scene_id && setSelectedSceneId(section.scene_id)}
                      aria-pressed={active}
                      className="flex min-w-0 flex-1 flex-col gap-0.5 rounded text-left focus:outline focus:outline-2 focus:outline-indigo-500"
                    >
                      <span className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-slate-700">
                          {index + 1}. {section.type.toLowerCase()}
                        </span>
                        {section.requires_review && (
                          <span className="ml-auto rounded bg-amber-100 px-1 py-0.5 text-[9px] font-semibold text-amber-700">
                            review
                          </span>
                        )}
                      </span>
                      <span className="truncate font-mono text-[10px] text-slate-400" title={section.scene_id ?? ''}>
                        {section.scene_id}
                      </span>
                      {section.safe_markers.length > 0 && (
                        <span className="truncate font-mono text-[10px] text-slate-400">
                          safe: {section.safe_markers.join(', ')}
                        </span>
                      )}
                    </button>
                    <div className="flex shrink-0 flex-col">
                      <button
                        type="button"
                        onClick={() => move(index, -1)}
                        disabled={index === 0 || busy}
                        aria-label={`Move section ${index + 1} (${section.type.toLowerCase()}) up`}
                        className="rounded border border-slate-300 px-1 text-[10px] leading-4 text-slate-700 disabled:opacity-30"
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        onClick={() => move(index, 1)}
                        disabled={index === order.length - 1 || busy}
                        aria-label={`Move section ${index + 1} (${section.type.toLowerCase()}) down`}
                        className="rounded border border-slate-300 px-1 text-[10px] leading-4 text-slate-700 disabled:opacity-30"
                      >
                        ↓
                      </button>
                    </div>
                  </div>
                  <label htmlFor={scriptId} className="mt-1 block text-[10px] font-medium text-slate-500">
                    Script for section {index + 1}
                  </label>
                  <textarea
                    id={scriptId}
                    value={section.script}
                    onChange={(event) => editScript(index, event.target.value)}
                    rows={2}
                    placeholder="No script"
                    className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1 text-xs focus:border-indigo-500 focus:outline-none"
                  />
                </li>
              )
            })}
          </ol>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={save}
              disabled={busy || !dirty}
              className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
            >
              Save draft
            </button>
            <button
              type="button"
              onClick={discard}
              disabled={busy || !dirty}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 disabled:opacity-40"
            >
              Discard local changes
            </button>
          </div>

          <p className="text-[11px] text-slate-400">
            {reviewState?.draft
              ? `Revision ${reviewState.draft.revision} of ${reviewState.draft_count} saved · base lesson plan ${reviewState.draft.lesson_plan_version ?? '—'}. The built package is unchanged; the draft is data for a future version.`
              : 'No draft yet. The lesson order shown is the package’s own fallback order.'}
          </p>
          <p role="status" aria-live="polite" className="text-[11px] font-medium text-slate-600">
            {announcement}
          </p>
        </section>

        {/* Side-by-side: rendered scene and the extracted information. */}
        <section
          ref={fullscreen.ref}
          className={`space-y-3 ${fullscreen.active ? 'overflow-auto bg-slate-100 p-4' : ''}`}
          onKeyDown={onKeyDown}
          tabIndex={-1}
          aria-label="Slide review"
        >
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => previousScene && setSelectedSceneId(previousScene.scene_id)}
              disabled={!previousScene}
              className="rounded-md border border-slate-300 px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
            >
              ← Previous
            </button>
            <button
              type="button"
              onClick={() => nextScene && setSelectedSceneId(nextScene.scene_id)}
              disabled={!nextScene}
              className="rounded-md border border-slate-300 px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
            >
              Next →
            </button>
            {scene && (
              <>
                <Badge
                  label="fidelity"
                  value={scene.fidelity ?? 'unknown'}
                  style={FIDELITY_STYLE[scene.fidelity ?? ''] ?? 'bg-rose-100 text-rose-700'}
                />
                <Badge value={scene.render_status} />
                {scene.requires_review && <Badge value="requires review" style="bg-amber-100 text-amber-700" />}
              </>
            )}
            <span className="ml-auto text-[11px] text-slate-400">Use ← / → to move between slides</span>
            <button
              type="button"
              onClick={() => setFocus((previous) => !previous)}
              aria-pressed={focus}
              className="rounded-md border border-slate-300 px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
            >
              {focus ? 'Show lesson order' : 'Focus slide'}
            </button>
            {fullscreen.supported && (
              <button
                type="button"
                onClick={fullscreen.toggle}
                className="rounded-md border border-slate-300 px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
              >
                {fullscreen.active ? 'Exit full screen' : 'Full screen'}
              </button>
            )}
          </div>

          {scene ? (
            <div
              className={`grid gap-3 ${
                focus ? 'md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]' : 'md:grid-cols-2'
              }`}
              data-testid="scene-side-by-side"
            >
              <SlideFrame
                institutionId={institutionId}
                scene={scene}
                loadRender={renderLoader}
                large={focus || fullscreen.active}
              />

              <div className="space-y-3">
                <div className="rounded-xl border border-slate-200 bg-white p-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Extracted text
                  </h3>
                  {scene.text.length === 0 ? (
                    <p className="mt-1 text-xs text-slate-400">No text on this slide.</p>
                  ) : (
                    <ul className="mt-1 space-y-0.5">
                      {scene.text.map((line, index) => (
                        <li key={index} className="whitespace-pre-wrap text-sm leading-snug text-slate-800">
                          {line}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div className="rounded-xl border border-slate-200 bg-white p-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Speaker notes
                  </h3>
                  {scene.notes ? (
                    <p className="mt-1 text-sm whitespace-pre-line text-indigo-900">{scene.notes}</p>
                  ) : (
                    <p className="mt-1 text-xs text-slate-400">No speaker notes on this slide.</p>
                  )}
                </div>

                <div className="rounded-xl border border-slate-200 bg-white p-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Warnings &amp; fidelity
                  </h3>
                  {scene.missing_fonts.length > 0 && (
                    <p className="mt-1 rounded-lg bg-amber-50 px-2 py-1 text-xs text-amber-800">
                      Missing font(s): {scene.missing_fonts.join(', ')} — lines using them are
                      approximate.
                    </p>
                  )}
                  {scene.warnings.length === 0 && scene.missing_fonts.length === 0 ? (
                    <p className="mt-1 text-xs text-slate-400">No warnings for this slide.</p>
                  ) : (
                    <ul className="mt-1 space-y-0.5">
                      {scene.warnings.map((warning, index) => (
                        <li key={index} className="font-mono text-[11px] text-slate-700">
                          {warning}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-400">This package contains no scenes.</p>
          )}
        </section>
      </div>
    </div>
  )
}
