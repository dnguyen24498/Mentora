import { useCallback, useEffect, useState } from 'react'
import {
  describeApiError,
  issueBootstrapToken,
  loadClass,
  type ClassView,
} from '../api/client'
import { describePrincipal, hasScope, isSignedIn, useSession } from '../auth/session'
import { useInstitution } from '../institution'
import { describeSchedule, useNow } from '../time'
import PageHeader from '../components/PageHeader'
import {
  Badge,
  Banner,
  BUTTON_PRIMARY,
  BUTTON_SECONDARY,
  EmptyState,
  PAGE_PADDING,
  Panel,
  Row,
  TOUCH_TARGET,
} from '../components/ui'
import { LIBRARY_PATH, Link, classroomPath, loginPath, navigate } from '../router'
import { STATE_TONE, stateLabel } from '../classroom/classState'

/**
 * A student enters a class — `/join/{classId}` (V0-021).
 *
 * This page exists because a join is **not** a link that works for everyone. The
 * credential a student's browser finally holds is bound to *their own account*,
 * so this page first establishes who is asking:
 *
 * * not signed in → the route guard has already sent the browser to sign in, so
 *   this is only a defensive fallback; a teacher signed in here is told plainly
 *   that they have no seat in the class, instead of being offered a button that
 *   can only fail.
 * * signed in → the class is shown, and "Join class" asks the server for the
 *   join credential. A refusal is reported with its precise reason: not on the
 *   roster (`NOT_ENROLLED`), the class has not started (`NOT_STARTED`), or the
 *   class is not in this tenant at all (`NOT_FOUND`).
 *
 * Pressing Join leads to the student's own fullscreen view of the class, which
 * requests its own credential again — so a refresh, a lost tab or a shared link
 * all end in the same place, and the credential is never the thing that is
 * stored.
 */
