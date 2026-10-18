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
    <header className="border-b border-slate-200 bg-white">
      <div className="flex flex-col gap-y-2 px-3 py-2 sm:px-4 lg:flex-row lg:flex-wrap lg:items-center lg:gap-x-3 lg:py-3">
        <SiteNav current={nav} artifactId={artifactId} classId={classId} />

        <h1 className="text-base font-semibold text-slate-800">{title}</h1>
        {subtitle && <span className="min-w-0 truncate text-sm text-slate-500">{subtitle}</span>}
        {meta && (
          <span className="hidden min-w-0 truncate font-mono text-[11px] text-slate-400 xl:inline">
            {meta}
          </span>
        )}

        <div className="flex flex-wrap items-center gap-2 lg:ml-auto">
          <label htmlFor="institution" className="text-xs text-slate-500">
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
            className={`${INPUT_CHROME_CLASS}${institutionEditable ? '' : ' bg-slate-100 text-slate-500'}`}
          />
          {actions}
        </div>
      </div>
      {children}
    </header>
  )
}
