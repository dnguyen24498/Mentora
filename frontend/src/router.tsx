import {
  useCallback,
  useEffect,
  useState,
  type AnchorHTMLAttributes,
  type MouseEvent,
} from 'react'

/**
 * A dependency-free client-side router.
 *
 * Four real pages: the material library at `/`, the Teacher Studio at
 * `/studio/{artifactId}`, the Classroom at `/classroom/{classId}` and the
 * learning page at `/learn/{artifactId}`; plus two sectioned areas,
 * `/admin/{section}` (create/read management of the V0 entities) and
 * `/settings/{section}` (client preferences and read-only server facts), and —
 * V0-021 — the sign-in page at `/login`, a class's student join page at
 * `/join/{classId}` and the student's own fullscreen view of it at
 * `/student/{classId}`. Each is its own page on purpose — the studio is the
 * large-screen slide review surface, the classroom is the runtime session view,
 * the learning page is the slide + teaching canvas and the student page is what
 * a phone in a lecture hall opens — so each is opened directly (often in a
 * second tab or on a second screen) and must survive a deep link and a refresh.
 * Single-origin mode is covered by the backend's SPA fallback
 * (`backend/app/api/spa.py`); the Vite dev server already serves the shell.
 */

export const LIBRARY_PATH = '/'
export const STUDIO_PATH = '/studio'
export const CLASSROOM_PATH = '/classroom'
export const LEARN_PATH = '/learn'
export const ADMIN_PATH = '/admin'
export const SETTINGS_PATH = '/settings'
export const LOGIN_PATH = '/login'
/** Where a student enters a class (V0-021). */
export const JOIN_PATH = '/join'
/** The student's own fullscreen view of a class they have joined (V0-021). */
export const STUDENT_PATH = '/student'

/** The admin (data management) sections, one route each. */
export const ADMIN_SECTIONS = ['overview', 'courses', 'classes', 'publications'] as const
export type AdminSection = (typeof ADMIN_SECTIONS)[number]

/** The settings sections, one route each. */
export const SETTINGS_SECTIONS = ['general', 'rendering', 'teaching', 'accessibility'] as const
export type SettingsSection = (typeof SETTINGS_SECTIONS)[number]

export type Route =
  | { name: 'library' }
  | { name: 'studio'; artifactId: string }
  | { name: 'classroom'; classId: string }
  | { name: 'learn'; artifactId: string }
  | { name: 'admin'; section: AdminSection }
  | { name: 'settings'; section: SettingsSection }
  | { name: 'login' }
  | { name: 'join'; classId: string }
  | { name: 'student'; classId: string }
  | { name: 'not-found'; path: string }

/** The canonical URL of the sign-in page, optionally with somewhere to return to. */
export function loginPath(next?: string): string {
  return next ? `${LOGIN_PATH}?next=${encodeURIComponent(next)}` : LOGIN_PATH
}

/** The canonical URL of one class's student join page. */
export function joinPath(classId: string): string {
  return `${JOIN_PATH}/${encodeURIComponent(classId)}`
}

/** The canonical URL of one class's student view. */
export function studentPath(classId: string): string {
  return `${STUDENT_PATH}/${encodeURIComponent(classId)}`
}

/** The canonical URL of one artifact's Teacher Studio page. */
export function studioPath(artifactId: string): string {
  return `${STUDIO_PATH}/${encodeURIComponent(artifactId)}`
}

/** The canonical URL of one class's classroom page. */
export function classroomPath(classId: string): string {
  return `${CLASSROOM_PATH}/${encodeURIComponent(classId)}`
}

/** The canonical URL of one artifact's learning page. */
export function learnPath(artifactId: string): string {
  return `${LEARN_PATH}/${encodeURIComponent(artifactId)}`
}

/** The canonical URL of an admin section (`/admin` is the overview). */
export function adminPath(section: AdminSection = 'overview'): string {
  return section === 'overview' ? ADMIN_PATH : `${ADMIN_PATH}/${section}`
}

/** The canonical URL of a settings section (`/settings` is general). */
export function settingsPath(section: SettingsSection = 'general'): string {
  return section === 'general' ? SETTINGS_PATH : `${SETTINGS_PATH}/${section}`
}

/**
 * Decode a single path segment into an id. Anything that is empty, contains a
 * slash or does not decode is not an id, so the path falls through to 404.
 */
