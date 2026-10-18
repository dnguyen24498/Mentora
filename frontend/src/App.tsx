import AdminPage from './admin/AdminPage'
import ClassroomPage from './classroom/ClassroomPage'
import LearnPage from './presentation/LearnPage'
import SettingsPage from './settings/SettingsPage'
import StudioPage from './pages/StudioPage'
import UploadPage from './pages/UploadPage'
import { LIBRARY_PATH, Link, useRoute } from './router'

/**
 * The app shell: it routes between the real pages.
 *
 * * `/` — the material library (`pages/UploadPage.tsx`): create a course,
 *   upload a `.pptx`, inspect the extracted Content IR, and open any class;
 * * `/studio/{artifactId}` — the Teacher Studio (`pages/StudioPage.tsx`): the
 *   full-width slide review of one uploaded deck, meant to be opened large;
 * * `/classroom/{classId}` — the Classroom (`classroom/ClassroomPage.tsx`): the
 *   authoritative runtime state of a running session (V0-011);
 * * `/learn/{artifactId}` — the Learning page (`presentation/LearnPage.tsx`):
 *   the slide plus the teaching canvas the teacher draws on, and the automatic
 *   text-only narration;
 * * `/admin/{section}` — the Admin area (`admin/AdminPage.tsx`): manage courses,
 *   classes and publications through the existing API;
 * * `/settings/{section}` — Settings (`settings/SettingsPage.tsx`): client
 *   preferences plus read-only server facts.
 *
 * Every page carries the shared navigation (`components/SiteNav.tsx`), so each
 * is reachable from each. Routing is a small dependency-free module
 * (`router.tsx`) rather than a router dependency: a handful of static pages do
 * not justify one, and the project adds no production dependency without an
 * accepted decision.
 */
export default function App() {
  const route = useRoute()

  if (route.name === 'studio') return <StudioPage artifactId={route.artifactId} />
  if (route.name === 'classroom') return <ClassroomPage classId={route.classId} />
  if (route.name === 'learn') return <LearnPage artifactId={route.artifactId} />
  if (route.name === 'admin') return <AdminPage section={route.section} />
  if (route.name === 'settings') return <SettingsPage section={route.section} />
  if (route.name === 'library') return <UploadPage />

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <main className="mx-auto max-w-2xl px-6 py-16">
        <h1 className="text-xl font-semibold">Page not found</h1>
        <p className="mt-2 text-sm text-slate-500">
          Nothing is served at <code className="rounded bg-slate-200 px-1 font-mono">{route.path}</code>.
        </p>
        <Link
          to={LIBRARY_PATH}
          className="mt-4 inline-block rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white"
        >
          Back to the material library
        </Link>
      </main>
    </div>
  )
}
