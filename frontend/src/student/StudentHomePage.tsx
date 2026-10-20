import { useCallback, useEffect, useState } from 'react'
import { describeApiError, listClasses, type ClassSummary } from '../api/client'
import { describePrincipal, useSession } from '../auth/session'
import { useInstitution } from '../institution'
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
  type Tone,
} from '../components/ui'
import { Link, joinPath } from '../router'
import { describeSchedule, useNow } from '../time'

const STATE_TONE: Record<string, Tone> = {
  SCHEDULED: 'info',
  PREPARING: 'warn',
  ACTIVE: 'good',
  COMPLETED: 'neutral',
}

/**
 * A student's own classes — `/student` (V0-024).
 *
 * The list is the student's **roster**: the server returns only the classes the
 * teacher assigned them (`GET /classes` is scoped by role), so this page cannot
 * become a window onto the institution's schedule. It is also where "wait until
 * your teacher starts" is said plainly: a scheduled class shows its time and a
 * waiting note, and the row becomes a **Join class** link only once the class is
 * `ACTIVE` — the same `NOT_STARTED` rule the join endpoint enforces.
 *
 * While any class is still scheduled the page re-reads the list on a timer, so a
 * teacher starting a class flips the row without the student having to guess
 * that a refresh is needed. That is a client-local poll, not a live event
 * stream: the ordered per-class event stream is `DEC-DATA-003` (OPEN, V1-002),
 * and the page does not pretend otherwise.
 */
export default function StudentHomePage() {
  const session = useSession()
  const [, setInstitution] = useInstitution()
  const now = useNow(1000, true)
  const [classes, setClasses] = useState<ClassSummary[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(true)

  useEffect(() => {
    document.title = 'My classes — Mentora'
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

  // A class the teacher has not started yet is the one thing worth watching: when
  // it starts, the row must become joinable without a hidden refresh. Nothing is
  // polled once every class is running or finished.
  const waiting = classes.some((item) => item.state === 'SCHEDULED')
  useEffect(() => {
    if (!waiting) return
    const timer = window.setInterval(() => void load(), 5000)
    return () => window.clearInterval(timer)
  }, [waiting, load])

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <PageHeader
        nav="student-home"
        title="My classes"
        subtitle={describePrincipal(session)}
        institution={session?.principal.institution_id ?? ''}
        onInstitutionChange={() => undefined}
        institutionEditable={false}
      >
        <button type="button" onClick={() => void load()} className={BUTTON_SECONDARY}>
          Refresh
        </button>
      </PageHeader>

      <main className={`mx-auto grid max-w-3xl grid-cols-1 gap-5 ${PAGE_PADDING}`}>
        <Banner tone="info">
          These are the classes your teacher assigned you. A class opens when your teacher starts
          it; until then it shows when it is due and says it is waiting.
        </Banner>

        {error && <Banner tone="bad">{error}</Banner>}
        {busy && !error && <p className="text-sm text-slate-500">Loading your classes…</p>}

        {!busy && !error && classes.length === 0 && (
          <Panel title="No classes yet">
            <EmptyState>
              Your teacher adds you to a class from its roster and shares its join link. If you
              followed a link, open it directly — the server checks that you are on that class.
            </EmptyState>
          </Panel>
        )}

        <div className="grid grid-cols-1 gap-4">
          {classes.map((item) => {
            const running = item.state === 'ACTIVE'
            const finished = item.state === 'COMPLETED'
            return (
              <Panel
                key={item.class_id}
                title={item.title}
                actions={
                  <Badge tone={STATE_TONE[item.state] ?? 'neutral'}>{item.state}</Badge>
                }
              >
                <dl className="space-y-1 text-sm">
                  <Row label="Scheduled for">
                    {item.scheduled_for ? describeSchedule(item.scheduled_for, now) : '—'}
                  </Row>
                  <Row label="Started">
                    {item.started_at ? describeSchedule(item.started_at, now) : 'not yet'}
                  </Row>
                </dl>

                {running ? (
                  <Link to={joinPath(item.class_id)} className={`${BUTTON_PRIMARY} mt-3 w-full sm:w-auto`}>
                    Join class
                  </Link>
                ) : (
                  <p
                    role="status"
                    className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600"
                  >
                    {finished
                      ? 'This class has finished.'
                      : 'Waiting for your teacher to start this class. This page checks again automatically.'}
                  </p>
                )}

                <p className="mt-2 font-mono text-[10px] break-all text-slate-400">
                  {item.class_id}
                </p>
              </Panel>
            )
          })}
        </div>
      </main>
    </div>
  )
}
