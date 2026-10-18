import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, classroomPath } from '../router'
import {
  describeApiError,
  enrollStudent,
  listClasses,
  listCourses,
  listEnrollments,
  listMaterials,
  loadClass,
  scheduleClass,
  startClass,
  type ClassSummary,
  type ClassView,
  type Course,
  type Enrollment,
  type Material,
} from '../api/client'
import { readSelectedClass, writeSelectedClass } from '../institution'
import { useSettings } from '../settings/store'
import {
  describeSchedule,
  fromDateTimeLocalValue,
  isDue,
  useNow,
} from '../time'
import {
  Badge,
  Banner,
  BUTTON_PRIMARY,
  EmptyState,
  INPUT_CLASS,
  Panel,
  Row,
  type Tone,
} from '../components/ui'

const STATE_TONE: Record<string, Tone> = {
  SCHEDULED: 'info',
  PREPARING: 'warn',
  ACTIVE: 'good',
  COMPLETED: 'neutral',
}

/**
 * Classes and their enrolments — the admin view.
 *
 * The write verbs are the runtime's own: **schedule** a class (it is not running
 * yet), **start** it (which pins the exact runtime tuple once, `V0-009`) and
 * **enrol** a student (idempotent). There is no "edit class" or "delete class":
 * once started, a session's pinned versions and snapshot are the historical
 * record, and a correction is a new class on a new version.
 *
 * A class can be given a datetime, and this page can **start it when that time
 * arrives** while it is open. That trigger is deliberately client-local: the
 * backend records `scheduled_for` and never acts on it, because an automatic
 * start would be a durable workflow/scheduler and `DEC-TECH-003` is `OPEN`. So
 * nothing runs while this page is closed, the page says exactly that, and a
 * refusal (a class whose course was never published cannot start) is reported
 * per class rather than swallowed.
 */
