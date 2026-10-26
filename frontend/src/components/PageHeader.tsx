import type { ReactNode } from 'react'
import SiteNav, { type SiteNavPage } from './SiteNav'
import { INPUT_CHROME_CLASS } from './ui'

export interface PageHeaderProps {
  /** The page being viewed, so the shared nav can mark its entry. */
  nav: SiteNavPage
  /** The page's name. It is the page's single `h1`. */
  title: string
  /** A short qualifier beside the title: a filename, a class. */
  subtitle?: ReactNode
  /** A mono identifier, shown where there is room for it. */
  meta?: ReactNode
  /** The deck this page is about, if it has one (Studio, Learn). */
  artifactId?: string | null
  /** The class this page is about, if it has one (Classroom). */
  classId?: string | null
  /** The tenant, owned by the page (`useInstitution`) — never a second copy. */
  institution: string
  onInstitutionChange: (value: string) => void
  /**
   * Whether the tenant may be typed into. A signed-in page sets this false: the
   * tenant comes from the session, so a field that silently ignored typing would
   * be a lie. It is still shown, because "which institution am I in" is a fact a
   * user needs.
   */
  institutionEditable?: boolean
  /** The page's own header action(s), beside the tenant field. */
  actions?: ReactNode
  /** A second row: a page's own section tabs (Admin, Settings). */
  children?: ReactNode
}

/**
 * The app bar the full pages share.
 *
 * The five id-scoped and sectioned pages (Studio, Classroom, Learn, Admin,
 * Settings) each grew the same bar — the shared nav, the page's name, the tenant
 * field and sometimes one action — and each one solved a narrow screen slightly
 * differently. It is one component now, so "how this app looks on a phone" is
 * decided in one place.
 *
 * The layout is the *same* bar on both screen sizes, with a phone-first stack:
 * a phone gets the nav on its own, then the title and its qualifier, then the
 * tenant field; from `lg` up the pieces return to the single dense row the app
 * was designed with. Nothing is hidden on a phone except the raw artifact id,
 * which is a debugging aid rather than something a reader acts on.
 *
 * The tenant field is a **prop**, not state inside the header: the page owns the
 * one `useInstitution` hook, so a change in the header flows to the page (and to
 * the data it reloads) instead of into a private copy.
 */
export default function PageHeader({
  nav,
  title,
  subtitle,
  meta,
  artifactId,
  classId,
  institution,
  onInstitutionChange,
  institutionEditable = true,
  actions,
  children,
}: PageHeaderProps) {
  return (
    <header className="sticky top-0 z-20 border-b border-slate-200/90 bg-white/95 shadow-[0_1px_3px_rgba(0,0,0,0.03)] backdrop-blur-md">
      <div className="flex flex-col gap-y-2.5 px-3 py-2 sm:px-5 lg:flex-row lg:flex-wrap lg:items-center lg:gap-x-3.5 lg:py-2.5">
        <div className="flex items-center gap-2">
          {/* University AI Learning Platform Crest */}
          <div
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-600 via-indigo-700 to-blue-700 text-white shadow-xs"
            aria-hidden="true"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M12 14l9-5-9-5-9 5 9 5z M12 14l6.16-3.422a12.083 12.083 0 01.665 6.479A11.952 11.952 0 0012 20.055a11.952 11.952 0 00-6.824-2.998 12.078 12.078 0 01.665-6.479L12 14z"
              />
            </svg>
          </div>
          <div className="hidden sm:block">
            <span className="block text-xs font-black tracking-widest text-slate-900 uppercase">
              Mentora
            </span>
            <span className="block text-[9px] font-semibold tracking-wider text-indigo-600 uppercase">
              University LMS
            </span>
          </div>
        </div>

        <SiteNav current={nav} artifactId={artifactId} classId={classId} />

        <div className="flex items-center gap-2 border-l-0 lg:border-l lg:border-slate-200 lg:pl-3">
          <h1 className="text-base font-bold text-slate-900 tracking-tight">{title}</h1>
          {subtitle && (
            <span className="min-w-0 truncate rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
              {subtitle}
            </span>
          )}
          {meta && (
            <span className="hidden min-w-0 truncate font-mono text-[11px] text-slate-400 xl:inline">
              {meta}
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 lg:ml-auto">
          <div className="flex items-center gap-1.5 rounded-lg border border-slate-200/85 bg-slate-50/80 px-2 py-1 shadow-2xs">
            <svg
              className="h-3.5 w-3.5 text-slate-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"
              />
            </svg>
            <label htmlFor="institution" className="text-xs font-semibold text-slate-600">
              Institution
            </label>
            <input
              id="institution"
              value={institution}
              readOnly={!institutionEditable}
              onChange={(event) => onInstitutionChange(event.target.value)}
              title={
                institutionEditable
                  ? undefined
                  : 'The institution comes from your session while you are signed in.'
              }
              className={`${INPUT_CHROME_CLASS}${institutionEditable ? '' : ' bg-slate-100/90 text-slate-500'}`}
            />
          </div>
          {actions}
        </div>
      </div>
      {children}
    </header>
  )
}
