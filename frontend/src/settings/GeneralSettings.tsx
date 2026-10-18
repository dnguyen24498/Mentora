import { useEffect, useState } from 'react'
import { Link } from '../router'
import { describeApiError, loadHealth, loadRendererStatus, type RendererStatus } from '../api/client'
import { useInstitution } from '../institution'
import { DEFAULT_SETTINGS, useSettings } from './store'
import { Banner, BUTTON_SECONDARY, EmptyState, INPUT_CLASS, Panel, Row } from '../components/ui'

/**
 * General settings: who you are, whether the server is up, and what the server
 * decides for you.
 *
 * The institution is the tenant every request is scoped by, so it is the one
 * setting with real consequences — changing it changes which tenant's data every
 * page reads. The home region is the opposite: it is the *server's* configuration
 * (`MENTORA_HOME_REGION`), so this page reports it from a live `/renderer` read
 * rather than offering an input that could not be honoured.
 */
export default function GeneralSettings() {
  const [institution, setInstitution] = useInstitution()
  const [, updateSettings] = useSettings()
  const [health, setHealth] = useState<'unknown' | 'ok' | 'down'>('unknown')
  const [renderer, setRenderer] = useState<RendererStatus | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    void loadHealth().then(
      (result) => {
        if (!cancelled) setHealth(result.status === 'ok' ? 'ok' : 'unknown')
      },
      (cause: unknown) => {
        if (cancelled) return
        setHealth('down')
        setError(describeApiError(cause))
      },
    )
    void loadRendererStatus(institution).then(
      (status) => {
        if (!cancelled) setRenderer(status)
      },
      () => {
        // The renderer probe failing is not worth an alert: the health line
        // above already says the API is unreachable.
      },
    )
    return () => {
      cancelled = true
    }
  }, [institution])

  return (
    <div className="mx-auto grid grid-cols-1 max-w-5xl gap-6 lg:grid-cols-2">
      <Panel title="Institution">
        <div className="space-y-3">
          <div>
            <label htmlFor="institution-general" className="block text-sm font-medium text-slate-700">
              Institution id
            </label>
            <input
              id="institution-general"
              value={institution}
              onChange={(event) => setInstitution(event.target.value)}
              className={`mt-1 ${INPUT_CLASS}`}
            />
            <p className="mt-1 text-[11px] text-slate-400">
              Sent as the <span className="font-mono">X-Institution-Id</span> header on every request.
              Every installation is scoped by institution, and the server enforces that boundary —
              this selects which tenant you are looking at, it does not grant access.
            </p>
          </div>

          <button
            type="button"
            onClick={() => setInstitution('university-001')}
            className={BUTTON_SECONDARY}
          >
            Use the default institution
          </button>
        </div>
      </Panel>

      <Panel title="Server">
        {error && <Banner tone="bad">{error}</Banner>}

        <dl className="space-y-1 text-sm">
          <Row label="Health">
            {health === 'ok' ? 'ok' : health === 'down' ? 'unreachable' : 'checking…'}
          </Row>
          <Row label="Renderer">
            {renderer ? `${renderer.identity.name}@${renderer.identity.version}` : '—'}
          </Row>
          <Row label="Default mode">{renderer?.default_mode ?? '—'}</Row>
          <Row label="Data region">{renderer?.identity.data_region ?? '—'}</Row>
          <Row label="Client origin">{typeof window === 'undefined' ? '—' : window.location.origin}</Row>
        </dl>

        <p className="text-[11px] text-slate-400">
          The home region is server configuration (<span className="font-mono">MENTORA_HOME_REGION</span>),
          shown here and pinned into a running class's plan. It is not a client setting.
        </p>
      </Panel>

      <Panel title="Preferences" className="lg:col-span-2">
        <p className="text-sm text-slate-600">
          Rendering, teaching and accessibility preferences are stored in this browser and apply to
          every page. They are conveniences: nothing here changes what the server stores, seals or
          publishes.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => updateSettings(DEFAULT_SETTINGS)}
            className={BUTTON_SECONDARY}
          >
            Restore defaults
          </button>
          <Link to="/settings/rendering" className="text-xs font-medium text-indigo-600 underline">
            Rendering
          </Link>
          <Link to="/settings/teaching" className="text-xs font-medium text-indigo-600 underline">
            Teaching
          </Link>
          <Link to="/settings/accessibility" className="text-xs font-medium text-indigo-600 underline">
            Accessibility
          </Link>
        </div>
        {!renderer && <EmptyState>The renderer capability is reported once the API answers.</EmptyState>}
      </Panel>
    </div>
  )
}
