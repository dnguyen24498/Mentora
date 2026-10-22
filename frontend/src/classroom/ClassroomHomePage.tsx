import { useCallback, useEffect, useState } from 'react'
import {
  describeApiError,
  listClasses,
  reopenClass,
  startClass,
  type ClassSummary,
} from '../api/client'
import { describePrincipal, hasScope, isStudent, useSession } from '../auth/session'
import { useInstitution } from '../institution'
import PageHeader from '../components/PageHeader'
import {
  Badge,
  Banner,
  BUTTON_PRIMARY,
  BUTTON_SECONDARY,
  BUTTON_SMALL,
  EmptyState,
  PAGE_PADDING,
  Panel,
  Row,
} from '../components/ui'
import { CLASSROOM_PATH, Link, adminPath, classroomPath } from '../router'
import { describeSchedule, useNow } from '../time'
import { STATE_TONE, stateLabel } from './classState'

/**
 * The one classroom hub — `/classroom` (V0-026, V0-028).
 *
 * The list is whatever the server says this person may see: a teacher (and an
 * institution administrator) gets the tenant's classes, a student gets only the
 * classes a teacher assigned them because `GET /classes` is scoped by role. The
 * same page therefore serves both sides of a lesson without a second "My
 * classes" destination.
 *
 * A teacher starts a scheduled class here. Since V0-028 the **class server** runs
 * the presentation in the background, so starting refreshes this list rather than
 * forcing a page that must stay open: closing the teacher's tab does not stop the
 * lesson. A student's card becomes **Join class** only when the server says the
 * class is running; the viewer has no slide controls, so watching is the whole
 * job.
 *
 * The background runner is an in-process development bridge, not the durable
 * scheduler/workflow `DEC-TECH-003` leaves `OPEN`: it stops if the API restarts
 * (a teacher can start it again from the classroom) and audio distribution is
 * still the HTTP relay, not the SFU (`DEC-TECH-004` is `OPEN`, V1-005). Students
 * follow the authoritative snapshot by a short poll (`DEC-DATA-003` is `OPEN`,
 * V1-002).
 */
