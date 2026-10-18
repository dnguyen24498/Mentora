import { useCallback, useEffect, useState } from 'react'
import {
  describeApiError,
  issueBootstrapToken,
  loadClass,
  type ClassView,
} from '../api/client'
import { describePrincipal, hasScope, isSignedIn, useSession } from '../auth/session'
import { useMode } from '../auth/mode'
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
  type Tone,
} from '../components/ui'
import { LIBRARY_PATH, Link, classroomPath, loginPath, navigate, studentPath } from '../router'

const STATE_TONE: Record<string, Tone> = {
  SCHEDULED: 'info',
  PREPARING: 'warn',
  ACTIVE: 'good',
  COMPLETED: 'neutral',
}

/**
 * A student enters a class — `/join/{classId}` (V0-021).
 *
 * This page exists because a join is **not** a link that works for everyone. The
 * credential a student's browser finally holds is bound to *their own account*,
 * so this page first establishes who is asking:
 *
 * * not signed in → sign in first. The development tenant shortcut is not a
 *   sign-in: it is a *teacher*, and joining is the student's own action, so it
 *   cannot join — the page says that rather than offering a button that can only
 *   fail.
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
  const mode = useMode()
  const [, setInstitution] = useInstitution()
  const now = useNow(1000, true)
  const [classView, setClassView] = useState<ClassView | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [joinError, setJoinError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    document.title = 'Join a class — Mentora'
  }, [])

  // The tenant for reads comes from the session; without one the development
  // shortcut's remembered institution is used, which can read a class but never
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

  async function join(): Promise<void> {
    setBusy(true)
    setJoinError(null)
    try {
      // Ask for the credential first: it is what proves the join is authorized,
      // and asking here means the student view never opens on a refusal.
      await issueBootstrapToken(classId)
      navigate(studentPath(classId))
    } catch (cause) {
      setJoinError(describeApiError(cause))
    } finally {
      setBusy(false)
    }
  }

  const signedIn = isSignedIn(session)
  const canJoin = signedIn && hasScope(session, 'join')
  const klass = classView?.class ?? null
  const running = klass?.state === 'ACTIVE'
  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <PageHeader
        nav="join"
        title="Join a class"
        subtitle={klass?.title}
        classId={classId}
        institution={session?.principal.institution_id ?? ''}
        onInstitutionChange={() => undefined}
      />

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
                <Badge tone={STATE_TONE[klass.state] ?? 'neutral'}>{klass.state}</Badge>
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
              who is asking. Sign in with the code your teacher gave you when they added you.
            </p>
            {mode.development && (
              <p className="mt-2 text-sm text-slate-700">
                This browser is in <strong>development mode</strong> (the tenant header shortcut), which
                is authorized as a <strong>teacher</strong> — joining a class is the student's own
                action, and a teacher has no seat in one.
              </p>
            )}
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
                  disabled={busy}
                  className={`${BUTTON_PRIMARY} mt-3 w-full sm:w-auto`}
                >
                  {busy ? 'Joining…' : 'Join class'}
                </button>
                <p className="mt-2 text-[11px] text-slate-400">
                  Joining asks the server for a short-lived credential scoped to this class. It is
                  subscribe-only: it cannot publish audio, and it carries none of your account's other
                  capabilities.
                </p>
              </>
            ) : (
              <Banner tone="warn">
                This account cannot request a class join. Only students join; a teacher runs a class from
                the classroom view.
              </Banner>
            )}
            {canJoin && running && (
              <p className="mt-2 text-[11px] text-slate-400">
                Prefer the teacher's view?{' '}
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
