import { useEffect } from 'react'
import PageHeader from '../components/PageHeader'
import { PAGE_PADDING, TAB_CLASS } from '../components/ui'
import { Link, adminPath, type AdminSection } from '../router'
import { useInstitution } from '../institution'
import AdminOverview from './AdminOverview'
import CoursesAdmin from './CoursesAdmin'
import ClassesAdmin from './ClassesAdmin'
import PublicationsAdmin from './PublicationsAdmin'

const TABS: { section: AdminSection; label: string }[] = [
  { section: 'overview', label: 'Overview' },
  { section: 'courses', label: 'Courses & materials' },
  { section: 'classes', label: 'Classes' },
  { section: 'publications', label: 'Publications' },
]

export interface AdminPageProps {
  /** Which management area is open (the `/admin/{section}` route). */
  section: AdminSection
}

/**
 * The admin area — `/admin/{section}`.
 *
 * It manages the V0 entities through the **existing** API only. There is no
 * generic update or delete endpoint, and that is a property of the domain, not a
 * gap: content is immutable, a draft is append-only and a publication is never
 * deleted (`DEC-CONTENT-005`), so the write verbs here are the domain's own
 * transitions — create, schedule, start, enrol, publish — alongside reads.
 * A correction is a new version, not an edit of an old one.
 */
export default function AdminPage({ section }: AdminPageProps) {
  const [institution, setInstitution] = useInstitution()

  useEffect(() => {
    document.title = 'Admin — Mentora'
  }, [])

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <PageHeader nav="admin" title="Admin" institution={institution} onInstitutionChange={setInstitution}>
        <nav
          aria-label="Admin sections"
          className="flex flex-wrap gap-1 border-t border-slate-100 px-3 py-2 sm:px-4"
        >
          {TABS.map((tab) => {
            const active = tab.section === section
            return (
              <Link
                key={tab.section}
                to={adminPath(tab.section)}
                aria-current={active ? 'page' : undefined}
                className={`${TAB_CLASS} ${
                  active
                    ? 'bg-indigo-600 text-white'
                    : 'border border-slate-300 text-slate-700 hover:bg-slate-50'
                }`}
              >
                {tab.label}
              </Link>
            )
          })}
        </nav>
      </PageHeader>

      <main className={PAGE_PADDING}>
        {section === 'overview' && <AdminOverview institutionId={institution} />}
        {section === 'courses' && <CoursesAdmin institutionId={institution} />}
        {section === 'classes' && <ClassesAdmin institutionId={institution} />}
        {section === 'publications' && <PublicationsAdmin institutionId={institution} />}
      </main>
    </div>
  )
}
