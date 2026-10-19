import { Link, adminPath, classroomPath, joinPath, learnPath, settingsPath, studioPath, loginPath } from '../router'
import { readSelectedArtifact, readSelectedClass } from '../institution'
import { TOUCH_TARGET } from './ui'
import { clearSession, describePrincipal, hasScope, isStudent, useSession } from '../auth/session'
import { resetDevelopmentMode, useMode } from '../auth/mode'
import { logout } from '../api/client'

/**
 * The app's page-to-page navigation (V0 frontend).
 *
 * Every page embeds it in its own header, so Library, Teacher Studio, Classroom
 * and Learning are reachable from each other without going back to the library
 * first. It is deliberately dependency-free and small, like the router.
 *
 * Studio, Classroom and Learn are scoped by an id (a deck or a class). The id is
 * only known once the teacher has opened something — the current page passes
 * the one it holds, otherwise the last one opened is remembered
 * (`institution.ts`). With no id yet, the link is not a link but a disabled
 * label that says why: a nav entry that goes nowhere is worse than none.
 *
 * Two things were added for identities (V0-021):
 *
 * * a student sees the entries a student can actually use — the class they were
 *   invited to, and their own view of it — because the authoring entries would
 *   only answer `403`. Roles are still enforced server-side; this is the honest
 *   version of the same fact;
 * * the right-hand end says who you are, or that you are in **development mode**
 *   (the `X-Institution-Id` shortcut, which is not a sign-in).
 *
 * V0-022 widens that first point from two roles to three: the entries are chosen by
 * **capability**, not by role name, so an institution administrator (who authors
 * nothing) sees the library, the Admin area and Settings — while a teacher sees the
 * authoring surfaces and a student sees their class. The rule is the same one the
 * server applies; the nav is simply its honest client-side projection.
 *
 * It is built to be a phone's primary navigation as well as a laptop's: each
 * entry is a chip with the 44px minimum tap area below `lg`
 * (`ui.tsx::TOUCH_TARGET`) and the original compact chip from `lg` up, and the
 * row wraps rather than overflowing — a handful of destinations is short enough
 * to show them all rather than hide some behind a menu.
 */
export type SiteNavPage =
  | 'library'
  | 'studio'
  | 'classroom'
  | 'learn'
  | 'admin'
  | 'settings'
  /** The student's join page (`/join/{classId}`). */
  | 'join'
  /** The student's own view of a class (`/student/{classId}`). */
  | 'student'
  /** The sign-in page (`/login`). */
  | 'login'

export interface SiteNavProps {
  /** The page being viewed, so it can be marked `aria-current`. */
  current: SiteNavPage
  /** The deck this page is about, if it has one (Studio, Learn). */
  artifactId?: string | null
  /** The class this page is about, if it has one (Classroom, Join, Student). */
  classId?: string | null
}

interface NavEntryProps {
  to: string | null
  label: string
  current: boolean
  /** Shown to explain a disabled entry. */
  hint: string
}

const ITEM_BASE = `inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-2 text-xs font-medium transition lg:px-2 lg:py-1 lg:text-[11px] ${TOUCH_TARGET}`

function NavEntry({ to, label, current, hint }: NavEntryProps) {
  if (!to) {
    return (
      <span
        aria-disabled="true"
        title={hint}
        className={`${ITEM_BASE} cursor-not-allowed border border-slate-200 text-slate-400`}
      >
        {label}
      </span>
    )
  }
  return (
    <Link
      to={to}
      aria-current={current ? 'page' : undefined}
      className={`${ITEM_BASE} border ${
        current
          ? 'border-indigo-600 bg-indigo-600 text-white'
          : 'border-slate-300 text-slate-700 hover:bg-slate-50'
      }`}
    >
      {label}
    </Link>
  )
}

export default function SiteNav({ current, artifactId, classId }: SiteNavProps) {
  const session = useSession()
  const mode = useMode()
  const artifact = artifactId || readSelectedArtifact()
  const klass = classId || readSelectedClass()
  const student = isStudent(session)

  return (
    <nav aria-label="Pages" className="flex flex-wrap items-center gap-1.5 sm:gap-1">
      {student ? (
        <>
          <NavEntry
            to={klass ? joinPath(klass) : null}
            label="My class"
            current={current === 'join'}
            hint="Open the join link your teacher gave you"
          />
          <NavEntry
            to={klass ? `/student/${encodeURIComponent(klass)}` : null}
            label="Attend"
            current={current === 'student'}
            hint="Join a class first to reach your view of it"
          />
        </>
      ) : (
        <>
          {hasScope(session, 'content:read') && (
            <NavEntry
              to="/"
              label="Library"
              current={current === 'library'}
              hint="The material library"
            />
          )}
          {hasScope(session, 'content:write') && (
            <NavEntry
              to={artifact ? studioPath(artifact) : null}
              label="Studio"
              current={current === 'studio'}
              hint="Open a deck from the library to reach its Teacher Studio"
            />
          )}
          {hasScope(session, 'class:write') && (
            <NavEntry
              to={klass ? classroomPath(klass) : null}
              label="Classroom"
              current={current === 'classroom'}
              hint="No class yet — schedule one to reach its classroom"
            />
          )}
          {hasScope(session, 'scene:read') && (
            <NavEntry
              to={artifact ? learnPath(artifact) : null}
              label="Learn"
              current={current === 'learn'}
              hint="Open a deck from the library to reach its learning page"
            />
          )}
          <span aria-hidden="true" className="mx-0.5 h-4 w-px bg-slate-200" />
          <NavEntry
            to={adminPath()}
            label="Admin"
            current={current === 'admin'}
            hint="Manage accounts, courses, classes and publications"
          />
          <NavEntry
            to={settingsPath()}
            label="Settings"
            current={current === 'settings'}
            hint="Preferences and server status"
          />
        </>
      )}

      <span aria-hidden="true" className="mx-0.5 h-4 w-px bg-slate-200" />
      {mode.signedIn ? (
        <span className="flex flex-wrap items-center gap-1.5">
          <span
            data-testid="session-principal"
            title={session?.principal.institution_id}
            className={`${ITEM_BASE} border border-emerald-200 bg-emerald-50 text-emerald-800`}
          >
            {describePrincipal(session)}
          </span>
          <button
            type="button"
            onClick={() => {
              void logout().catch(() => undefined)
              clearSession()
              resetDevelopmentMode()
            }}
            className={`${ITEM_BASE} border border-slate-300 text-slate-700 hover:bg-slate-50`}
          >
            Sign out
          </button>
        </span>
      ) : (
        <span className="flex flex-wrap items-center gap-1.5">
          {mode.development && (
            <span
              data-testid="session-development"
              title="The X-Institution-Id development shortcut: this browser is authorized as a teacher with no account behind it"
              className={`${ITEM_BASE} cursor-default border border-amber-200 bg-amber-50 text-amber-800`}
            >
              Development mode
            </span>
          )}
          <NavEntry
            to={current === 'login' ? null : loginPath()}
            label="Sign in"
            current={current === 'login'}
            hint="You are on the sign-in page"
          />
        </span>
      )}
    </nav>
  )
}