export default function JoinClassPage({ classId }: { classId: string }) {
  const session = useSession()
  const [, setInstitution] = useInstitution()
  const now = useNow(1000, true)
  const [classView, setClassView] = useState<ClassView | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [joinError, setJoinError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    document.title = 'Join a class — Mentora'
  }, [])

  // The tenant for reads comes from the session. Without one (the guard's job)
  // the remembered institution is used, which can still read a class but never
  // join it.
  useEffect(() => {
    if (session) setInstitution(session.principal.institution_id)
  }, [session, setInstitution])

  const load = useCallback(async () => {
    setLoadError(null)
    try {
      setClassView(await loadClass(session?.principal.institution_id ?? '', classId))
    } catch (cause) {
      setClassView(null)
      setLoadError(describeApiError(cause))
    }
  }, [classId, session])

  useEffect(() => {
    void load()
  }, [load])

  // A student who opened the link before the lesson began should not have to
  // guess when to press Refresh: while the class is still scheduled, re-read it,
  // and the join button becomes available the moment the teacher starts it. An
  // ended class is watched for the same reason: a reopen returns it to ACTIVE.
  // A client-local poll, not a live event stream (DEC-DATA-003 is OPEN, V1-002).
  const classState = classView?.class.state
  useEffect(() => {
    if (classState !== 'SCHEDULED' && classState !== 'COMPLETED') return
    const timer = window.setInterval(() => void load(), 5000)
    return () => window.clearInterval(timer)
  }, [classState, load])

  async function join(): Promise<void> {
    setBusy(true)
    setJoinError(null)
    try {
      // Ask for the credential first: it is what proves the join is authorized,
      // and asking here means the student view never opens on a refusal.
      await issueBootstrapToken(classId)
      navigate(classroomPath(classId))
    } catch (cause) {
      setJoinError(describeApiError(cause))
    } finally {
      setBusy(false)
    }
  }

  const signedIn = isSignedIn(session)
  const canJoin = signedIn && hasScope(session, 'join')
  const klass = classView?.class ?? null
  const running = klass?.state === 'ACTIVE' || klass?.state === 'DEGRADED'
  const finished = klass?.state === 'COMPLETED'
  return (
    <div className="min-h-screen bg-academic-canvas text-slate-900 bg-academic-grid">
      <PageHeader
        nav="join"
        title="Join a class"
        subtitle={klass?.title}
        classId={classId}
        institution={session?.principal.institution_id ?? ''}
        onInstitutionChange={() => undefined}
      />

      <div className="mx-auto max-w-3xl px-4 pt-6 pb-2 sm:px-6">
        <div className="rounded-2xl border border-indigo-100/80 bg-gradient-to-r from-slate-900 via-indigo-950 to-blue-950 p-6 text-white shadow-sm sm:p-7">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-indigo-200">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            Lecture Hall Access
          </span>
          <h2 className="mt-2 text-xl font-bold tracking-tight text-white sm:text-2xl">
            {klass?.title ?? 'Classroom Entry'}
          </h2>
          <p className="mt-1 text-xs text-indigo-200/90 leading-relaxed">
            Verify your enrolled student credentials and enter the real-time AI lecture hall.
          </p>
        </div>
      </div>

      <main className={`${PAGE_PADDING} mx-auto grid grid-cols-1 max-w-3xl gap-6`}>
        {loadError && <Banner tone="bad">{loadError}</Banner>}

        <Panel
          title="This class"
          actions={
            <button type="button" onClick={() => void load()} disabled={busy} className={BUTTON_SECONDARY}>
              Refresh
            </button>
          }
        >
          {!klass && !loadError && <EmptyState>Loading the class…</EmptyState>}
          {klass && (
            <dl className="space-y-1 text-sm">
              <Row label="Title">{klass.title}</Row>
              <Row label="State">
                <Badge tone={STATE_TONE[klass.state] ?? 'neutral'}>{stateLabel(klass.state)}</Badge>
              </Row>
              <Row label="Scheduled for">
                {klass.scheduled_for ? describeSchedule(klass.scheduled_for, now) : '—'}
              </Row>
              <Row label="Starts">{klass.started_at ?? 'not yet started'}</Row>
            </dl>
          )}
          <p className="text-[11px] text-slate-400">
            A join credential is issued only while the class is running, so a class that is still
            scheduled says so instead of appearing to work.
          </p>
        </Panel>

        {!signedIn ? (
          <Panel title="Sign in to join">
            <p className="text-sm text-slate-700">
              A join credential is bound to <strong>your own account</strong>, so the class needs to know
              who is asking. Sign in with the password your teacher set for you when they added you.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Link to={loginPath(`/join/${classId}`)} className={BUTTON_PRIMARY}>
                Sign in
              </Link>
              <Link to={LIBRARY_PATH} className={BUTTON_SECONDARY}>
                Back to the library
              </Link>
            </div>
          </Panel>
        ) : (
          <Panel title="You">
            <p className="text-sm text-slate-700">
              Signed in as <strong>{describePrincipal(session)}</strong>.
            </p>
            {canJoin ? (
              <>
                <button
                  type="button"
                  onClick={() => void join()}
                  disabled={busy || !running}
                  className={`${BUTTON_PRIMARY} mt-3 w-full sm:w-auto`}
                >
                  {busy ? 'Joining…' : running ? 'Join class' : finished ? 'Class ended' : 'Waiting for your teacher'}
                </button>
                {running ? (
                  <p className="mt-2 text-[11px] text-slate-400">
                    Joining asks the server for a short-lived credential scoped to this class. It is
                    subscribe-only: it cannot publish audio, and it carries none of your account's other
                    capabilities.
                  </p>
                ) : finished ? (
                  <p role="status" className="mt-2 text-[11px] text-slate-500">
                    This class has ended. The lesson is locked until your teacher reopens it. This page
                    checks again automatically, so a reopen will enable Join by itself.
                  </p>
                ) : (
                  <p role="status" className="mt-2 text-[11px] text-slate-500">
                    Only your teacher can start the class, and a join credential is issued once it is
                    running. This page checks again automatically, so there is nothing to do but wait.
                  </p>
                )}
              </>
            ) : (
              <Banner tone="warn">
                This account cannot request a class join. Only students join; a teacher runs a class from
                the classroom view.
              </Banner>
            )}
            {canJoin && running && (
              <p className="mt-2 text-[11px] text-slate-400">
                Want to skip ahead?{' '}
                <Link to={classroomPath(classId)} className={`text-indigo-700 hover:underline ${TOUCH_TARGET}`}>
                  Open the classroom
                </Link>
              </p>
            )}
          </Panel>
        )}

        {joinError && <Banner tone="bad">{joinError}</Banner>}
      </main>
    </div>
  )
}
