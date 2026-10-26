import { useEffect, useState } from 'react'
import { Link, adminPath, classroomPath } from '../router'
import {
  describeApiError,
  listClasses,
  listCourses,
  type ClassSummary,
  type Course,
} from '../api/client'
import { Badge, Banner, BUTTON_SMALL, EmptyState, Panel } from '../components/ui'

/**
 * The admin landing view: what the tenant holds, and where to manage it.
 *
 * It is a read: three counts and the entity lists, each linking to the section
 * that can act on it. Nothing is created here — a dashboard that also mutates is
 * harder to reason about than one that points at the page that does.
 */
export default function AdminOverview({ institutionId }: { institutionId: string }) {
  const [courses, setCourses] = useState<Course[]>([])
  const [classes, setClasses] = useState<ClassSummary[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    Promise.all([listCourses(institutionId), listClasses(institutionId)])
      .then(([loadedCourses, loadedClasses]) => {
        if (cancelled) return
        setCourses(loadedCourses)
        setClasses(loadedClasses)
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(describeApiError(cause))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [institutionId])

  const activeClasses = classes.filter((item) => item.state === 'ACTIVE').length

  return (
    <div className="mx-auto grid grid-cols-1 max-w-7xl gap-6 lg:grid-cols-2">
      <Panel
        title="This institution"
        actions={
          <button
            type="button"
            onClick={() => void Promise.all([listCourses(institutionId), listClasses(institutionId)]).then(
              ([loadedCourses, loadedClasses]) => {
                setCourses(loadedCourses)
                setClasses(loadedClasses)
                setError(null)
              },
              (cause: unknown) => setError(describeApiError(cause)),
            )}
            className={BUTTON_SMALL}
          >
            Refresh
          </button>
        }
      >
        {error && <Banner tone="bad">{error}</Banner>}
        {loading && <EmptyState>Loading…</EmptyState>}

        <dl className="grid grid-cols-3 gap-2.5 text-center sm:gap-4">
          <div className="rounded-xl border border-slate-200/80 bg-slate-50/70 p-3 sm:p-4 shadow-xs">
            <dt className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 sm:text-[11px]">Courses</dt>
            <dd data-testid="admin-course-count" className="mt-1 text-2xl font-serif font-bold text-slate-900 sm:text-3xl">
              {courses.length}
            </dd>
          </div>
          <div className="rounded-xl border border-slate-200/80 bg-slate-50/70 p-3 sm:p-4 shadow-xs">
            <dt className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 sm:text-[11px]">Classes</dt>
            <dd data-testid="admin-class-count" className="mt-1 text-2xl font-serif font-bold text-slate-900 sm:text-3xl">
              {classes.length}
            </dd>
          </div>
          <div className="rounded-xl border border-slate-200/80 bg-slate-50/70 p-3 sm:p-4 shadow-xs">
            <dt className="text-[10px] font-semibold uppercase tracking-wider text-emerald-600 sm:text-[11px]">Running</dt>
            <dd className="mt-1 text-2xl font-serif font-bold text-emerald-600 sm:text-3xl">{activeClasses}</dd>
          </div>
        </dl>

        <div className="flex flex-wrap gap-3 border-t border-slate-100 pt-3.5 text-xs">
          <Link to={adminPath('courses')} className="font-medium text-indigo-600 hover:text-indigo-800 underline">
            Manage courses &amp; materials
          </Link>
          <Link to={adminPath('classes')} className="font-medium text-indigo-600 hover:text-indigo-800 underline">
            Schedule a class
          </Link>
          <Link to={adminPath('publications')} className="font-medium text-indigo-600 hover:text-indigo-800 underline">
            Publish and verify
          </Link>
        </div>

        <p className="text-[11px] text-slate-400">
          Institutions are isolated by the <span className="font-mono">X-Institution-Id</span> header;
          changing the institution above switches every list on this page.
        </p>
      </Panel>

      <Panel title="Courses">
        {courses.length === 0 && !loading && (
          <EmptyState>
            No courses yet. <Link to={adminPath('courses')} className="text-indigo-600 underline">Create one</Link> to
            upload material into.
          </EmptyState>
        )}
        <ul className="space-y-2">
          {courses.map((course) => (
            <li key={course.course_id}>
              <Link
                to={adminPath('courses')}
                className="flex items-center gap-2 rounded-xl border border-slate-200/80 bg-white/80 p-3 hover:border-indigo-300 hover:bg-white hover:shadow-xs transition-all"
              >
                <span className="truncate text-sm font-medium text-slate-900">{course.title}</span>
                <span className="ml-auto truncate font-mono text-[10px] text-slate-400">
                  {course.course_id}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </Panel>

      <Panel title="Classes" className="lg:col-span-2">
        {classes.length === 0 && !loading && (
          <EmptyState>No classes yet.</EmptyState>
        )}
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {classes.map((item) => (
            <li key={item.class_id}>
              <Link
                to={classroomPath(item.class_id)}
                className="flex flex-col gap-1.5 rounded-xl border border-slate-200/80 bg-white/80 p-3.5 hover:border-indigo-300 hover:bg-white hover:shadow-xs transition-all"
              >
                <span className="flex items-center gap-2">
                  <span className="truncate text-sm font-medium text-slate-900">{item.title}</span>
                  <Badge tone={item.state === 'ACTIVE' ? 'good' : 'neutral'}>{item.state}</Badge>
                </span>
                <span className="truncate font-mono text-[10px] text-slate-400">{item.class_id}</span>
              </Link>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  )
}
