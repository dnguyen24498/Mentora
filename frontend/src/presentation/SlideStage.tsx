import { useEffect, useState } from 'react'
import TeachingCanvas, { type AnnotationStroke } from './TeachingCanvas'
import type { ReviewScene } from '../api/client'

export interface SlideStageProps {
  institutionId: string
  scene: ReviewScene
  /** Injectable so the page tests never need a server or a real blob URL. */
  loadRender: (institutionId: string, path: string) => Promise<string>
  /** The annotations for this slide (kept by the page, one list per scene). */
  strokes: AnnotationStroke[]
  onStrokesChange: (strokes: AnnotationStroke[]) => void
}

/**
 * The learning surface: the rendered slide with the teaching canvas over it.
 *
 * The slide arrives as a tenant-scoped API response, so it is fetched by the
 * client and shown as an object URL — `<img src>` cannot send the
 * `X-Institution-Id` header (the same reason the Teacher Studio does it).
 */
export default function SlideStage({
  institutionId,
  scene,
  loadRender,
  strokes,
  onStrokesChange,
}: SlideStageProps) {
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

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
    <div className="space-y-2">
      <TeachingCanvas strokes={strokes} onStrokesChange={onStrokesChange}>
        <div className="aspect-video w-full bg-slate-50">
          {loading && (
            <div className="flex h-full items-center justify-center">
              <p className="text-sm text-slate-400">Loading slide…</p>
            </div>
          )}
          {error && (
            <div className="flex h-full items-center justify-center px-6">
              <p className="max-w-md text-center text-sm text-rose-700">
                Could not load this slide&apos;s render. {error}
              </p>
            </div>
          )}
          {url && !error && (
            <img
              src={url}
              alt={`Slide ${scene.order + 1}`}
              className="h-full w-full object-contain"
              draggable={false}
            />
          )}
        </div>
      </TeachingCanvas>
      <p className="text-[11px] text-slate-500">
        Slide {scene.order + 1} · <span className="font-mono">{scene.scene_id}</span> ·{' '}
        {scene.object_count} object(s) · {scene.step_count} reveal step(s)
      </p>
    </div>
  )
}
