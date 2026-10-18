import type {
  ClassroomCommandType,
  ClassroomState,
  ClassroomStatus,
  ClassroomTransportCapabilities,
  ClassroomUiPreferences,
} from './state/types'

export interface ClassroomShellProps {
  state: ClassroomState
  capabilities: ClassroomTransportCapabilities
  onNavigate: (type: ClassroomCommandType) => void
  onResync: () => void
  onToggleFocusScene: () => void
  onPreferenceChange: (patch: Partial<ClassroomUiPreferences>) => void
}

const STATUS_LABEL: Record<ClassroomStatus, string> = {
  idle: 'Connecting…',
  resyncing: 'Resynchronising…',
  live: 'In sync',
  gap: 'Sequence gap — controls frozen',
  'stale-epoch': 'Session changed owner — resynchronising',
  disconnected: 'Disconnected — controls frozen',
}

const STATUS_STYLE: Record<ClassroomStatus, string> = {
  idle: 'bg-slate-200 text-slate-700',
  resyncing: 'bg-amber-100 text-amber-700',
  live: 'bg-emerald-100 text-emerald-700',
  gap: 'bg-rose-100 text-rose-700',
  'stale-epoch': 'bg-rose-100 text-rose-700',
  disconnected: 'bg-rose-100 text-rose-700',
}

/**
 * The classroom shell (V0-011).
 *
 * It is presentational: it renders the projection the reducer produced and calls
 * back for the two kinds of action — a command (disabled unless the transport can
 * carry one and the client is in sync) and a resync. Group student audio is out
 * of scope, so nothing here activates a microphone (DEC-TURN-001).
 */
