import { useEffect } from 'react'
import ClassroomShell from './ClassroomShell'
import { Link } from '../router'
import { useInstitution } from '../institution'
import { useClassroomSession } from './useClassroomSession'
import type { ClassroomTransport } from './state/transport'
import type { ClassroomTelemetry } from './state/telemetry'
import type { ClassroomSessionOptions } from './state/session'

export interface ClassroomPageProps {
  /** The class whose session is displayed (the `/classroom/{classId}` route). */
  classId: string
  /** Injectable so page tests drive the stream without a server (V0-007 precedent). */
  createTransport?: (institutionId: string, classId: string) => ClassroomTransport
  telemetry?: ClassroomTelemetry
  sessionOptions?: Omit<ClassroomSessionOptions, 'classId'>
}

/**
 * The classroom page.
 *
 * It is the student/teacher view of a running session: the shell renders the
 * authoritative state that the reducer projects, and a refresh restores that
 * state from the session snapshot (DEC-RUNTIME-004). It is a page of its own, so
 * it survives a deep link, a bookmark and a refresh, and it shares the tenant the
 * way the Teacher Studio does.
 */
export default function ClassroomPage({
  classId,
  createTransport,
  telemetry,
  sessionOptions,
}: ClassroomPageProps) {
  const [institution, setInstitution] = useInstitution()
  const { state, capabilities, send, resync, toggleFocusScene, updatePreferences } =
    useClassroomSession({ institutionId: institution, classId, createTransport, telemetry, sessionOptions })

  useEffect(() => {
    document.title = `Classroom ${classId} — Mentora`
  }, [classId])

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3">
          <Link to="/" className="text-sm font-medium text-slate-600 hover:text-slate-900">
            ← Library
          </Link>
          <h1 className="text-base font-semibold text-slate-800">Classroom</h1>
          <span className="truncate font-mono text-[11px] text-slate-400">{classId}</span>
          <div className="ml-auto flex items-center gap-2">
            <label htmlFor="institution" className="text-xs text-slate-500">
              Institution
            </label>
            <input
              id="institution"
              value={institution}
              onChange={(event) => setInstitution(event.target.value)}
              className="rounded border border-slate-300 px-2 py-1 text-xs"
            />
          </div>
        </div>
      </header>
      <main className="px-4 py-4">
        <ClassroomShell
          state={state}
          capabilities={capabilities}
          onNavigate={send}
          onResync={resync}
          onToggleFocusScene={toggleFocusScene}
          onPreferenceChange={updatePreferences}
        />
      </main>
    </div>
  )
}
