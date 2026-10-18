import AdminPage from './admin/AdminPage'
import ClassroomPage from './classroom/ClassroomPage'
import LearnPage from './presentation/LearnPage'
import SettingsPage from './settings/SettingsPage'
import StudioPage from './pages/StudioPage'
import UploadPage from './pages/UploadPage'
import LoginPage from './auth/LoginPage'
import JoinClassPage from './student/JoinClassPage'
import StudentClassPage from './student/StudentClassPage'
import StudentNotice from './auth/StudentNotice'
import { isStudent, useSession } from './auth/session'
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
 *   preferences plus read-only server facts;
 * * `/login` — sign in (`auth/LoginPage.tsx`, V0-021): a labelled development
 *   credential mock behind a provider-neutral interface, because no credential
 *   mechanism is a decided technology;
 * * `/join/{classId}` — a student enters a class (`student/JoinClassPage.tsx`):
 *   the class, and one button that asks the server for the caller's own join
 *   credential;
 * * `/student/{classId}` — the student's own fullscreen view of a class
 *   (`student/StudentClassPage.tsx`), built for a phone in a lecture hall.
 *
 * Every page carries the shared navigation (`components/SiteNav.tsx`), so each
 * is reachable from each. Routing is a small dependency-free module
 * (`router.tsx`) rather than a router dependency: a handful of static pages do
 * not justify one, and the project adds no production dependency without an
 * accepted decision.
 *
 * The authoring pages are the *teacher's*, and a student who opens one is told so
 * rather than shown a page whose every request would answer `403`. That is a
 * courtesy, not the control: the server enforces the role on every request
 * (V0-021), so the client can only ever offer fewer things than it is allowed.
 */
export default function App() {
  const route = useRoute()
  const session = useSession()
  const student = isStudent(session)

  if (route.name === 'login') return <LoginPage />
  if (route.name === 'join') return <JoinClassPage classId={route.classId} />
  if (route.name === 'student') return <StudentClassPage classId={route.classId} />

  // A student may still open Settings (client preferences) — it holds nothing
  // that belongs to a role — but not the authoring surfaces.
  if (student && route.name !== 'settings' && route.name !== 'not-found') {
    return <StudentNotice />
  }
  if (route.name === 'studio') return <StudioPage artifactId={route.artifactId} />
  if (route.name === 'classroom') return <ClassroomPage classId={route.classId} />
  if (route.name === 'learn') return <LearnPage artifactId={route.artifactId} />
  if (route.name === 'admin') return <AdminPage section={route.section} />
  if (route.name === 'settings') return <SettingsPage section={route.section} />
  if (route.name === 'library') return <UploadPage />

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <main className="mx-auto max-w-2xl px-4 py-12 sm:px-6 sm:py-16">
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
