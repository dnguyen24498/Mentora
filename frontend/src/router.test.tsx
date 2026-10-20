import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import {
  adminPath,
  classroomPath,
  joinPath,
  learnPath,
  Link,
  loginPath,
  navigate,
  parseRoute,
  settingsPath,
  studentPath,
  studioPath,
} from './router'

const ARTIFACT = '1e4c06bc-f29e-4ba4-9b39-b0b2cf5f4f1e'

describe('parseRoute', () => {
  it('maps the root to the material library', () => {
    expect(parseRoute('/')).toEqual({ name: 'library' })
    // A trailing slash is the same page.
    expect(parseRoute('/')).toEqual({ name: 'library' })
  })

  it('maps /studio/{artifactId} to the studio page', () => {
    expect(parseRoute(`/studio/${ARTIFACT}`)).toEqual({ name: 'studio', artifactId: ARTIFACT })
    // Trailing slash, query string and fragment are not part of the id.
    expect(parseRoute(`/studio/${ARTIFACT}/`)).toEqual({ name: 'studio', artifactId: ARTIFACT })
    expect(parseRoute(`/studio/${ARTIFACT}?tab=notes`)).toEqual({
      name: 'studio',
      artifactId: ARTIFACT,
    })
    expect(parseRoute(`/studio/${ARTIFACT}#top`)).toEqual({ name: 'studio', artifactId: ARTIFACT })
  })

  it('decodes an escaped artifact id', () => {
    expect(parseRoute('/studio/a%2Fb')).toEqual({ name: 'not-found', path: '/studio/a%2Fb' })
    expect(parseRoute('/studio/a%20b')).toEqual({ name: 'studio', artifactId: 'a b' })
  })

  it('falls back to not-found for anything else, including an empty studio id', () => {
    expect(parseRoute('/studio')).toEqual({ name: 'not-found', path: '/studio' })
    expect(parseRoute('/studio/')).toEqual({ name: 'not-found', path: '/studio' })
    expect(parseRoute('/studio/a/b')).toEqual({ name: 'not-found', path: '/studio/a/b' })
    expect(parseRoute('/classroom')).toEqual({ name: 'not-found', path: '/classroom' })
    expect(parseRoute('/nope')).toEqual({ name: 'not-found', path: '/nope' })
  })

  it('maps /classroom/{classId} to the classroom page', () => {
    expect(parseRoute('/classroom/class-1')).toEqual({ name: 'classroom', classId: 'class-1' })
    expect(parseRoute('/classroom/class-1/')).toEqual({ name: 'classroom', classId: 'class-1' })
    expect(parseRoute('/classroom/a/b')).toEqual({ name: 'not-found', path: '/classroom/a/b' })
  })

  it('maps /learn/{artifactId} to the learning page', () => {
    expect(parseRoute(`/learn/${ARTIFACT}`)).toEqual({ name: 'learn', artifactId: ARTIFACT })
    expect(parseRoute(`/learn/${ARTIFACT}/`)).toEqual({ name: 'learn', artifactId: ARTIFACT })
    expect(parseRoute(`/learn/${ARTIFACT}?slide=2`)).toEqual({
      name: 'learn',
      artifactId: ARTIFACT,
    })
    // No id, a deeper path or an escaped slash is not the page.
    expect(parseRoute('/learn')).toEqual({ name: 'not-found', path: '/learn' })
    expect(parseRoute('/learn/')).toEqual({ name: 'not-found', path: '/learn' })
    expect(parseRoute('/learn/a/b')).toEqual({ name: 'not-found', path: '/learn/a/b' })
    expect(parseRoute('/learn/a%2Fb')).toEqual({ name: 'not-found', path: '/learn/a%2Fb' })
  })
})

describe('studioPath', () => {
  it('builds the canonical studio URL and round-trips through parseRoute', () => {
    expect(studioPath(ARTIFACT)).toBe(`/studio/${ARTIFACT}`)
    expect(parseRoute(studioPath(ARTIFACT))).toEqual({ name: 'studio', artifactId: ARTIFACT })
  })
})

describe('classroomPath', () => {
  it('builds the canonical classroom URL and round-trips through parseRoute', () => {
    expect(classroomPath('class-1')).toBe('/classroom/class-1')
    expect(parseRoute(classroomPath('class-1'))).toEqual({ name: 'classroom', classId: 'class-1' })
  })
})

describe('learnPath', () => {
  it('builds the canonical learning URL and round-trips through parseRoute', () => {
    expect(learnPath(ARTIFACT)).toBe(`/learn/${ARTIFACT}`)
    expect(parseRoute(learnPath(ARTIFACT))).toEqual({ name: 'learn', artifactId: ARTIFACT })
  })
})

describe('admin routes', () => {
  it('maps /admin to the overview and /admin/{section} to a section', () => {
    expect(parseRoute('/admin')).toEqual({ name: 'admin', section: 'overview' })
    expect(parseRoute('/admin/')).toEqual({ name: 'admin', section: 'overview' })
    expect(parseRoute('/admin/courses')).toEqual({ name: 'admin', section: 'courses' })
    expect(parseRoute('/admin/classes?course=1')).toEqual({ name: 'admin', section: 'classes' })
  })

  it('treats an unknown section as not found rather than an empty page', () => {
    expect(parseRoute('/admin/nope')).toEqual({ name: 'not-found', path: '/admin/nope' })
    expect(parseRoute('/admin/courses/extra')).toEqual({
      name: 'not-found',
      path: '/admin/courses/extra',
    })
    // A near-miss is not the area either.
    expect(parseRoute('/adminx')).toEqual({ name: 'not-found', path: '/adminx' })
  })
})