export default function ClassroomHomePage() {
  const session = useSession()
  const [, setInstitution] = useInstitution()
  const now = useNow(1000, true)
  const [classes, setClasses] = useState<ClassSummary[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(true)
  const [starting, setStarting] = useState<string | null>(null)
  const [reopening, setReopening] = useState<string | null>(null)
  const [actionError, setActionError] = useState<{ classId: string; message: string } | null>(null)

  const student = isStudent(session)
  const canStart = hasScope(session, 'class:write')
  // Opening a classroom reads the pinned scenes, so the capability that decides
  // whether the link is offered is `scene:read` (a teacher and a student hold it;
  // an institution administrator reads the schedule but not the lesson).
  const canView = hasScope(session, 'scene:read')

  useEffect(() => {
    document.title = 'Classroom — Mentora'
  }, [])

  useEffect(() => {
    if (session) setInstitution(session.principal.institution_id)
  }, [session, setInstitution])

  const load = useCallback(async () => {
    setError(null)
    try {
      setClasses(await listClasses(session?.principal.institution_id ?? ''))
    } catch (cause) {
      setClasses([])
      setError(describeApiError(cause))
    } finally {
      setBusy(false)
    }
  }, [session])

  useEffect(() => {
    void load()
  }, [load])

  // A class that is still scheduled is the one thing worth watching: the moment
  // the teacher starts it, the student's card must become joinable without a
  // hidden refresh. This is the same client-local poll the student page uses,
  // not the ordered per-class stream (DEC-DATA-003 is OPEN, V1-002).
  const waiting = classes.some((item) => item.state === 'SCHEDULED' || item.state === 'PREPARING')
  useEffect(() => {
    if (!waiting) return
    const timer = window.setInterval(() => void load(), 5000)
    return () => window.clearInterval(timer)
  }, [waiting, load])

  async function start(item: ClassSummary): Promise<void> {
    setStarting(item.class_id)
    setActionError(null)
    try {
      await startClass(session?.principal.institution_id ?? '', item.class_id)
      // The class server now presents in the background. Refresh the list so the
      // row flips to running; the teacher does not have to open (or keep open) a
      // presentation page for the lesson to continue.
      await load()
    } catch (cause) {
      setActionError({ classId: item.class_id, message: describeApiError(cause) })
    } finally {
      setStarting(null)
    }
  }

  async function reopen(item: ClassSummary): Promise<void> {
    setReopening(item.class_id)
    setActionError(null)
    try {
      await reopenClass(item.class_id)
      // Reopening keeps the class id, its roster and its pinned content, and the
      // server starts presenting again from the first slide. The list is enough.
      await load()
    } catch (cause) {
      setActionError({ classId: item.class_id, message: describeApiError(cause) })
    } finally {
      setReopening(null)
    }
  }

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <PageHeader
        nav="classroom"
        title="Classroom"
        subtitle={describePrincipal(session)}
        institution={session?.principal.institution_id ?? ''}
        onInstitutionChange={() => undefined}
        institutionEditable={false}
        actions={
          <button type="button" onClick={() => void load()} className={BUTTON_SMALL}>
            Refresh
          </button>
        }
      />

      <main className={`mx-auto grid max-w-4xl grid-cols-1 gap-5 ${PAGE_PADDING}`}>
        <Banner tone="info">
          {student ? (
            <>
              Your teacher starts the class. When it is running, open it and watch: the slides move
              by themselves and you do not need any slide controls.
            </>
          ) : (
            <>
              Start a class here; the class server presents its pinned slides automatically in the
              background, so students keep watching even when no teacher tab is open. The presenter
              is a single-process development bridge: if the API restarts, open the classroom and
              start the presentation again.
            </>
          )}{' '}
          Students follow the authoritative class state by a short poll, not a media stream.
        </Banner>

        {error && <Banner tone="bad">{error}</Banner>}
        {busy && !error && <p className="text-sm text-slate-500">Loading classes…</p>}

        {!busy && !error && classes.length === 0 && (
          <Panel title="No classes yet">
            <EmptyState>
              {student
                ? 'Your teacher adds you to a class from its roster and shares its join link. If you followed a link, open it directly — the server checks that you are on that class.'
                : 'Schedule a class in Admin → Classes, then start it here. A class needs a published course version before it can start.'}
            </EmptyState>
            {!student && canStart && (
              <div className="mt-3">
                <Link to={adminPath('classes')} className={BUTTON_PRIMARY}>
                  Go to class management
                </Link>
              </div>
            )}
          </Panel>
        )}

        <div className="grid grid-cols-1 gap-4">
          {classes.map((item) => {
            const running = item.state === 'ACTIVE' || item.state === 'DEGRADED'
            const finished = item.state === 'COMPLETED'
            const scheduled = item.state === 'SCHEDULED' || item.state === 'PREPARING'
            const localError =
              actionError?.classId === item.class_id ? actionError.message : null

            return (
              <Panel
                key={item.class_id}
                title={item.title}
                actions={
                  <Badge tone={STATE_TONE[item.state] ?? 'neutral'}>{stateLabel(item.state)}</Badge>
                }
              >
                <dl className="space-y-1 text-sm">
                  <Row label="Scheduled for">
                    {item.scheduled_for ? describeSchedule(item.scheduled_for, now) : '—'}
                  </Row>
                  <Row label="Started">
                    {item.started_at ? describeSchedule(item.started_at, now) : 'not yet'}
                  </Row>
                  <Row label="Class">
                    <span className="break-all font-mono text-[11px] text-slate-400">
                      {item.class_id}
                    </span>
                  </Row>
                </dl>

                {localError && (
                  <div className="mt-3">
                    <Banner tone="bad">{localError}</Banner>
                  </div>
                )}

                {running && canView && (
                  <Link
                    to={classroomPath(item.class_id)}
                    className={`${BUTTON_PRIMARY} mt-3 w-full sm:w-auto`}
                  >
                    {student ? 'Join class' : 'Open classroom'}
                  </Link>
                )}

                {finished && canView && !student && (
                  <Link
                    to={classroomPath(item.class_id)}
                    className={`${BUTTON_SECONDARY} mt-3 w-full sm:w-auto`}
                  >
                    Review last slide
                  </Link>
                )}

                {finished && canStart && (
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => void reopen(item)}
                      disabled={reopening !== null}
                      className={`${BUTTON_PRIMARY} w-full sm:w-auto`}
                    >
                      {reopening === item.class_id ? 'Reopening…' : 'Reopen class'}
                    </button>
                  </div>
                )}

                {scheduled && canStart && (
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => void start(item)}
                      disabled={starting !== null}
                      className={`${BUTTON_PRIMARY} w-full sm:w-auto`}
                    >
                      {starting === item.class_id ? 'Starting…' : 'Start class'}
                    </button>
                    <span className="text-xs text-slate-500">
                      Starts the class; the server presents its pinned slides in the background.
                    </span>
                  </div>
                )}

                {scheduled && !canStart && (
                  <p
                    role="status"
                    className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600"
                  >
                    {student
                      ? 'Waiting for your teacher to start this class. This page checks again automatically.'
                      : 'Waiting for a teacher to start this class.'}
                  </p>
                )}

                {finished && canStart && (
                  <p className="mt-3 text-xs text-slate-500">
                    The session is over and students are locked out of the lesson until you
                    reopen it. Reopening keeps the roster and the pinned slides and starts again
                    from the first slide; you can also{' '}
                    <Link
                      to={adminPath('classes')}
                      className="font-medium text-indigo-700 hover:underline"
                    >
                      schedule a new class
                    </Link>
                    .
                  </p>
                )}

                {finished && !student && !canStart && (
                  <p className="mt-3 text-xs text-slate-500">
                    The session is over and its students are locked out of the lesson. A teacher
                    reopens it, or a new class is scheduled.
                  </p>
                )}

                {finished && student && (
                  <p
                    role="status"
                    className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600"
                  >
                    This class has ended. It is locked until your teacher reopens it.
                  </p>
                )}

                {!running && !finished && !scheduled && (
                  <p className="mt-3 text-sm text-slate-600">
                    This class is {stateLabel(item.state)}. A teacher can open the classroom when
                    the session is running.
                  </p>
                )}
              </Panel>
            )
          })}
        </div>

        {!student && canStart && classes.length > 0 && (
          <p className="text-xs text-slate-500">
            Need another class?{' '}
            <Link to={adminPath('classes')} className="font-medium text-indigo-700 hover:underline">
              Schedule one in class management
            </Link>
            .
          </p>
        )}

        {student && (
          <p className="text-xs text-slate-500">
            The classroom list is your roster. If a class is missing, ask your teacher to assign
            you. The address is{' '}
            <Link to={CLASSROOM_PATH} className="font-medium text-indigo-700 hover:underline">
              {CLASSROOM_PATH}
            </Link>
            .
          </p>
        )}
      </main>
    </div>
  )
}
