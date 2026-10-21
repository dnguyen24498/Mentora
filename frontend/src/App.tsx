import { useEffect } from 'react'
import AdminPage from './admin/AdminPage'
import ClassroomHomePage from './classroom/ClassroomHomePage'
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
import { LIBRARY_PATH, LOGIN_PATH, Link, loginPath, useRoute } from './router'

/**
 * The app shell: it routes between the real pages, and it is **behind a sign-in**
 * (V0-023).
 *
 * * `/` — the material library (`pages/UploadPage.tsx`): create a course,
 *   upload a `.pptx`, inspect the extracted Content IR, and open any class;
 * * `/studio/{artifactId}` — the Teacher Studio (`pages/StudioPage.tsx`): the
 *   full-width slide review of one uploaded deck, meant to be opened large;
 * * `/classroom` — the Classroom hub (`classroom/ClassroomHomePage.tsx`): every
 *   class the signed-in person may see; a teacher starts one here and its
 *   pinned slides play automatically, while a student joins a running class to
 *   watch the same slides;
 * * `/classroom/{classId}` — one class (`classroom/ClassroomPage.tsx` for a
 *   teacher, `student/StudentClassPage.tsx` for a student): the authoritative
 *   runtime state of the running session (V0-011);
 * * `/learn/{artifactId}` — a legacy deck rehearsal page
 *   (`presentation/LearnPage.tsx`), kept for direct links but no longer part of
 *   the classroom navigation;
 * * `/admin/{section}` — the Admin area (`admin/AdminPage.tsx`): manage courses,
 *   classes and publications through the existing API;
 * * `/settings/{section}` — Settings (`settings/SettingsPage.tsx`): client
 *   preferences plus read-only server facts;
 * * `/login` — sign in (`auth/LoginPage.tsx`): the **only** public route, a
 *   labelled development credential mock behind a provider-neutral interface,
 *   because no credential mechanism is a decided technology;
 * * `/join/{classId}` — a student enters a class (`student/JoinClassPage.tsx`):
 *   the class, and one button that asks the server for the caller's own join
 *   credential;
 * * `/student` — a student's classes (`student/StudentHomePage.tsx`): only the
 *   classes a teacher assigned them, each joinable once the teacher starts it;
 * * `/student/{classId}` — the student's own fullscreen view of a class
 *   (`student/StudentClassPage.tsx`), built for a phone in a lecture hall.
 *
 * Every page carries the shared navigation (`components/SiteNav.tsx`), so each
 * is reachable from each. Routing is a small dependency-free module
 * (`router.tsx`) rather than a router dependency: a handful of static pages do
 * not justify one, and the project adds no production dependency without an
 * accepted decision.
 *
 * **The guard.** Until V0-023 the app could be read anonymously through the
 * development tenant shortcut; now a session is required on every route, so any
 * other route with no session is redirected to `/login` with the page it wanted
 * remembered (`?next=`), and a successful sign-in returns there. The redirect is
 * `replace`, so the guarded path does not linger in the history. The backend
 * enforces the same rule — this is the honest client-side projection of it, and a
 * stale client can only ever *show* less than it is allowed, never more.
 *
 * The authoring pages are the *teacher's*, and a student who opens one is told so
 * rather than shown a page whose every request would answer `403`. That too is a
 * courtesy, not the control: the server enforces the role on every request
 * (V0-021), so the client can only ever offer fewer things than it is allowed.
 */
export default function App() {
  const route = useRoute()
  const session = useSession()

  // `/login` is the only public route. Everything else — a deep link included —
  // is remembered and returned to after signing in.
  if (route.name !== 'login' && !session) return <RequireSignIn />

  const student = isStudent(session)

  if (route.name === 'login') return <LoginPage />
  if (route.name === 'join') return <JoinClassPage classId={route.classId} />
  // The hub is one page for everyone; the server scopes a student's list to
  // their roster, so the same page can show a teacher every class and a student
  // only the classes they are on.
  if (route.name === 'classroom-home' || route.name === 'student-home') {
    return <ClassroomHomePage />
  }
  // One class URL for both sides: a teacher gets the presentation stage, a
  // student gets the view-only follower (V0-025). The old `/student/{id}` stays
  // as an alias for links already shared.
  if (route.name === 'classroom') {
    return student ? (
      <StudentClassPage classId={route.classId} />
    ) : (
      <ClassroomPage classId={route.classId} />
    )
  }
  if (route.name === 'student') return <StudentClassPage classId={route.classId} />

  // A student may still open Settings (client preferences) — it holds nothing
  // that belongs to a role — but not the authoring surfaces.
  if (student && route.name !== 'settings' && route.name !== 'not-found') {
    return <StudentNotice />
  }
  if (route.name === 'studio') return <StudioPage artifactId={route.artifactId} />
  if (route.name === 'learn') return <LearnPage artifactId={route.artifactId} />
  if (route.name === 'admin') return <AdminPage section={route.section} />
  if (route.name === 'settings') return <SettingsPage section={route.section} />
  if (route.name === 'library') return <UploadPage />

  return <NotFound path={route.name === 'not-found' ? route.path : window.location.pathname} />
}

/** The app's own not-found view: a real page, so a bad deep link is not blank. */
function NotFound({ path }: { path: string }) {
  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <main className="mx-auto max-w-2xl px-4 py-12 sm:px-6 sm:py-16">
        <h1 className="text-xl font-semibold">Page not found</h1>
        <p className="mt-2 text-sm text-slate-500">
          Nothing is served at <code className="rounded bg-slate-200 px-1 font-mono">{path}</code>.
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

/**
 * The sign-in form, shown in place of a protected page when there is no session
 * (V0-023).
 *
 * It renders `LoginPage` **immediately** rather than redirecting and waiting for a
 * re-render: the route hook subscribes to `popstate` in an effect, and effects run
 * child-first, so an event dispatched from this child's effect would arrive before
 * the hook was listening and leave a blank page. The URL is rewritten (a `replace`,
 * so the guarded path does not linger in the history) to the truthful
 * `/login?next=…`, which is also what `LoginPage` reads to return the person to the
 * page they wanted. `/login` itself is never put in `?next`.
 */
function RequireSignIn() {
  useEffect(() => {
    const here = `${window.location.pathname}${window.location.search}`
    if (here.startsWith(LOGIN_PATH)) return
    window.history.replaceState({}, '', loginPath(here))
  }, [])
  return <LoginPage />
}
