import { useEffect } from 'react'
import ClassroomShell from './ClassroomShell'
import TeacherStage from './TeacherStage'
import PageHeader from '../components/PageHeader'
import { PAGE_PADDING } from '../components/ui'
import { useInstitution, writeSelectedClass } from '../institution'
import { useClassroomSession } from './useClassroomSession'
import { hasScope, useSession } from '../auth/session'
import { Link, adminPath, joinPath } from '../router'
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
  const session = useSession()
  const canTeach = hasScope(session, 'class:write')
  const {
    state,
    capabilities,
    send,
    resync,
    applySnapshot,
    toggleFocusScene,
    updatePreferences,
  } = useClassroomSession({ institutionId: institution, classId, createTransport, telemetry, sessionOptions })

  useEffect(() => {
    document.title = `Classroom ${classId} — Mentora`
  }, [classId])

  // The shared nav links back to this class's classroom from the other pages.
  useEffect(() => {
    writeSelectedClass(classId)
  }, [classId])

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <PageHeader
        nav="classroom"
        title="Classroom"
        subtitle={<span className="font-mono">{classId}</span>}
        classId={classId}
        institution={institution}
        onInstitutionChange={setInstitution}
      />
      <main className={PAGE_PADDING}>
        {hasScope(session, 'class:write') && (
          <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600">
            <span className="min-w-0 flex-1">
              Assign students, start this class, or share its join link from class management.
            </span>
            <Link to={adminPath('classes')} className="font-medium text-indigo-700 hover:underline">
              Class management
            </Link>
            <Link to={joinPath(classId)} className="font-medium text-indigo-700 hover:underline">
              Student join link
            </Link>
          </div>
        )}
        {canTeach && (
          <TeacherStage
            classId={classId}
            sessionState={state.events.sessionState}
            currentSceneId={state.events.scene.sceneId}
            currentSectionIndex={state.events.scene.sectionIndex}
            stateVersion={state.events.stateVersion}
            onSnapshot={applySnapshot}
            onResync={resync}
          />
        )}
        <ClassroomShell
          state={state}
          capabilities={capabilities}
          onNavigate={send}
          onResync={resync}
          onToggleFocusScene={toggleFocusScene}
          onPreferenceChange={updatePreferences}
          hideSceneControls={canTeach}
        />
      </main>
    </div>
  )
}
