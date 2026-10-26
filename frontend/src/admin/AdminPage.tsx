import { useEffect } from 'react'
import PageHeader from '../components/PageHeader'
import { PAGE_PADDING, TAB_CLASS } from '../components/ui'
import { Link, adminPath, type AdminSection } from '../router'
import { useInstitution } from '../institution'
import { hasScope, useSession, type Scope } from '../auth/session'
import AdminOverview from './AdminOverview'
import AccountsAdmin from './AccountsAdmin'
import CoursesAdmin from './CoursesAdmin'
import ClassesAdmin from './ClassesAdmin'
import PublicationsAdmin from './PublicationsAdmin'

/**
 * The management sections, each behind the capability it actually needs.
 *
 * The list is *filtered by capability*, never by a role name, so the nav always
 * matches what the server would allow: an institution administrator (V0-022) holds
 * `account:write` and sees the directory; a teacher holds the authoring capabilities
 * and does not. A section that is not offered is not rendered at all — the UI never
 * displays a page whose every request would answer `403`.
 */
const TABS: { section: AdminSection; label: string; scope: Scope }[] = [
  { section: 'overview', label: 'Overview', scope: 'content:read' },
  { section: 'accounts', label: 'Accounts', scope: 'account:write' },
  { section: 'courses', label: 'Courses & materials', scope: 'content:write' },
  { section: 'classes', label: 'Classes', scope: 'class:write' },
  { section: 'publications', label: 'Publications', scope: 'publication:write' },
]

export interface AdminPageProps {
  /** Which management area is open (the `/admin/{section}` route). */
  section: AdminSection
}

/**
 * The admin area — `/admin/{section}`.
 *
 * It manages the V0 entities through the **existing** API only. Where the domain is
 * append-only — content is immutable, a draft is append-only and a publication is
 * never deleted (`DEC-CONTENT-005`) — the write verbs here are the domain's own
 * transitions (create, schedule, start, enrol, publish) rather than an edit of an old
 * one. Accounts (V0-022) are the exception that proves the rule: an identity *is*
 * mutable (a name, a role, an enabled state), so the directory has a real update and
 * a real removal, and its removal is refused while a class references the account.
 */
export default function AdminPage({ section }: AdminPageProps) {
  const [institution, setInstitution] = useInstitution()
  const session = useSession()

  useEffect(() => {
    document.title = 'Admin — Mentora'
  }, [])

  const available = TABS.filter((tab) => hasScope(session, tab.scope))
  const current = available.find((tab) => tab.section === section)

  return (
    <div className="min-h-screen bg-academic-canvas text-slate-900 bg-academic-grid">
      <PageHeader nav="admin" title="Admin" institution={institution} onInstitutionChange={setInstitution}>
        <nav
          aria-label="Admin sections"
          className="flex flex-wrap gap-1.5 border-t border-slate-100 bg-slate-50/50 px-3 py-2 sm:px-4"
        >
          {available.map((tab) => {
            const active = tab.section === section
            return (
              <Link
                key={tab.section}
                to={adminPath(tab.section)}
                aria-current={active ? 'page' : undefined}
                className={`${TAB_CLASS} ${
                  active
                    ? 'bg-gradient-to-r from-indigo-600 to-indigo-700 text-white shadow-2xs font-semibold'
                    : 'border border-slate-200/90 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900 shadow-2xs'
                }`}
              >
                {tab.label}
              </Link>
            )
          })}
        </nav>
      </PageHeader>

      <main className={`${PAGE_PADDING} mx-auto max-w-7xl`}>
        {!current ? (
          <UnavailableSection available={available} />
        ) : (
          <>
            {section === 'overview' && <AdminOverview institutionId={institution} />}
            {section === 'accounts' && <AccountsAdmin institutionId={institution} />}
            {section === 'courses' && <CoursesAdmin institutionId={institution} />}
            {section === 'classes' && <ClassesAdmin institutionId={institution} />}
            {section === 'publications' && <PublicationsAdmin institutionId={institution} />}
          </>
        )}
      </main>
    </div>
  )
}

/**
 * A section this principal's capabilities do not reach.
 *
 * Reached only through a URL the nav does not offer, so it says which sections the
 * signed-in role *does* have rather than 403ing behind a page that looked loadable.
 */
function UnavailableSection({ available }: { available: { section: AdminSection; label: string }[] }) {
  return (
    <section className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
      <h2 className="text-base font-semibold">Not available for this account</h2>
      <p className="mt-1">
        The signed-in role does not hold the capability this section requires, so it is not
        offered and the server would refuse it.
      </p>
      {available.length > 0 && (
        <p className="mt-2 flex flex-wrap gap-2">
          {available.map((tab) => (
            <Link
              key={tab.section}
              to={adminPath(tab.section)}
              className="rounded border border-amber-400 bg-white px-2 py-1 font-medium text-amber-900"
            >
              {tab.label}
            </Link>
          ))}
        </p>
      )}
    </section>
  )
}
