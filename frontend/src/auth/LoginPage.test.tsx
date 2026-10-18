import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LoginPage from './LoginPage'
import { ApiError, login, logout, type SessionIssuance } from '../api/client'
import { clearSession, readSession, writeSession } from './session'
import { INSTITUTION } from '../test/fixtures'

// The page is orchestration over `/auth/*`; what the endpoints do is covered by
// the backend tests, so the client is mocked.
vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return { ...actual, login: vi.fn(), logout: vi.fn() }
})

const ISSUANCE: SessionIssuance = {
  authenticated: true,
  token: 'tok-1',
  token_type: 'Bearer',
  expires_at: new Date(Date.now() + 3_600_000).toISOString(),
  principal: {
    authenticated: true,
    institution_id: INSTITUTION,
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
}

describe('LoginPage', () => {
  beforeEach(() => {
    localStorage.clear()
    clearSession()
    vi.clearAllMocks()
    window.history.replaceState({}, '', '/login')
  })

  it('says the credential mechanism is not a decided technology', () => {
    render(<LoginPage />)

    expect(screen.getByRole('heading', { level: 1, name: 'Sign in' })).toBeTruthy()
    expect(screen.getByText(/not a decided technology/i)).toBeTruthy()
    expect(screen.getByText(/institutional federation/i)).toBeTruthy()
  })

  it('names development mode as not a sign-in, and cannot join a class', () => {
    render(<LoginPage />)

    expect(screen.getByText(/development shortcut/i)).toBeTruthy()
    // The shortcut has no account, so it can never join — the page says so
    // rather than offering a button that can only fail.
    expect(screen.getByText(/cannot join a class/i)).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Continue in development mode' })).toBeTruthy()
  })

  it('signs in, stores the session and reports who it is', async () => {
    const user = userEvent.setup()
    vi.mocked(login).mockResolvedValue(ISSUANCE)
    render(<LoginPage />)

    await user.type(screen.getByLabelText('Email'), 'student7@school.example')
    await user.type(screen.getByLabelText('Sign-in code'), 'dev-code-7')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() =>
      expect(login).toHaveBeenCalledWith({
        institutionId: INSTITUTION,
        email: 'student7@school.example',
        credential: 'dev-code-7',
      }),
    )
    // The store holds the session, and only the token is what gets sent.
    expect(readSession()?.token).toBe('tok-1')
    expect(await screen.findByText(/Student Seven/)).toBeTruthy()
  })

  it('reports a refusal by its stable code, never as a generic failure', async () => {
    const user = userEvent.setup()
    vi.mocked(login).mockRejectedValue(
      new ApiError('AUTHENTICATION_FAILED', 'credentials were not accepted', 'INVALID_CREDENTIALS'),
    )
    render(<LoginPage />)

    await user.type(screen.getByLabelText('Email'), 'student7@school.example')
    await user.type(screen.getByLabelText('Sign-in code'), 'wrong')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText(/AUTHENTICATION_FAILED/)).toBeTruthy()
    // No session was stored on a refusal.
    expect(readSession()).toBeNull()
  })

  it('distinguishes an unavailable capability from a denial', async () => {
    const user = userEvent.setup()
    vi.mocked(login).mockRejectedValue(
      new ApiError('AUTHENTICATION_UNAVAILABLE', 'the capability is unreachable', null),
    )
    render(<LoginPage />)

    await user.type(screen.getByLabelText('Email'), 'student7@school.example')
    await user.type(screen.getByLabelText('Sign-in code'), 'dev-code-7')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    // Not "wrong credentials": the account may be perfectly valid.
    expect(await screen.findByText(/AUTHENTICATION_UNAVAILABLE/)).toBeTruthy()
  })

  it('shows the signed-in principal and signs out', async () => {
    const user = userEvent.setup()
    writeSession({
      token: 'tok-1',
      principal: ISSUANCE.principal,
      authenticator: ISSUANCE.authenticator,
      notice: ISSUANCE.notice,
      expiresAt: ISSUANCE.expires_at,
    })
    vi.mocked(logout).mockResolvedValue({ revoked: true })
    render(<LoginPage />)

    expect(screen.getByText(/Student Seven · student/)).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Sign out' }))

    await waitFor(() => expect(readSession()).toBeNull())
  })

  it('signs the browser out locally even when the server cannot be reached', async () => {
    const user = userEvent.setup()
    writeSession({
      token: 'tok-1',
      principal: ISSUANCE.principal,
      authenticator: ISSUANCE.authenticator,
      notice: ISSUANCE.notice,
      expiresAt: ISSUANCE.expires_at,
    })
    // A dead backend must not leave the browser looking signed in.
    vi.mocked(logout).mockRejectedValue(new ApiError('BACKEND_UNAVAILABLE', 'down'))
    render(<LoginPage />)

    await user.click(screen.getByRole('button', { name: 'Sign out' }))
    await waitFor(() => expect(readSession()).toBeNull())
  })

  it('returns to the page that asked for a sign-in', async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, '', '/login?next=%2Fjoin%2Fclass-1')
    vi.mocked(login).mockResolvedValue(ISSUANCE)
    render(<LoginPage />)

    await user.type(screen.getByLabelText('Email'), 'student7@school.example')
    await user.type(screen.getByLabelText('Sign-in code'), 'dev-code-7')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(window.location.pathname).toBe('/join/class-1'))
  })

  it('refuses to be sent off-site by a hostile next parameter', async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, '', '/login?next=%2F%2Fevil.example')
    vi.mocked(login).mockResolvedValue(ISSUANCE)
    render(<LoginPage />)

    await user.type(screen.getByLabelText('Email'), 'student7@school.example')
    await user.type(screen.getByLabelText('Sign-in code'), 'dev-code-7')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(window.location.pathname).toBe('/'))
  })
})
