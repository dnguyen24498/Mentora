import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SiteNav from './SiteNav'
import { ApiError, loadPrincipal } from '../api/client'
import { writeSession, clearSession } from '../auth/session'
import { resetDevelopmentMode } from '../auth/mode'
import { writeSelectedArtifact, writeSelectedClass } from '../institution'
import { INSTITUTION, ARTIFACT } from '../test/fixtures'

// The nav asks the API which mode it is in (`GET /auth/me`), because the
// development shortcut has no session to inspect.
vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return { ...actual, loadPrincipal: vi.fn(), logout: vi.fn() }
})

beforeEach(() => {
  vi.mocked(loadPrincipal).mockRejectedValue(new ApiError('UNAUTHENTICATED', 'no session'))
})

/**
 * The shared nav is the answer to "get from any page to any other page". The two
 * scoped pages (Studio/Learn need a deck, Classroom needs a class) are only
 * links once there is an id to link to; before that they say why they are not.
 */
describe('SiteNav', () => {
  beforeEach(() => {
    localStorage.clear()
    // The session and the mode probe are both memoised in their modules, so
    // clearing storage is not enough.
    clearSession()
    resetDevelopmentMode()
  })

  it('always links the library, and explains the pages that need a deck or class', () => {
    render(<SiteNav current="library" />)

    expect(screen.getByRole('link', { name: 'Library' }).getAttribute('href')).toBe('/')

    for (const label of ['Studio', 'Classroom', 'Learn']) {
      // Not a link yet: a nav entry that goes nowhere would be a trap.
      expect(screen.queryByRole('link', { name: label })).toBeNull()
      expect(screen.getByText(label).getAttribute('aria-disabled')).toBe('true')
    }
  })

  it('links every page from the remembered deck and class', () => {
    writeSelectedArtifact(ARTIFACT)
    writeSelectedClass('class-1')

    render(<SiteNav current="library" />)

    expect(screen.getByRole('link', { name: 'Studio' }).getAttribute('href')).toBe(
      `/studio/${ARTIFACT}`,
    )
    expect(screen.getByRole('link', { name: 'Classroom' }).getAttribute('href')).toBe(
      '/classroom/class-1',
    )
    expect(screen.getByRole('link', { name: 'Learn' }).getAttribute('href')).toBe(
      `/learn/${ARTIFACT}`,
    )
  })

  it('links the sectioned areas even with no deck or class', () => {
    render(<SiteNav current="library" />)

    expect(screen.getByRole('link', { name: 'Admin' }).getAttribute('href')).toBe('/admin')
    expect(screen.getByRole('link', { name: 'Settings' }).getAttribute('href')).toBe('/settings')
  })

  it('marks the sectioned areas as current where they are the page', () => {
    render(<SiteNav current="admin" />)
    expect(screen.getByRole('link', { name: 'Admin' }).getAttribute('aria-current')).toBe('page')
    expect(screen.getByRole('link', { name: 'Settings' }).getAttribute('aria-current')).toBeNull()
  })

  it('marks the current page and prefers the id the page itself holds', () => {
    writeSelectedArtifact('a-deck-opened-earlier')

    render(<SiteNav current="studio" artifactId={ARTIFACT} />)

    const studio = screen.getByRole('link', { name: 'Studio' })
    expect(studio.getAttribute('href')).toBe(`/studio/${ARTIFACT}`)
    expect(studio.getAttribute('aria-current')).toBe('page')
    expect(screen.getByRole('link', { name: 'Library' }).getAttribute('aria-current')).toBeNull()
  })
})

/**
 * With identities (V0-021) the nav also has to answer "who am I", and offer a
 * student the entries a student can actually use — the authoring entries would
 * only answer `403`. The role is still enforced server-side; this is the honest
 * version of the same fact.
 */
