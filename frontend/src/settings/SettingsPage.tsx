import { useEffect } from 'react'
import PageHeader from '../components/PageHeader'
import { PAGE_PADDING, TAB_CLASS } from '../components/ui'
import { Link, settingsPath, type SettingsSection } from '../router'
import { useInstitution } from '../institution'
import GeneralSettings from './GeneralSettings'
import RenderingSettings from './RenderingSettings'
import TeachingSettings from './TeachingSettings'
import AccessibilitySettings from './AccessibilitySettings'
import SecuritySettings from './SecuritySettings'

const TABS: { section: SettingsSection; label: string }[] = [
  { section: 'general', label: 'General' },
  { section: 'rendering', label: 'Rendering' },
  { section: 'teaching', label: 'Teaching' },
  { section: 'accessibility', label: 'Accessibility' },
  { section: 'security', label: 'Security' },
]

export interface SettingsPageProps {
  /** Which settings page is open (the `/settings/{section}` route). */
  section: SettingsSection
}

/**
 * The settings area — `/settings/{section}`.
 *
 * Everything here is a **client preference**: there is no settings API. The
 * server's configuration is its environment (the home region) and the per-request
 * render mode, and the read-only parts of these pages show that server state
 * rather than pretending to change it (`GET /renderer`, `GET /health`).
 *
 * Preferences are held in one place (`settings/store.ts`) so a change is visible
 * everywhere at once, and the accessibility page edits the classroom's own
 * persisted preferences rather than keeping a second copy.
 */
export default function SettingsPage({ section }: SettingsPageProps) {
  const [institution, setInstitution] = useInstitution()

  useEffect(() => {
    document.title = 'Settings — Mentora'
  }, [])

  return (
    <div className="min-h-screen bg-academic-canvas text-slate-900 bg-academic-grid">
      <PageHeader
        nav="settings"
        title="Settings"
        institution={institution}
        onInstitutionChange={setInstitution}
      >
        <nav
          aria-label="Settings sections"
          className="flex flex-wrap gap-1.5 border-t border-slate-100 bg-slate-50/50 px-3 py-2 sm:px-4"
        >
          {TABS.map((tab) => {
            const active = tab.section === section
            return (
              <Link
                key={tab.section}
                to={settingsPath(tab.section)}
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
        {section === 'general' && <GeneralSettings />}
        {section === 'rendering' && <RenderingSettings institutionId={institution} />}
        {section === 'teaching' && <TeachingSettings />}
        {section === 'accessibility' && <AccessibilitySettings />}
        {section === 'security' && <SecuritySettings />}
      </main>
    </div>
  )
}