export default function ClassroomShell({
  state,
  capabilities,
  onNavigate,
  onResync,
  onToggleFocusScene,
  onPreferenceChange,
}: ClassroomShellProps) {
  const { events, ui } = state
  const status = events.status
  const inSync = status === 'live'
  const canControl = inSync && capabilities.liveEvents && capabilities.commands
  const frozen = !inSync
  const scene = events.scene
  const reason = events.freezeReason
  const recoveryMessage =
    reason === 'gap'
      ? 'A sequence gap was detected: the client missed one or more events. Unsafe controls are disabled until it resynchronises from the authoritative snapshot.'
      : reason === 'stale-epoch'
        ? 'The session is now owned by another actor epoch. Stale effects are discarded; resynchronising from the authoritative snapshot.'
        : reason === 'disconnected'
          ? 'The authoritative snapshot could not be loaded. The last known state is shown, but controls are frozen until reconnection.'
          : 'Resynchronising from the authoritative snapshot…'

  return (
    <section
      data-testid="classroom-shell"
      data-reduced-motion={ui.preferences.reducedMotion}
      className={[
        'mx-auto max-w-6xl rounded-lg border bg-white p-4 shadow-sm',
        ui.preferences.highContrast ? 'border-slate-900 ring-2 ring-slate-900' : 'border-slate-200',
      ].join(' ')}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h2 className="text-base font-semibold text-slate-800">Live classroom</h2>
        <span
          data-testid="classroom-status"
          data-status={status}
          role="status"
          aria-live="polite"
          className={`rounded px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[status]}`}
        >
          {STATUS_LABEL[status]}
        </span>
        <span className="text-xs text-slate-500">
          session <span className="font-mono">{events.sessionState ?? '—'}</span>
        </span>
      </div>

      {frozen && (
        <div
          data-testid="classroom-recovery"
          data-reason={reason ?? status}
          role={reason === 'gap' || reason === 'stale-epoch' || reason === 'disconnected' ? 'alert' : 'status'}
          className="mt-3 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800"
        >
          {recoveryMessage}
        </div>
      )}

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <section aria-labelledby="classroom-scene-heading" className="rounded border border-slate-200 p-4">
          <h3 id="classroom-scene-heading" className="text-sm font-semibold text-slate-700">
            Scene
          </h3>
          <p data-testid="classroom-scene-id" className="mt-2 font-mono text-lg text-slate-900">
            {scene.sceneId ?? 'No scene yet'}
          </p>
          <dl className="mt-3 grid grid-cols-2 gap-2 text-sm text-slate-600">
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-400">Section</dt>
              <dd>{scene.sectionIndex ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-400">Step</dt>
              <dd>{scene.stepId ?? 'scene start'}</dd>
            </div>
          </dl>
          <p className="mt-3 text-xs text-slate-500">
            The pinned package&apos;s visual scene is presented by the timeline (V0-013); this view
            shows the authoritative runtime state.
          </p>
        </section>

        <aside aria-labelledby="classroom-state-heading" className="rounded border border-slate-200 p-4">
          <h3 id="classroom-state-heading" className="text-sm font-semibold text-slate-700">
            Authoritative state
          </h3>
          <dl className="mt-3 space-y-2 text-sm text-slate-600">
            <div className="flex justify-between gap-2">
              <dt className="shrink-0">Actor epoch</dt>
              <dd className="min-w-0 truncate font-mono">{events.epoch ?? '—'}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="shrink-0">Last sequence</dt>
              <dd className="min-w-0 truncate font-mono">{events.lastSequence}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="shrink-0">State version</dt>
              <dd className="min-w-0 truncate font-mono">{events.stateVersion}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="shrink-0">Checkpoint</dt>
              <dd className="min-w-0 truncate font-mono">{events.checkpoint?.label ?? '—'}</dd>
            </div>
          </dl>
          {events.lastOutcome && (
            <p data-testid="classroom-last-outcome" className="mt-3 text-xs text-slate-400">
              Last event: {events.lastOutcome}
            </p>
          )}
        </aside>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => onNavigate('NAVIGATE_PREVIOUS')}
          disabled={!canControl}
          className="inline-flex min-h-11 items-center justify-center rounded border border-slate-300 px-3 py-2.5 text-sm font-medium text-slate-700 disabled:cursor-not-allowed disabled:opacity-50 lg:min-h-0 lg:py-1.5"
        >
          Previous scene
        </button>
        <button
          type="button"
          onClick={() => onNavigate('NAVIGATE_NEXT')}
          disabled={!canControl}
          className="inline-flex min-h-11 items-center justify-center rounded border border-slate-300 px-3 py-2.5 text-sm font-medium text-slate-700 disabled:cursor-not-allowed disabled:opacity-50 lg:min-h-0 lg:py-1.5"
        >
          Next scene
        </button>
        <button
          type="button"
          onClick={onResync}
          disabled={status === 'resyncing'}
          className="inline-flex min-h-11 items-center justify-center rounded bg-slate-800 px-3 py-2.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50 lg:min-h-0 lg:py-1.5"
        >
          Resynchronise
        </button>
        <button
          type="button"
          onClick={onToggleFocusScene}
          aria-pressed={ui.focusScene}
          className="inline-flex min-h-11 items-center justify-center rounded border border-slate-300 px-3 py-2.5 text-sm font-medium text-slate-700 lg:min-h-0 lg:py-1.5"
        >
          Focus scene
        </button>
      </div>

      <fieldset className="mt-4 flex flex-wrap items-center gap-4 border-t border-slate-100 pt-3 text-sm text-slate-600">
        <legend className="sr-only">Accessibility preferences</legend>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={ui.preferences.reducedMotion}
            onChange={(event) => onPreferenceChange({ reducedMotion: event.target.checked })}
          />
          Reduce motion
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={ui.preferences.highContrast}
            onChange={(event) => onPreferenceChange({ highContrast: event.target.checked })}
          />
          High contrast
        </label>
      </fieldset>

      {!capabilities.liveEvents && (
        <p data-testid="classroom-transport-notice" className="mt-4 text-xs text-slate-500">
          This build reads the authoritative snapshot only. The ordered per-class event stream and
          command path arrive with V1-002 (<span className="font-mono">DEC-DATA-003</span> is OPEN),
          so live controls stay disabled.
        </p>
      )}
    </section>
  )
}
