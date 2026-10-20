import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SiteNav from './SiteNav'
import { logout } from '../api/client'
import { writeSession, clearSession, readSession } from '../auth/session'
import { writeSelectedArtifact, writeSelectedClass } from '../institution'
import { ARTIFACT } from '../test/fixtures'

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return { ...actual, logout: vi.fn() }
})

/**
 * The shared nav is the answer to "get from any page to any other page". The two
 * scoped pages (Studio/Learn need a deck, Classroom needs a class) are only
 * links once there is an id to link to; before that they say why they are not.
 *
 * Since V0-023 the entries are chosen by **capability**, and no session is no
 * capabilities, so these tests sign a teacher in: the nav only ever renders inside
 * a page the route guard let through.
 */
describe('SiteNav', () => {
  beforeEach(() => {
    localStorage.clear()
    clearSession()
    signInAs('teacher')
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
    clearSession()
  })

  it('offers sign-in, and claims nothing at all, with no session (V0-023)', () => {
    render(<SiteNav current="library" />)

    expect(screen.getByRole('link', { name: 'Sign in' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Sign out' })).toBeNull()
    expect(screen.queryByTestId('session-principal')).toBeNull()
    // No session is no capabilities: the authoring entries are gone, not disabled.
    for (const label of ['Library', 'Studio', 'Classroom', 'Learn']) {
      expect(screen.queryByText(label)).toBeNull()
    }
    // The old "development mode" chip was removed; the shortcut is off by default.
    expect(screen.queryByTestId('session-development')).toBeNull()
  })

  it('shows the signed-in principal and a way out', () => {
    signInAs('teacher')
    writeSelectedArtifact(ARTIFACT)
    render(<SiteNav current="library" />)

    expect(screen.getByTestId('session-principal').textContent).toContain('Teacher · Teacher')
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeTruthy()
    // A teacher keeps the authoring entries.
    expect(screen.getByRole('link', { name: 'Library' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Studio' }).getAttribute('href')).toBe(
      `/studio/${ARTIFACT}`,
    )
  })

  it('gives an administrator the library and the directory, not the authoring surfaces', () => {
    signInAs('institution_admin')
    writeSelectedArtifact(ARTIFACT)
    writeSelectedClass('class-1')

    render(<SiteNav current="library" />)

    expect(screen.getByRole('link', { name: 'Library' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Admin' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Settings' })).toBeTruthy()
    // An administrator authors nothing and is not a participant, so the nav does
    // not offer a page whose every request would answer 403.
    for (const label of ['Studio', 'Classroom', 'Learn']) {
      expect(screen.queryByRole('link', { name: label })).toBeNull()
      expect(screen.queryByText(label)).toBeNull()
    }
  })

  it('offers a student their classes instead of the authoring entries', () => {
    signInAs('student')
    writeSelectedClass('class-1')

    render(<SiteNav current="join" />)

    expect(screen.getByRole('link', { name: 'My classes' }).getAttribute('href')).toBe('/student')
    expect(screen.getByRole('link', { name: 'Attend' }).getAttribute('href')).toBe(
      '/student/class-1',
    )
    // The authoring surfaces are gone, not merely disabled.
    for (const label of ['Studio', 'Classroom', 'Learn', 'Admin']) {
      expect(screen.queryByRole('link', { name: label })).toBeNull()
    }
  })

  it('still offers the class list before a student has opened a class', () => {
    signInAs('student')
    render(<SiteNav current="student-home" />)

    // The list is the student's own roster and needs no remembered class id.
    expect(screen.getByRole('link', { name: 'My classes' }).getAttribute('href')).toBe('/student')
    // The class-scoped entry does need one, so it is explained rather than a link.
    expect(screen.queryByRole('link', { name: 'Attend' })).toBeNull()
    expect(screen.getByText('Attend').getAttribute('aria-disabled')).toBe('true')
  })

  it('does not link the page you are already on', () => {
    render(<SiteNav current="login" />)
    expect(screen.queryByRole('link', { name: 'Sign in' })).toBeNull()
    expect(screen.getByText('Sign in').getAttribute('aria-disabled')).toBe('true')
  })

  it('signs out from the nav, clearing the session whatever the server says', async () => {
    const user = userEvent.setup()
    signInAs('teacher')
    vi.mocked(logout).mockResolvedValue({ revoked: true })
    render(<SiteNav current="library" />)

    await user.click(screen.getByRole('button', { name: 'Sign out' }))

    await waitFor(() => expect(logout).toHaveBeenCalled())
    expect(readSession()).toBeNull()
    expect(screen.getByRole('link', { name: 'Sign in' })).toBeTruthy()
  })
})

function signInAs(role: 'teacher' | 'student' | 'institution_admin') {
  const TEACHER_SCOPES = [
    'account:read',
    'class:read',
    'class:write',
    'content:read',
    'content:write',
    'enrollment:write',
    'publication:write',
    'review:write',
    'scene:read',
  ]
  const scopes =
    role === 'student'
      ? ['class:read', 'scene:read', 'join']
      : role === 'institution_admin'
        ? ['account:read', 'account:write', 'content:read', 'class:read']
        : TEACHER_SCOPES
  const session = {
    token: 'tok-1',
    principal: {
      authenticated: true,
      institution_id: 'university-001',
      role,
      scopes,
      account_id: 'account-1',
      email: role === 'student' ? 'student7@school.example' : `${role}@school.example`,
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