export default function ClassesAdmin({ institutionId }: { institutionId: string }) {
  const [settings, updateSettings] = useSettings()
  const autoStart = settings.autoStartDueClasses
  const [courses, setCourses] = useState<Course[]>([])
  const [classes, setClasses] = useState<ClassSummary[]>([])
  const [courseId, setCourseId] = useState('')
  const [materials, setMaterials] = useState<Material[]>([])
  const [title, setTitle] = useState('')
  const [versionId, setVersionId] = useState('')
  const [scheduledFor, setScheduledFor] = useState('')
  const [selected, setSelected] = useState(readSelectedClass)
  const [detail, setDetail] = useState<ClassView | null>(null)
  const [enrollments, setEnrollments] = useState<Enrollment[]>([])
  const [studentId, setStudentId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  // What the automatic start did, per class. Kept as a record so a class is
  // reported once and a failed attempt is not retried every tick.
  const [autoResults, setAutoResults] = useState<Record<string, string>>({})
  const attempted = useRef<Set<string>>(new Set())

  const refreshClasses = useCallback(async () => {
    try {
      const loaded = await listClasses(institutionId)
      setClasses(loaded)
      return loaded
    } catch (cause) {
      setError(describeApiError(cause))
      return []
    }
  }, [institutionId])

  const refreshDetail = useCallback(async (classId: string) => {
    if (!classId) {
      setDetail(null)
      setEnrollments([])
      return
    }
    try {
      const [view, enrolled] = await Promise.all([
        loadClass(institutionId, classId),
        listEnrollments(institutionId, classId),
      ])
      setDetail(view)
      setEnrollments(enrolled.enrollments)
    } catch (cause) {
      setDetail(null)
      setError(describeApiError(cause))
    }
  }, [institutionId])

  useEffect(() => {
    let cancelled = false
    setError(null)
    setNotice(null)
    void (async () => {
      const loaded = await listCourses(institutionId)
      if (cancelled) return
      setCourses(loaded)
      setCourseId((previous) => previous || (loaded[0]?.course_id ?? ''))
      await refreshClasses()
    })()
    return () => {
      cancelled = true
    }
  }, [institutionId, refreshClasses])

  useEffect(() => {
    writeSelectedClass(selected)
    void refreshDetail(selected)
  }, [selected, refreshDetail])

  // The version ids a teacher may pin a class to are the course's materials.
  useEffect(() => {
    let cancelled = false
    if (!courseId) {
      setMaterials([])
      return
    }
    void listMaterials(institutionId, courseId)
      .then(
        (loaded) => {
          if (!cancelled) setMaterials(loaded)
        },
        (cause: unknown) => {
          if (!cancelled) setError(describeApiError(cause))
        },
      )
    return () => {
      cancelled = true
    }
  }, [institutionId, courseId])

  async function schedule() {
    if (!courseId) return
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const created = await scheduleClass(institutionId, {
        course_id: courseId,
        title: title.trim() || null,
        version_id: versionId.trim() || null,
        // Read as the teacher's own local time. The API records it and never acts
        // on it (DEC-TECH-003 stays OPEN); the page's own clock is what waits.
        scheduled_for: fromDateTimeLocalValue(scheduledFor),
      })
      setTitle('')
      setVersionId('')
      setScheduledFor('')
      await refreshClasses()
      setSelected(created.class_id)
      setNotice(
        created.scheduled_for
          ? `Scheduled "${created.title}" for ${describeSchedule(created.scheduled_for, now)}. ` +
              'It starts when you start it, or on time while this page is open with auto-start on.'
          : `Scheduled "${created.title}". Nothing runs until you start it — give it a time and ` +
              'turn auto-start on to have that happen by itself.',
      )
    } catch (cause) {
      setError(describeApiError(cause))
    } finally {
      setBusy(false)
    }
  }

  async function start() {
    if (!selected) return
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const view = await startClass(institutionId, selected)
      setDetail(view)
      await refreshClasses()
      setNotice(
        view.created
          ? 'Class started: the runtime tuple is now pinned and the class is ACTIVE.'
          : 'This class was already started — the same pinned tuple was returned.',
      )
    } catch (cause) {
      setError(describeApiError(cause))
    } finally {
      setBusy(false)
    }
  }

  async function enrol() {
    if (!selected || !studentId.trim()) return
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const enrollment = await enrollStudent(institutionId, selected, studentId.trim())
      setStudentId('')
      await refreshDetail(selected)
      setNotice(
        enrollment.created
          ? `Enrolled ${enrollment.student_id}.`
          : `${enrollment.student_id} was already enrolled.`,
      )
    } catch (cause) {
      setError(describeApiError(cause))
    } finally {
      setBusy(false)
    }
  }

  const versions = (detail?.session_plan?.versions ?? {}) as Record<string, unknown>

  // The clock that drives both the countdowns and the automatic start. It runs
  // only while there is something to watch, so an idle page leaves no timer behind.
  const watched = classes.filter((item) => item.state === 'SCHEDULED' && item.scheduled_for)
  const now = useNow(1000, autoStart || watched.length > 0)

  // Switching auto-start off forgets the attempts, so switching it back on retries
  // a start that failed instead of skipping that class for ever.
  useEffect(() => {
    if (!autoStart) attempted.current.clear()
  }, [autoStart])

  // The automatic start. While this page is open, a class whose time has come is
  // started — the same idempotent `POST /classes/{id}/start` the button uses, so a
  // replay is harmless. Nothing watches while the page is closed: there is no
  // server-side scheduler (DEC-TECH-003 is OPEN), and the note in the panel says so.
  useEffect(() => {
    if (!autoStart) return
    const due = classes.filter(
      (item) =>
        item.state === 'SCHEDULED' &&
        isDue(item.scheduled_for, now) &&
        !attempted.current.has(item.class_id),
    )
    if (due.length === 0) return
    // Claim them synchronously: the clock ticks again before the request settles,
    // and one class must never be started twice by two ticks.
    for (const item of due) attempted.current.add(item.class_id)

    void (async () => {
      for (const item of due) {
        try {
          const view = await startClass(institutionId, item.class_id)
          setAutoResults((previous) => ({
            ...previous,
            [item.class_id]: view.created
              ? `Started "${item.title}" at its scheduled time.`
              : `"${item.title}" was already started; its pinned tuple is unchanged.`,
          }))
          if (selected === item.class_id) setDetail(view)
        } catch (cause) {
          setAutoResults((previous) => ({
            ...previous,
            [item.class_id]: `Could not start "${item.title}": ${describeApiError(cause)}`,
          }))
        }
      }
      await refreshClasses()
    })()
  }, [autoStart, classes, institutionId, now, refreshClasses, selected])

  return (
    <div className="mx-auto grid max-w-7xl gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
      <div className="space-y-6">
        <Panel title="Schedule a class">
          <div className="space-y-3">
            <div>
              <label htmlFor="class-course" className="block text-sm font-medium text-slate-700">
                Course
              </label>
              <select
                id="class-course"
                value={courseId}
                onChange={(event) => setCourseId(event.target.value)}
                className={`${INPUT_CLASS} mt-1`}
              >
                {courses.length === 0 && <option value="">No courses yet</option>}
                {courses.map((course) => (
                  <option key={course.course_id} value={course.course_id}>
                    {course.title}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="class-title" className="block text-sm font-medium text-slate-700">
                Title
              </label>
              <input
                id="class-title"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="Period 3 — Biology"
                className={`${INPUT_CLASS} mt-1`}
              />
            </div>

            <div>
              <label htmlFor="class-version" className="block text-sm font-medium text-slate-700">
                Course version (optional)
              </label>
              <input
                id="class-version"
                list="class-version-options"
                value={versionId}
                onChange={(event) => setVersionId(event.target.value)}
                placeholder="leave empty for the current published version"
                className={`${INPUT_CLASS} mt-1 font-mono text-xs`}
              />
              <datalist id="class-version-options">
                {materials.map((material) => (
                  <option key={material.version_id} value={material.version_id}>
                    {material.filename}
                  </option>
                ))}
              </datalist>
              <p className="mt-1 text-[11px] text-slate-400">
                A version pins this class to one publication even after a correction is published.
              </p>
            </div>

            <div>
              <label
                htmlFor="class-scheduled-for"
                className="block text-sm font-medium text-slate-700"
              >
                Scheduled for (optional)
              </label>
              <input
                id="class-scheduled-for"
                type="datetime-local"
                value={scheduledFor}
                onChange={(event) => setScheduledFor(event.target.value)}
                className={`${INPUT_CLASS} mt-1`}
              />
              <p className="mt-1 text-[11px] text-slate-400">
                Read on your own clock and recorded with the class. The server never acts on it — an
                automatic start would be a durable scheduler, and{' '}
                <span className="font-mono">DEC-TECH-003</span> is OPEN — so the waiting is done by an
                open page, with auto-start below.
              </p>
            </div>

            <button
              type="button"
              onClick={() => void schedule()}
              disabled={busy || !courseId}
              className={`${BUTTON_PRIMARY} w-full`}
            >
              Schedule class
            </button>
          </div>
        </Panel>

        <Panel
          title="Classes"
          actions={
            <label className="flex items-center gap-1.5 py-1 text-xs text-slate-600 sm:text-[11px]">
              <input
                type="checkbox"
                data-testid="class-auto-start"
                checked={autoStart}
                onChange={(event) =>
                  updateSettings({ autoStartDueClasses: event.target.checked })
                }
              />
              Auto-start when due
            </label>
          }
        >
          <ul className="space-y-1.5">
            {classes.map((item) => {
              const active = item.class_id === selected
              const due = isDue(item.scheduled_for, now)
              return (
                <li key={item.class_id}>
                  <button
                    type="button"
                    onClick={() => setSelected(item.class_id)}
                    aria-pressed={active}
                    className={`flex w-full items-center gap-2 rounded-lg border px-3 py-2 text-left ${
                      active ? 'border-indigo-500 bg-indigo-50' : 'border-slate-200 hover:bg-slate-50'
                    }`}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-slate-800">
                        {item.title}
                      </span>
                      {item.scheduled_for && (
                        <span
                          data-testid={`class-schedule-${item.class_id}`}
                          className={`block truncate text-[10px] ${
                            due && item.state === 'SCHEDULED'
                              ? 'font-medium text-amber-700'
                              : 'text-slate-500'
                          }`}
                        >
                          {describeSchedule(item.scheduled_for, now)}
                        </span>
                      )}
                    </span>
                    <Badge tone={STATE_TONE[item.state] ?? 'neutral'}>{item.state}</Badge>
                  </button>
                </li>
              )
            })}
          </ul>
          {classes.length === 0 && <EmptyState>No classes yet.</EmptyState>}

          <p data-testid="class-schedule-note" className="text-[11px] text-slate-400">
            A class with a time is started by <em>this page</em> while it is open. There is no
            server-side scheduler — a durable one is <span className="font-mono">DEC-TECH-003</span>,
            still OPEN — so closing this page stops the waiting, and pressing Start stays available
            either way.
          </p>

          {Object.keys(autoResults).length > 0 && (
            <ul
              data-testid="admin-auto-start-results"
              role="status"
              className="space-y-1 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-[11px] text-slate-700"
            >
              {Object.entries(autoResults).map(([classId, message]) => (
                <li key={classId}>{message}</li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <div className="space-y-6">
        {error && <Banner tone="bad">{error}</Banner>}
        {notice && <Banner tone="good">{notice}</Banner>}

        {!detail && <Panel title="Class detail"><EmptyState>Select a class.</EmptyState></Panel>}

        {detail && (
          <>
            <Panel
              title="Class detail"
              actions={
                <div className="flex flex-wrap items-center gap-2">
                  <Link
                    to={classroomPath(detail.class.class_id)}
                    className="inline-flex min-h-11 items-center justify-center rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 lg:min-h-0 lg:px-2 lg:py-1 lg:text-[11px]"
                  >
                    Open classroom
                  </Link>
                  <button
                    type="button"
                    onClick={() => void start()}
                    disabled={busy || detail.class.state !== 'SCHEDULED'}
                    className="inline-flex min-h-11 items-center justify-center rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-40 lg:min-h-0 lg:px-2 lg:py-1 lg:text-[11px]"
                  >
                    Start
                  </button>
                </div>
              }
            >
              <dl className="space-y-1 text-sm">
                <Row label="Class">{detail.class.class_id}</Row>
                <Row label="Course">{detail.class.course_id}</Row>
                <Row label="State">{detail.class.state}</Row>
                <Row label="Version">{detail.class.version_id ?? 'current published'}</Row>
                <Row label="Scheduled for">
                  {detail.class.scheduled_for
                    ? describeSchedule(detail.class.scheduled_for, now)
                    : '—'}
                </Row>
              </dl>

              {detail.session ? (
                <dl className="space-y-1 border-t border-slate-100 pt-3 text-sm">
                  <Row label="Session">{detail.session.session_id}</Row>
                  <Row label="Session state">{detail.session.state}</Row>
                  <Row label="Actor epoch">{detail.session.actor_epoch}</Row>
                  <Row label="State version">{detail.session.state_version}</Row>
                  <Row label="Event sequence">{detail.session.event_sequence}</Row>
                </dl>
              ) : (
                <p className="border-t border-slate-100 pt-3 text-[11px] text-slate-400">
                  Not started: no session and no pinned versions exist yet.
                </p>
              )}
            </Panel>

            {detail.session_plan && (
              <Panel title="Pinned runtime tuple">
                <dl className="space-y-1 text-sm">
                  {Object.entries(versions).map(([key, value]) => (
                    <Row key={key} label={key}>
                      {value === null ? '—' : String(value)}
                    </Row>
                  ))}
                </dl>
                <p className="text-[11px] text-slate-400">
                  Resolved once at start and never looked up again; publishing a correction later
                  leaves this tuple byte-identical.
                </p>
              </Panel>
            )}

            <Panel title={`Enrolments (${enrollments.length})`}>
              <div className="flex gap-2">
                <input
                  aria-label="Student id"
                  value={studentId}
                  onChange={(event) => setStudentId(event.target.value)}
                  onKeyDown={(event) => event.key === 'Enter' && void enrol()}
                  placeholder="student-007"
                  className={INPUT_CLASS}
                />
                <button
                  type="button"
                  onClick={() => void enrol()}
                  disabled={busy || !studentId.trim()}
                  className={`${BUTTON_PRIMARY} shrink-0`}
                >
                  Enrol
                </button>
              </div>
              <p className="text-[11px] text-slate-400">
                Enrolment is the class-scoped authorization a student needs to be handed a join
                credential; enrolling twice is one enrolment.
              </p>

              <ul className="space-y-1">
                {enrollments.map((enrollment) => (
                  <li
                    key={enrollment.enrollment_id}
                    className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-1.5 text-xs"
                  >
                    <span className="font-medium text-slate-800">{enrollment.student_id}</span>
                    <span className="ml-auto truncate font-mono text-[10px] text-slate-400">
                      {enrollment.created_at}
                    </span>
                  </li>
                ))}
              </ul>
              {enrollments.length === 0 && <EmptyState>No students enrolled.</EmptyState>}
            </Panel>
          </>
        )}
      </div>
    </div>
  )
}
