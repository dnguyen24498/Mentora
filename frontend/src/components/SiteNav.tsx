import {
  Link,
  LIBRARY_PATH,
  CLASSROOM_PATH,
  adminPath,
  settingsPath,
  studioPath,
  loginPath,
} from '../router'
import { readSelectedArtifact } from '../institution'
import { TOUCH_TARGET } from './ui'
import {
  clearSession,
  describePrincipal,
  hasScope,
  isSignedIn,
  isStudent,
  useSession,
} from '../auth/session'
import { logout } from '../api/client'

/**
 * The app's page-to-page navigation (V0 frontend).
 *
 * Every page embeds it in its own header, so Library, Teacher Studio and the
 * Classroom hub are reachable from each other without going back to the library
 * first. It is deliberately dependency-free and small, like the router.
 *
 * Studio is scoped by a deck id. The id is only known once the teacher has
 * opened something — the current page passes the one it holds, otherwise the
 * last one opened is remembered (`institution.ts`). With no id yet, the entry
 * still goes somewhere real: the Library, where the deck is chosen. A disabled
 * label looked like a broken page; the chooser is the honest destination and
 * needs no id. The Classroom entry is the hub at `/classroom`; the person picks
 * the class there, so the nav never has to guess the last one.
 *
 * Two things were added for identities (V0-021):
 *
 * * a student sees the entries a student can actually use — the class they were
 *   invited to, and their own view of it — because the authoring entries would
 *   only answer `403`. Roles are still enforced server-side; this is the honest
 *   version of the same fact;
 * * the right-hand end says who you are, and offers a sign-out.
 *
 * V0-022 widens that first point from two roles to three: the entries are chosen by
 * **capability**, not by role name, so an institution administrator (who authors
 * nothing) sees the library, the Admin area and Settings — while a teacher sees the
 * authoring surfaces and a student sees their class. The rule is the same one the
 * server applies; the nav is simply its honest client-side projection.
 *
 * V0-023 removes the "development mode" chip: the tenant shortcut is off by default
 * and every page requires a sign-in, so a session is the only state this nav knows.
 * The nav is only ever rendered *inside* a signed-in page (the route guard sees to
 * that), so the right-hand end always names the signed-in account.
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
  /** The student's list of classes (`/student`). */
  | 'student-home'
  /** The student's own view of a class (`/student/{classId}`). */
  | 'student'
  /** The sign-in page (`/login`). */
  | 'login'

export interface SiteNavProps {
  /** The page being viewed, so it can be marked `aria-current`. */
  current: SiteNavPage
  /** The deck this page is about, if it has one (Studio). */
  artifactId?: string | null
  /** The class this page is about, if it has one (Join, Student). */
  classId?: string | null
}

interface NavEntryProps {
  to: string | null
  label: string
  current: boolean
  /** Shown to explain a disabled entry. */
  hint: string
}

const ITEM_BASE = `inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-2 text-xs font-medium transition-all duration-150 lg:px-2.5 lg:py-1 lg:text-[11px] ${TOUCH_TARGET}`

function NavEntry({ to, label, current, hint }: NavEntryProps) {
  if (!to) {
    return (
      <span
        aria-disabled="true"
        title={hint}
        className={`${ITEM_BASE} cursor-not-allowed border border-slate-200/80 bg-slate-50 text-slate-400`}
      >
        {label}
      </span>
    )
  }
  return (
    <Link
      to={to}
      title={hint}
      aria-current={current ? 'page' : undefined}
      className={`${ITEM_BASE} border ${
        current
          ? 'border-indigo-600 bg-gradient-to-r from-indigo-600 to-indigo-700 text-white shadow-2xs font-semibold'
          : 'border-slate-200/90 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900 shadow-2xs'
      }`}
    >
      {label}
    </Link>
  )
}

export default function SiteNav({ current, artifactId }: SiteNavProps) {
  const session = useSession()
  const signedIn = isSignedIn(session)
  const artifact = artifactId || readSelectedArtifact()
  const student = isStudent(session)
  const inClassroom =
    current === 'classroom' || current === 'student-home' || current === 'student'

  return (
    <nav aria-label="Pages" className="flex flex-wrap items-center gap-1.5 sm:gap-1">
      {student ? (
        <NavEntry
          to={CLASSROOM_PATH}
          label="Classroom"
          current={inClassroom}
          hint="Your classes and the one running now"
        />
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
              to={artifact ? studioPath(artifact) : LIBRARY_PATH}
              label="Studio"
              current={current === 'studio'}
              hint={
                artifact
                  ? 'Review this deck in the Teacher Studio'
                  : 'Choose a deck in the Library to open its Teacher Studio'
              }
            />
          )}
          {hasScope(session, 'class:read') && (
            <NavEntry
              to={CLASSROOM_PATH}
              label="Classroom"
              current={inClassroom}
              hint="All classes, and the one to start or open"
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
      {signedIn ? (
        <span className="flex flex-wrap items-center gap-1.5">
          <span
            data-testid="session-principal"
            title={session?.principal.institution_id}
            className={`${ITEM_BASE} border border-emerald-300/80 bg-emerald-50 text-emerald-800 shadow-2xs font-medium`}
          >
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" aria-hidden="true" />
            {describePrincipal(session)}
          </span>
          <button
            type="button"
            onClick={() => {
              void logout().catch(() => undefined)
              clearSession()
            }}
            className={`${ITEM_BASE} border border-slate-200/90 bg-white text-slate-700 hover:bg-rose-50 hover:border-rose-200 hover:text-rose-700 shadow-2xs`}
          >
            Sign out
          </button>
        </span>
      ) : (
        <span className="flex flex-wrap items-center gap-1.5">
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
