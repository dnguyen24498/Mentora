import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import {
  clearSession,
  currentToken,
  describeAuthenticator,
  describePrincipal,
  hasScope,
  isSignedIn,
  isStudent,
  readSession,
  useSession,
  writeSession,
  type AuthSession,
} from './session'

/**
 * The session store is where the credential lives, so its exact semantics are
 * worth pinning: only the token is ever sent, an expired session is not a
 * session, and the capability check is advisory (the server is the authority).
 */

function session(overrides: Partial<AuthSession> = {}): AuthSession {
  const base: AuthSession = {
    token: 'tok-1',
    principal: {
      authenticated: true,
      institution_id: 'university-001',
      role: 'student',
      scopes: ['class:read', 'scene:read', 'join'],
      account_id: 'account-7',
      email: 'student7@school.example',
      display_name: 'Student Seven',
      session_id: 'session-1',
    },
    authenticator: {
      id: 'local-credentials@1.0.0',
      name: 'local-credentials',
      version: '1.0.0',
      kind: 'DEVELOPMENT_MOCK',
    },
    notice: 'The credential mechanism is a labelled development mock.',
    expiresAt: new Date(Date.now() + 3_600_000).toISOString(),
  }
  return { ...base, ...overrides }
}

describe('session store', () => {
  beforeEach(() => {
    localStorage.clear()
    clearSession()
  })

  it('round-trips a session and exposes the token to the API client', () => {
    expect(readSession()).toBeNull()
    expect(currentToken()).toBeNull()

    writeSession(session())

    expect(currentToken()).toBe('tok-1')
    expect(readSession()?.principal.institution_id).toBe('university-001')
    // Persisted, so a refresh stays signed in.
    expect(localStorage.getItem('mentora.session')).toContain('tok-1')
  })

  it('treats an expired session as no session at all', () => {
    writeSession(session({ expiresAt: new Date(Date.now() - 1000).toISOString() }))

    // The server would refuse it anyway; showing a signed-in page that 401s
    // every request would be the worse answer.
    expect(readSession()).toBeNull()
    expect(currentToken()).toBeNull()
  })

  it('keeps a session whose expiry it cannot parse', () => {
    // The server is the authority on lifetime; a format change must not sign
    // everyone out.
    writeSession(session({ expiresAt: 'not-a-date' }))
    expect(readSession()).not.toBeNull()
  })

  it('ignores a corrupt stored value rather than throwing', () => {
    localStorage.setItem('mentora.session', '{not json')
    // Force a re-read: a previous read would have memoised.
    clearSession()
    localStorage.setItem('mentora.session', '{not json')
    expect(() => readSession()).not.toThrow()
    expect(readSession()).toBeNull()
  })

  it('notifies subscribers on sign-in and sign-out', () => {
    const seen: string[] = []
    function Probe() {
      const current = useSession()
      seen.push(describePrincipal(current))
      return <span data-testid="who">{describePrincipal(current)}</span>
    }

    render(<Probe />)
    expect(screen.getByTestId('who').textContent).toBe('Not signed in')

    act(() => writeSession(session()))
    expect(screen.getByTestId('who').textContent).toBe('Student Seven · Student')

    act(() => clearSession())
    expect(screen.getByTestId('who').textContent).toBe('Not signed in')

    // Each state change re-rendered the subscriber.
    expect(seen).toContain('Student Seven · Student')
  })

  it('clears the persisted value on sign-out', () => {
    writeSession(session())
    clearSession()
    expect(localStorage.getItem('mentora.session')).toBeNull()
    expect(currentToken()).toBeNull()
  })
})

describe('capability checks', () => {
  beforeEach(() => {
    localStorage.clear()
    clearSession()
  })

  it('reads capabilities off the session, not the role name', () => {
    const student = session()
    expect(hasScope(student, 'join')).toBe(true)
    expect(hasScope(student, 'enrollment:write')).toBe(false)

    const teacher = session({
      principal: { ...student.principal, role: 'teacher', scopes: ['enrollment:write'] },
    })
    expect(hasScope(teacher, 'enrollment:write')).toBe(true)
    expect(hasScope(teacher, 'join')).toBe(false)
  })

  it('treats no session as no capabilities at all (V0-023)', () => {
    // Every page requires a sign-in, and the development tenant shortcut is off by
    // default, so a caller with no session holds nothing and is shown nothing — the
    // route guard sends it to `/login`. The server enforces the same rule.
    for (const scope of [
      'content:read',
      'content:write',
      'class:write',
      'enrollment:write',
      'scene:read',
      'account:write',
      'join',
    ] as const) {
      expect(hasScope(null, scope)).toBe(false)
    }
    expect(isSignedIn(null)).toBe(false)
    expect(isStudent(null)).toBe(false)
  })

  it('distinguishes a real sign-in from no session', () => {
    expect(isSignedIn(session())).toBe(true)
    expect(isStudent(session())).toBe(true)
    expect(isStudent(session({ principal: { ...session().principal, role: 'teacher' } }))).toBe(false)
  })
})

describe('descriptions', () => {
  beforeEach(() => {
    localStorage.clear()
    clearSession()
  })

  it('says plainly that nobody is signed in', () => {
    expect(describePrincipal(null)).toBe('Not signed in')
  })

  it('names the person and their role', () => {
    expect(describePrincipal(session())).toBe('Student Seven · Student')
  })

  it('falls back to the email when there is no display name', () => {
    const named = session()
    expect(describePrincipal(session({ principal: { ...named.principal, display_name: null } }))).toBe(
      'student7@school.example · Student',
    )
  })

  it('says out loud when the authenticator is a stand-in', () => {
    const note = describeAuthenticator(session())
    expect(note).toContain('development credential mock')
    expect(note).toContain('local-credentials@1.0.0')
    expect(note).toContain('not the platform')
  })

  it('has nothing to say with no session', () => {
    expect(describeAuthenticator(null)).toBeNull()
  })
})
