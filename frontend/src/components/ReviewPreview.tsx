import { useEffect, useMemo, useState, type KeyboardEvent, type ReactNode } from 'react'
import { fetchObjectUrl, type ReviewPackage, type ReviewScene } from '../api/client'

const STATE_STYLE: Record<string, string> = {
  READY: 'bg-emerald-100 text-emerald-700',
  REVIEW_REQUIRED: 'bg-amber-100 text-amber-700',
  BLOCKED: 'bg-rose-100 text-rose-700',
}

const FIDELITY_STYLE: Record<string, string> = {
  NATIVE_RENDERED: 'bg-emerald-100 text-emerald-700',
  COMPATIBLE_RENDERED: 'bg-sky-100 text-sky-700',
  STRUCTURAL_RENDERED: 'bg-slate-100 text-slate-600',
  DEGRADED_RENDERED: 'bg-amber-100 text-amber-700',
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

/** The rendered slide, loaded through the tenant-scoped API and shown as a blob URL. */
function SlideFrame({
  institutionId,
  scene,
}: {
  institutionId: string
  scene: ReviewScene
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
    fetchObjectUrl(institutionId, scene.render_url)
      .then((objectUrl) => {
        if (cancelled) {
          URL.revokeObjectURL(objectUrl)
          return
        }
        created = objectUrl
        setUrl(objectUrl)
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : String(cause))
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
      if (created) URL.revokeObjectURL(created)
    }
  }, [institutionId, scene.render_url])

  return (
    <figure className="space-y-2">
      <div className="flex min-h-[300px] items-center justify-center overflow-hidden rounded-xl border border-slate-200 bg-white p-2">
        {loading && <p className="text-sm text-slate-400">Loading slide…</p>}
        {error && (
          <p className="max-w-md px-4 text-center text-sm text-rose-700">
            Could not load this slide's render. {error}
          </p>
        )}
        {url && !error && (
          <img
            src={url}
            alt={`Rendered fallback of slide ${scene.order + 1} (structural placeholder)`}
            className="max-h-[70vh] w-full object-contain"
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
 * Read-only teacher review preview (V0-007, preview slice).
 *
 * Shows the render, the extracted text, the speaker notes, the warnings/fidelity
 * and the lesson order for a built package. There is deliberately **no
 * approve/reject and no editing**: a review must never mutate an immutable
 * package, and the publication transition is V0-008. Because a package is only
 * built when the V0-005 fidelity gate passed, a blocking failure can never reach
 * this screen — it surfaces as an error when the package is built.
 */
export default function ReviewPreview({
  institutionId,
  review,
}: {
  institutionId: string
  review: ReviewPackage
}) {
  const [selectedSceneId, setSelectedSceneId] = useState<string | null>(
    () => review.scenes[0]?.scene_id ?? null,
  )

  // Keep the selection valid when the reviewed package changes.
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

  const index = scene ? review.scenes.findIndex((c) => c.scene_id === scene.scene_id) : -1
  const previous = index > 0 ? review.scenes[index - 1] : null
  const next = index >= 0 && index < review.scenes.length - 1 ? review.scenes[index + 1] : null

  function onKeyDown(event: KeyboardEvent) {
    if (event.key === 'ArrowLeft' && previous) {
      event.preventDefault()
      setSelectedSceneId(previous.scene_id)
    } else if (event.key === 'ArrowRight' && next) {
      event.preventDefault()
      setSelectedSceneId(next.scene_id)
    }
  }

  return (
    <div className="space-y-4" data-testid="review-preview">
      <div className="rounded-xl border border-slate-200 bg-white p-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Teacher review preview
          </span>
          <Badge value={review.state} style={STATE_STYLE[review.state]} />
          {review.requires_review && <Badge value="requires review" style="bg-amber-100 text-amber-700" />}
          {review.publishable && <Badge value="publishable" style="bg-emerald-100 text-emerald-700" />}
          <span className="ml-auto text-[11px] text-slate-400">
            {review.scene_count} slides · {review.file_count} package files
          </span>
        </div>

        {/* DEC-TECH-005 is OPEN: never present the placeholder as a native render. */}
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
          <KeyValue term="Lesson plan">
            {review.lesson_plan_version ?? '—'} (course v{review.course_version})
          </KeyValue>
          <KeyValue term="Knowledge index">{review.knowledge_index_version}</KeyValue>
          <KeyValue term="Teaching Graph">{review.teaching_graph_version ?? 'none (baseline, AI-free)'}</KeyValue>
        </dl>

        <p className="mt-2 text-[11px] text-slate-400">
          Read-only: approving/rejecting and editing a script are the publication task (V0-008), so this
          screen has no approve action.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
        <div className="space-y-2 self-start rounded-xl border border-slate-200 bg-white p-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Lesson order</h3>
          <ol className="space-y-1">
            {review.lesson_order.map((section) => {
              const active = section.scene_id === selectedSceneId
              return (
                <li key={section.section_id}>
                  <button
                    type="button"
                    onClick={() => section.scene_id && setSelectedSceneId(section.scene_id)}
                    aria-pressed={active}
                    className={`flex w-full flex-col gap-0.5 rounded-lg border px-2 py-1.5 text-left transition ${
                      active ? 'border-indigo-500 bg-indigo-50' : 'border-slate-200 hover:bg-slate-50'
                    }`}
                  >
                    <span className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-slate-700">
                        {section.order + 1}. {section.type.toLowerCase()}
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
                </li>
              )
            })}
          </ol>
        </div>

        <div className="space-y-3" onKeyDown={onKeyDown} tabIndex={-1}>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => previous && setSelectedSceneId(previous.scene_id)}
              disabled={!previous}
              className="rounded-md border border-slate-300 px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
            >
              ← Previous
            </button>
            <button
              type="button"
              onClick={() => next && setSelectedSceneId(next.scene_id)}
              disabled={!next}
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
          </div>

          {scene ? (
            <>
              <SlideFrame institutionId={institutionId} scene={scene} />

              <div className="grid gap-3 md:grid-cols-2">
                <div className="rounded-xl border border-slate-200 bg-white p-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Extracted text
                  </h3>
                  {scene.text.length === 0 ? (
                    <p className="mt-1 text-xs text-slate-400">No text on this slide.</p>
                  ) : (
                    <ul className="mt-1 space-y-0.5">
                      {scene.text.map((line, i) => (
                        <li key={i} className="whitespace-pre-wrap text-sm leading-snug text-slate-800">
                          {line}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div className="space-y-3">
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
                        {scene.warnings.map((warning, i) => (
                          <li key={i} className="font-mono text-[11px] text-slate-700">
                            {warning}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              </div>
            </>
          ) : (
            <p className="text-sm text-slate-400">This package contains no scenes.</p>
          )}
        </div>
      </div>
    </div>
  )
}
