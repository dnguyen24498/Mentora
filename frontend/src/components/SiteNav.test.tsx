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
 * scoped pages (Studio/Learn need a deck, Classroom needs a class) are links even
 * before an id is known: they fall back to the chooser where that id is picked
 * (the Library for a deck, Admin → Classes for a class), so an entry is never a
 * dead label.
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

  it('always links the library, and sends a page that needs a deck or class to its chooser', () => {
    render(<SiteNav current="library" />)

    expect(screen.getByRole('link', { name: 'Library' }).getAttribute('href')).toBe('/')

    // No remembered deck/class: the entry is still a real link, to where one is
    // chosen — not a disabled label that looks like a broken page.
    expect(screen.getByRole('link', { name: 'Studio' }).getAttribute('href')).toBe('/')
    // Classroom hub is the chooser for classes.
    expect(screen.getByRole('link', { name: 'Classroom' }).getAttribute('href')).toBe(
      '/classroom',
    )
    // Learn link removed from navigation (V0-026).
    for (const label of ['Studio', 'Classroom']) {
      expect(screen.getByRole('link', { name: label }).getAttribute('aria-disabled')).toBeNull()
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
      '/classroom',
    )
    // Learn link removed from navigation (V0-026).
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
    // An administrator can read the directory, and the hub is now open to anyone
    // with class:read. The authoring surfaces remain out of scope.
    for (const label of ['Studio', 'Learn']) {
      expect(screen.queryByRole('link', { name: label })).toBeNull()
      expect(screen.queryByText(label)).toBeNull()
    }
    expect(screen.getByRole('link', { name: 'Classroom' })).toBeTruthy()
  })

  it('offers a student their classroom list instead of the authoring entries', () => {
    signInAs('student')
    writeSelectedClass('class-1')

    render(<SiteNav current="join" />)

    // The classroom hub replaces the student's separate class list.
    expect(screen.getByRole('link', { name: 'Classroom' }).getAttribute('href')).toBe(
      '/classroom',
    )
    // The authoring surfaces are gone, not merely disabled.
    for (const label of ['Studio', 'Learn', 'Admin']) {
      expect(screen.queryByRole('link', { name: label })).toBeNull()
    }
  })

  it('still offers the class list before a student has opened a class', () => {
    signInAs('student')
    render(<SiteNav current="student-home" />)

    // The list is the student's own roster and needs no remembered class id.
    expect(screen.getByRole('link', { name: 'Classroom' }).getAttribute('href')).toBe(
      '/classroom',
    )
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
