import { useCallback, useEffect, useState } from 'react'
import {
  describeApiError,
  fetchObjectUrl,
  loadRendererStatus,
  type RendererStatus,
} from '../api/client'
import { readSelectedArtifact } from '../institution'
import { useSettings, type RenderMode } from './store'
import { Badge, Banner, EmptyState, Panel, Row, type Tone } from '../components/ui'

const MODES: { mode: RenderMode; title: string; description: string }[] = [
  {
    mode: 'faithful',
    title: 'Faithful (default)',
    description:
      "Reproduces the source deck's own layout and styling. Anything the renderer cannot reproduce — a chart, an unavailable font, a picture it cannot inline — is drawn in the platform's look, in place.",
  },
  {
    mode: 'themed',
    title: 'Themed',
    description:
      "Recovers the author's grouping, then re-lays the content out in the platform theme: the grouping and content are the author's, the look is the platform's.",
  },
]

function show(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

/**
 * Rendering settings: which mode slide renders are produced in.
 *
 * The preference is used by the compile action in Admin, and previewed live here
 * through `GET /artifacts/{id}/renders/{order}?mode=`. It cannot change a **packaged**
 * render: a package's renders are pinned at build time, and that is the point —
 * what a teacher reviewed is what a class is taught from.
 */
export default function RenderingSettings({ institutionId }: { institutionId: string }) {
  const [settings, updateSettings] = useSettings()
  const [status, setStatus] = useState<RendererStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [artifactId] = useState(readSelectedArtifact)
  const [order, setOrder] = useState(0)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    void loadRendererStatus(institutionId, settings.renderMode).then(
      (loaded) => {
        if (!cancelled) setStatus(loaded)
      },
      (cause: unknown) => {
        if (!cancelled) setError(describeApiError(cause))
      },
    )
    return () => {
      cancelled = true
    }
  }, [institutionId, settings.renderMode])

  const loadPreview = useCallback(async () => {
    setPreviewError(null)
    setPreviewUrl((previous) => {
      if (previous) URL.revokeObjectURL(previous)
      return null
    })
    if (!artifactId) return
    try {
      const url = await fetchObjectUrl(
        institutionId,
        `/artifacts/${artifactId}/renders/${order}?mode=${settings.renderMode}`,
      )
      setPreviewUrl(url)
    } catch (cause) {
      setPreviewError(describeApiError(cause))
    }
  }, [artifactId, institutionId, order, settings.renderMode])

  useEffect(() => {
    void loadPreview()
    return () => {
      setPreviewUrl((previous) => {
        if (previous) URL.revokeObjectURL(previous)
        return null
      })
    }
  }, [loadPreview])

  const health = status?.health ?? {}
  const healthTone: Tone =
    health.state === 'open' ? 'bad' : health.state === 'half_open' ? 'warn' : 'good'

  return (
    <div className="mx-auto grid grid-cols-1 max-w-6xl gap-6 lg:grid-cols-2">
      <Panel title="Render mode">
        <fieldset className="space-y-2">
          <legend className="sr-only">Render mode</legend>
          {MODES.map((option) => (
            <label
              key={option.mode}
              className={`flex cursor-pointer gap-3 rounded-lg border p-3 ${
                settings.renderMode === option.mode
                  ? 'border-indigo-500 bg-indigo-50'
                  : 'border-slate-200 hover:bg-slate-50'
              }`}
            >
              <input
                type="radio"
                name="render-mode"
                value={option.mode}
                checked={settings.renderMode === option.mode}
                onChange={() => updateSettings({ renderMode: option.mode })}
                className="mt-1"
              />
              <span>
                <span className="block text-sm font-medium text-slate-800">{option.title}</span>
                <span className="block text-xs text-slate-500">{option.description}</span>
              </span>
            </label>
          ))}
        </fieldset>
        <p className="text-[11px] text-slate-400">
          This selects the mode for new renders — a compile, and the preview below. It cannot
          change a packaged render: a package&apos;s renders are pinned at build time, so what a
          teacher reviewed is what a class is taught from.
        </p>
        <p className="text-[11px] text-slate-400">
          No renderer technology is accepted yet (
          <span className="font-mono">DEC-TECH-005</span> is
          <span className="font-mono"> OPEN</span>): this selects between the two prototype renderers
          and nothing more.
        </p>
      </Panel>

      <Panel title={`Renderer (${settings.renderMode})`}>
        {error && <Banner tone="bad">{error}</Banner>}
        {!status && !error && <EmptyState>Reading renderer capability…</EmptyState>}
        {status && (
          <>
            <dl className="space-y-1 text-sm">
              <Row label="Identity">
                {status.identity.name}@{status.identity.version}
              </Row>
              <Row label="Engine">{status.identity.engine}</Row>
              <Row label="Config hash">{status.identity.config_hash}</Row>
              <Row label="Data region">{status.identity.data_region}</Row>
              <Row label="Default mode">{status.default_mode}</Row>
            </dl>

            <div className="flex items-center gap-2 border-t border-slate-100 pt-3">
              <span className="text-sm text-slate-500">Circuit breaker</span>
              <Badge tone={healthTone}>{String(health.state ?? 'unknown')}</Badge>
            </div>
            <dl className="space-y-1 text-sm">
              {Object.entries(health)
                .filter(([key]) => key !== 'state')
                .map(([key, value]) => (
                  <Row key={key} label={key}>
                    {show(value)}
                  </Row>
                ))}
            </dl>

            {status.support && Object.keys(status.support).length > 0 && (
              <>
                <p className="border-t border-slate-100 pt-3 text-[11px] uppercase tracking-wide text-slate-400">
                  Declared support
                </p>
                <dl className="space-y-1 text-sm">
                  {Object.entries(status.support).map(([key, value]) => (
                    <Row key={key} label={key}>
                      {show(value)}
                    </Row>
                  ))}
                </dl>
              </>
            )}
          </>
        )}
      </Panel>

      <Panel
        title={`Preview (${settings.renderMode})`}
        className="lg:col-span-2"
        actions={
          <div className="flex items-center gap-2">
            <label htmlFor="preview-order" className="text-[11px] font-medium text-slate-500">
              Slide
            </label>
            <input
              id="preview-order"
              type="number"
              min={0}
              value={order}
              onChange={(event) => setOrder(Math.max(0, Number(event.target.value) || 0))}
              className="w-16 rounded-md border border-slate-300 px-2 py-2 text-base focus:border-indigo-500 focus:outline-none lg:py-1 lg:text-xs"
            />
          </div>
        }
      >
        {!artifactId && (
          <EmptyState>
            No deck opened yet. Open one in the library and its first slide will preview here.
          </EmptyState>
        )}
        {artifactId && previewError && <Banner tone="bad">{previewError}</Banner>}
        {artifactId && !previewError && (
          <div className="space-y-2">
            <div className="aspect-video w-full overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
              {previewUrl ? (
                <img
                  src={previewUrl}
                  alt={`Slide ${order + 1} rendered in ${settings.renderMode} mode`}
                  className="h-full w-full object-contain"
                />
              ) : (
                <div className="flex h-full items-center justify-center">
                  <p className="text-sm text-slate-400">Loading preview…</p>
                </div>
              )}
            </div>
            <p className="truncate font-mono text-[10px] text-slate-400">artifact {artifactId}</p>
          </div>
        )}
      </Panel>
    </div>
  )
}
