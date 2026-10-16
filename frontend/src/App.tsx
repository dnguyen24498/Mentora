import StudioPage from './pages/StudioPage'
import UploadPage from './pages/UploadPage'
import { LIBRARY_PATH, Link, useRoute } from './router'

/**
 * The app shell: it routes between the two real pages.
 *
 * * `/` — the material library (`pages/UploadPage.tsx`): create a course,
 *   upload a `.pptx`, inspect the extracted Content IR;
 * * `/studio/{artifactId}` — the Teacher Studio (`pages/StudioPage.tsx`): the
 *   full-width slide review of one uploaded deck, meant to be opened large.
 *
 * Routing is a ~60-line dependency-free module (`router.tsx`) rather than a
 * router dependency: two static pages do not justify one, and the project adds
 * no production dependency without an accepted decision.
 */
export default function App() {
  const route = useRoute()

  if (route.name === 'studio') return <StudioPage artifactId={route.artifactId} />
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
