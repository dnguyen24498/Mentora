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
    <div className="min-h-screen bg-academic-canvas bg-academic-grid text-slate-900">
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

      <main className={`mx-auto grid max-w-4xl grid-cols-1 gap-6 ${PAGE_PADDING}`}>
        {/* Student Portal Academic Hero */}
        <section className="relative overflow-hidden rounded-2xl border border-slate-200/80 bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900 p-6 text-white shadow-xl">
          <div className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full bg-emerald-500/10 blur-3xl" />
          <div className="pointer-events-none absolute -bottom-16 -left-16 h-56 w-56 rounded-full bg-indigo-500/15 blur-3xl" />
          <div className="relative flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-emerald-400">
                <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse-subtle" />
                Student Academic Portal
              </div>
              <h2 className="mt-1 text-2xl font-serif font-bold text-white tracking-tight">
                Course Enrolment &amp; Live Lectures
              </h2>
              <p className="mt-1.5 text-xs text-slate-300 max-w-xl leading-relaxed">
                Lectures synchronize in real time with your instructor. Active sessions allow immediate hall admission; scheduled sessions will update automatically once opened.
              </p>
            </div>
            <div className="flex items-center gap-3 self-start md:self-auto shrink-0">
              <div className="rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 backdrop-blur-sm text-center">
                <div className="text-xl font-bold font-serif text-white">
                  {classes.filter((c) => c.state === 'ACTIVE').length}
                </div>
                <div className="text-[10px] font-medium uppercase tracking-wider text-emerald-400">
                  Live Now
                </div>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 backdrop-blur-sm text-center">
                <div className="text-xl font-bold font-serif text-white">
                  {classes.length}
                </div>
                <div className="text-[10px] font-medium uppercase tracking-wider text-slate-300">
                  Enrolled
                </div>
              </div>
            </div>
          </div>
        </section>

        <Banner tone="info">
          These are the classes your teacher assigned you. A class opens when your teacher starts
          it; until then it shows when it is due and says it is waiting.
        </Banner>

        {error && <Banner tone="bad">{error}</Banner>}
        {busy && !error && (
          <div className="flex items-center justify-center p-8 rounded-xl border border-slate-200 bg-white text-sm text-slate-500">
            <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-indigo-600" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            Loading your classes…
          </div>
        )}

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
              <div
                key={item.class_id}
                className={`relative overflow-hidden rounded-xl border transition-all duration-200 ${
                  running
                    ? 'border-emerald-300/80 bg-white shadow-lg ring-1 ring-emerald-500/20'
                    : 'border-slate-200/80 bg-white/95 shadow-sm hover:shadow-md'
                }`}
              >
                {running && (
                  <div className="h-1 bg-gradient-to-r from-emerald-500 via-teal-400 to-indigo-500" />
                )}
                <div className="p-5 sm:p-6">
                  <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-4">
                    <div>
                      <h3 className="text-lg font-serif font-bold text-slate-900 tracking-tight">
                        {item.title}
                      </h3>
                      <p className="mt-0.5 font-mono text-[11px] text-slate-400">
                        Course: {item.course_id}
                      </p>
                    </div>
                    <Badge tone={STATE_TONE[item.state] ?? 'neutral'}>{item.state}</Badge>
                  </div>

                  <dl className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm bg-slate-50/70 p-3.5 rounded-lg border border-slate-100">
                    <Row label="Scheduled for">
                      {item.scheduled_for ? describeSchedule(item.scheduled_for, now) : '—'}
                    </Row>
                    <Row label="Started">
                      {item.started_at ? describeSchedule(item.started_at, now) : 'not yet'}
                    </Row>
                  </dl>

                  <div className="mt-4 pt-2">
                    {running ? (
                      <Link
                        to={joinPath(item.class_id)}
                        className={`${BUTTON_PRIMARY} w-full sm:w-auto inline-flex items-center justify-center gap-2 !bg-emerald-600 hover:!bg-emerald-700 !shadow-emerald-600/20`}
                      >
                        <span className="h-2 w-2 rounded-full bg-white animate-pulse" />
                        Join class
                      </Link>
                    ) : (
                      <p
                        role="status"
                        className="rounded-lg bg-slate-50 border border-slate-100 px-3.5 py-2.5 text-sm text-slate-600 flex items-center gap-2"
                      >
                        <span className="text-slate-400">ℹ</span>
                        {finished
                          ? 'This class has finished.'
                          : 'Waiting for your teacher to start this class. This page checks again automatically.'}
                      </p>
                    )}
                  </div>

                  <p className="mt-3 font-mono text-[10px] break-all text-slate-400">
                    ID: {item.class_id}
                  </p>
                </div>
              </div>
            )
          })}
        </div>
      </main>
    </div>
  )
}