function parseId(raw: string): string | null {
  if (!raw || raw.includes('/')) return null
  try {
    const decoded = decodeURIComponent(raw)
    // A decoded slash would not survive the matching `*Path()` builder.
    return decoded && !decoded.includes('/') ? decoded : null
  } catch {
    return null
  }
}

/** Map a pathname onto a route. Unknown paths are the app's own 404 view. */
export function parseRoute(pathname: string): Route {
  // A server may hand through a query string or a fragment; neither names a page.
  const path = pathname.split('?')[0].split('#')[0]
  const trimmed = path.replace(/\/+$/, '') || LIBRARY_PATH

  if (trimmed === LIBRARY_PATH) return { name: 'library' }

  if (trimmed === LOGIN_PATH) return { name: 'login' }

  if (trimmed.startsWith(`${JOIN_PATH}/`)) {
    const classId = parseId(trimmed.slice(JOIN_PATH.length + 1))
    if (classId) return { name: 'join', classId }
  }

  if (trimmed.startsWith(`${STUDENT_PATH}/`)) {
    const classId = parseId(trimmed.slice(STUDENT_PATH.length + 1))
    if (classId) return { name: 'student', classId }
  }

  if (trimmed.startsWith(`${STUDIO_PATH}/`)) {
    const artifactId = parseId(trimmed.slice(STUDIO_PATH.length + 1))
    if (artifactId) return { name: 'studio', artifactId }
  }

  if (trimmed.startsWith(`${CLASSROOM_PATH}/`)) {
    const classId = parseId(trimmed.slice(CLASSROOM_PATH.length + 1))
    if (classId) return { name: 'classroom', classId }
  }

  if (trimmed.startsWith(`${LEARN_PATH}/`)) {
    const artifactId = parseId(trimmed.slice(LEARN_PATH.length + 1))
    if (artifactId) return { name: 'learn', artifactId }
  }

  // The admin and settings areas are a fixed set of sections, so an unknown
  // section is a 404 rather than an empty page.
  if (trimmed === ADMIN_PATH) return { name: 'admin', section: 'overview' }
  if (trimmed.startsWith(`${ADMIN_PATH}/`)) {
    const section = trimmed.slice(ADMIN_PATH.length + 1)
    if ((ADMIN_SECTIONS as readonly string[]).includes(section)) {
      return { name: 'admin', section: section as AdminSection }
    }
  }

  if (trimmed === SETTINGS_PATH) return { name: 'settings', section: 'general' }
  if (trimmed.startsWith(`${SETTINGS_PATH}/`)) {
    const section = trimmed.slice(SETTINGS_PATH.length + 1)
    if ((SETTINGS_SECTIONS as readonly string[]).includes(section)) {
      return { name: 'settings', section: section as SettingsSection }
    }
  }

  return { name: 'not-found', path: trimmed }
}

/** The route for the current location, re-read on back/forward and on `navigate`. */
export function useRoute(): Route {
  const [pathname, setPathname] = useState(() => window.location.pathname)

  useEffect(() => {
    function onPopState() {
      setPathname(window.location.pathname)
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  return parseRoute(pathname)
}

/** Push a client-side location and tell `useRoute` about it. */
export function navigate(to: string, options: { replace?: boolean } = {}): void {
  const current = `${window.location.pathname}${window.location.search}`
  if (to === current) return
  if (options.replace) window.history.replaceState({}, '', to)
  else window.history.pushState({}, '', to)
  // `pushState` does not fire `popstate`, so the route hook would not update.
  window.dispatchEvent(new PopStateEvent('popstate'))
}

type LinkProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href' | 'onClick'> & {
  to: string
  onClick?: (event: MouseEvent<HTMLAnchorElement>) => void
}

/**
 * An `<a>` that is routed client-side but stays a real link: middle-click,
 * cmd/ctrl-click and "open in new tab" are left to the browser, which is
 * exactly how the studio gets onto a large screen.
 */
export function Link({ to, children, onClick, ...rest }: LinkProps) {
  const handleClick = useCallback(
    (event: MouseEvent<HTMLAnchorElement>) => {
      onClick?.(event)
      if (event.defaultPrevented) return
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
      if (rest.target && rest.target !== '_self') return
      event.preventDefault()
      navigate(to)
    },
    [onClick, rest.target, to],
  )

  return (
    <a {...rest} href={to} onClick={handleClick}>
      {children}
    </a>
  )
}