describe('SiteNav — identities', () => {
  beforeEach(() => {
    localStorage.clear()
    // The session and the mode probe are both memoised in their modules, so
    // clearing storage is not enough.
    clearSession()
    resetDevelopmentMode()
  })

  it('offers sign-in, and never claims a user, with no session', () => {
    render(<SiteNav current="library" />)

    expect(screen.getByRole('link', { name: 'Sign in' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Sign out' })).toBeNull()
    expect(screen.queryByTestId('session-principal')).toBeNull()
  })

  it('names the development shortcut rather than a signed-in user', () => {
    // The dev shortcut has no session at all, so the nav has nothing to name
    // beyond "you are not signed in".
    render(<SiteNav current="library" />)

    expect(screen.queryByTestId('session-principal')).toBeNull()
    expect(screen.getByRole('link', { name: 'Sign in' }).getAttribute('href')).toBe('/login')
  })

  it('names the development shortcut when the API reports it', async () => {
    // With no session the client cannot see which mode it is in, so it asks:
    // `/auth/me` answers `authenticated: false` for the tenant header shortcut.
    vi.mocked(loadPrincipal).mockResolvedValue({
      principal: {
        authenticated: false,
        institution_id: INSTITUTION,
        role: 'teacher',
        scopes: [],
        account_id: null,
        email: null,
        display_name: null,
        session_id: null,
      },
      authenticator: {
        id: 'local-credentials@1.0.0',
        name: 'local-credentials',
        version: '1.0.0',
        kind: 'DEVELOPMENT_MOCK',
      },
      notice: 'development shortcut',
      development_shortcut: true,
    })
    resetDevelopmentMode()

    render(<SiteNav current="library" />)

    // It says "development mode", never a signed-in user.
    expect(await screen.findByTestId('session-development')).toBeTruthy()
    expect(screen.queryByTestId('session-principal')).toBeNull()
    expect(screen.getByRole('link', { name: 'Sign in' })).toBeTruthy()
  })

  it('does not claim a mode when the shortcut is switched off', async () => {
    // `401 SESSION_REQUIRED`: the header is not accepted by this deployment, so
    // "development mode" would be a lie.
    vi.mocked(loadPrincipal).mockRejectedValue(new ApiError('UNAUTHENTICATED', 'no session'))
    resetDevelopmentMode()

    render(<SiteNav current="library" />)

    expect(screen.queryByTestId('session-development')).toBeNull()
    await waitFor(() => expect(loadPrincipal).toHaveBeenCalled())
  })

  it('shows the signed-in principal and a way out', () => {
    signInAs('teacher')
    writeSelectedArtifact(ARTIFACT)
    render(<SiteNav current="library" />)

    expect(screen.getByTestId('session-principal').textContent).toContain('Teacher · teacher')
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeTruthy()
    // A teacher keeps the authoring entries.
    expect(screen.getByRole('link', { name: 'Library' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Studio' }).getAttribute('href')).toBe(
      `/studio/${ARTIFACT}`,
    )
  })

  it('offers a student their class instead of the authoring entries', () => {
    signInAs('student')
    writeSelectedClass('class-1')

    render(<SiteNav current="join" />)

    expect(screen.getByRole('link', { name: 'My class' }).getAttribute('href')).toBe(
      '/join/class-1',
    )
    expect(screen.getByRole('link', { name: 'Attend' }).getAttribute('href')).toBe(
      '/student/class-1',
    )
    // The authoring surfaces are gone, not merely disabled.
    for (const label of ['Studio', 'Classroom', 'Learn', 'Admin']) {
      expect(screen.queryByRole('link', { name: label })).toBeNull()
    }
  })

  it('explains a student’s entries before they have a class', () => {
    signInAs('student')
    render(<SiteNav current="library" />)

    for (const label of ['My class', 'Attend']) {
      expect(screen.queryByRole('link', { name: label })).toBeNull()
      expect(screen.getByText(label).getAttribute('aria-disabled')).toBe('true')
    }
  })

  it('does not link the page you are already on', () => {
    render(<SiteNav current="login" />)
    expect(screen.queryByRole('link', { name: 'Sign in' })).toBeNull()
    expect(screen.getByText('Sign in').getAttribute('aria-disabled')).toBe('true')
  })
})

function signInAs(role: 'teacher' | 'student') {
  const session = {
    token: 'tok-1',
    principal: {
      authenticated: true,
      institution_id: 'university-001',
      role,
      scopes: role === 'student' ? ['class:read', 'scene:read', 'join'] : ['class:write'],
      account_id: 'account-1',
      email: role === 'student' ? 'student7@school.example' : 'teacher@school.example',
      display_name: role === 'student' ? null : 'Teacher',
      session_id: 'session-1',
    },
    authenticator: {
      id: 'local-credentials@1.0.0',
      name: 'local-credentials',
      version: '1.0.0',
      kind: 'DEVELOPMENT_MOCK' as const,
    },
    notice: 'mock',
    expiresAt: new Date(Date.now() + 3_600_000).toISOString(),
  }
  writeSession(session)
}