describe('settings routes', () => {
  it('maps /settings to general and /settings/{section} to a section', () => {
    expect(parseRoute('/settings')).toEqual({ name: 'settings', section: 'general' })
    expect(parseRoute('/settings/rendering')).toEqual({ name: 'settings', section: 'rendering' })
    expect(parseRoute('/settings/teaching')).toEqual({ name: 'settings', section: 'teaching' })
    expect(parseRoute('/settings/accessibility')).toEqual({
      name: 'settings',
      section: 'accessibility',
    })
    expect(parseRoute('/settings/security')).toEqual({ name: 'settings', section: 'security' })
  })

  it('treats an unknown section as not found', () => {
    expect(parseRoute('/settings/nope')).toEqual({ name: 'not-found', path: '/settings/nope' })
  })
})

describe('adminPath and settingsPath', () => {
  it('omits the section for the default page and round-trips through parseRoute', () => {
    expect(adminPath()).toBe('/admin')
    expect(adminPath('overview')).toBe('/admin')
    expect(adminPath('publications')).toBe('/admin/publications')
    expect(parseRoute(adminPath('publications'))).toEqual({
      name: 'admin',
      section: 'publications',
    })

    expect(settingsPath()).toBe('/settings')
    expect(settingsPath('general')).toBe('/settings')
    expect(settingsPath('teaching')).toBe('/settings/teaching')
    expect(parseRoute(settingsPath('teaching'))).toEqual({ name: 'settings', section: 'teaching' })
  })
})

describe('identity routes (V0-021)', () => {
  it('maps /login to the sign-in page', () => {
    expect(parseRoute('/login')).toEqual({ name: 'login' })
    expect(parseRoute('/login/')).toEqual({ name: 'login' })
    // `?next=` is where to return to, not part of the route.
    expect(parseRoute('/login?next=%2Fjoin%2Fclass-1')).toEqual({ name: 'login' })
  })

  it('maps /join/{classId} to the student join page and /student/{classId} to the student view', () => {
    expect(parseRoute('/join/class-1')).toEqual({ name: 'join', classId: 'class-1' })
    expect(parseRoute('/join/class-1/')).toEqual({ name: 'join', classId: 'class-1' })
    expect(parseRoute('/student/class-1')).toEqual({ name: 'student', classId: 'class-1' })
    expect(parseRoute('/student/class-1?slide=2')).toEqual({ name: 'student', classId: 'class-1' })
    // No class id is not the page: a join with nothing to join would be a trap.
    expect(parseRoute('/join')).toEqual({ name: 'not-found', path: '/join' })
    expect(parseRoute('/join/')).toEqual({ name: 'not-found', path: '/join' })
    expect(parseRoute('/student')).toEqual({ name: 'student-home' })
    expect(parseRoute('/student/')).toEqual({ name: 'student-home' })
    expect(parseRoute('/student/a/b')).toEqual({ name: 'not-found', path: '/student/a/b' })
  })
})

describe('loginPath, joinPath and studentPath', () => {
  it('builds canonical URLs that round-trip through parseRoute', () => {
    expect(loginPath()).toBe('/login')
    expect(loginPath('/join/class-1')).toBe('/login?next=%2Fjoin%2Fclass-1')
    expect(parseRoute(loginPath('/join/class-1'))).toEqual({ name: 'login' })

    expect(joinPath('class-1')).toBe('/join/class-1')
    expect(parseRoute(joinPath('class-1'))).toEqual({ name: 'join', classId: 'class-1' })
    expect(studentPath('class-1')).toBe('/student/class-1')
    expect(parseRoute(studentPath('class-1'))).toEqual({ name: 'student', classId: 'class-1' })
  })
})

describe('navigate and Link', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/')
  })

  it('pushes a client-side location without a full page load', async () => {
    const user = userEvent.setup()
    render(<Link to={studioPath(ARTIFACT)}>Open Teacher Studio</Link>)

    await user.click(screen.getByRole('link', { name: 'Open Teacher Studio' }))

    expect(window.location.pathname).toBe(`/studio/${ARTIFACT}`)
    // The href is real, so the link works with no JS and in a new tab.
    expect(screen.getByRole('link', { name: 'Open Teacher Studio' }).getAttribute('href')).toBe(
      `/studio/${ARTIFACT}`,
    )
  })

  it('leaves a new-tab link to the browser', async () => {
    const user = userEvent.setup()
    render(
      <Link to={studioPath(ARTIFACT)} target="_blank" rel="noreferrer">
        Open in a new tab
      </Link>,
    )

    await user.click(screen.getByRole('link', { name: 'Open in a new tab' }))

    // The router did not take over: the location is untouched (jsdom does not
    // follow target=_blank, which is exactly what the real browser would do).
    expect(window.location.pathname).toBe('/')
  })

  it('does not push the same location twice', () => {
    navigate('/studio/x')
    const before = window.history.length
    navigate('/studio/x')
    expect(window.history.length).toBe(before)
  })
})
