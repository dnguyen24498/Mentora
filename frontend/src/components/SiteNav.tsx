import { Link, adminPath, classroomPath, learnPath, settingsPath, studioPath } from '../router'
import { readSelectedArtifact, readSelectedClass } from '../institution'

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
 */
export type SiteNavPage = 'library' | 'studio' | 'classroom' | 'learn' | 'admin' | 'settings'

export interface SiteNavProps {
  /** The page being viewed, so it can be marked `aria-current`. */
  current: SiteNavPage
  /** The deck this page is about, if it has one (Studio, Learn). */
  artifactId?: string | null
  /** The class this page is about, if it has one (Classroom). */
  classId?: string | null
}

interface NavEntryProps {
  to: string | null
  label: string
  current: boolean
  /** Shown to explain a disabled entry. */
  hint: string
}

const ITEM_BASE = 'rounded-md px-2 py-1 text-[11px] font-medium transition'

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
  const artifact = artifactId || readSelectedArtifact()
  const klass = classId || readSelectedClass()

  return (
    <nav aria-label="Pages" className="flex flex-wrap items-center gap-1">
      <NavEntry to="/" label="Library" current={current === 'library'} hint="The material library" />
      <NavEntry
        to={artifact ? studioPath(artifact) : null}
        label="Studio"
        current={current === 'studio'}
        hint="Open a deck from the library to reach its Teacher Studio"
      />
      <NavEntry
        to={klass ? classroomPath(klass) : null}
        label="Classroom"
        current={current === 'classroom'}
        hint="No class yet — schedule one to reach its classroom"
      />
      <NavEntry
        to={artifact ? learnPath(artifact) : null}
        label="Learn"
        current={current === 'learn'}
        hint="Open a deck from the library to reach its learning page"
      />
      <span aria-hidden="true" className="mx-0.5 h-4 w-px bg-slate-200" />
      <NavEntry
        to={adminPath()}
        label="Admin"
        current={current === 'admin'}
        hint="Manage courses, classes and publications"
      />
      <NavEntry
        to={settingsPath()}
        label="Settings"
        current={current === 'settings'}
        hint="Preferences and server status"
      />
    </nav>
  )
}
