import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LoginPage from './LoginPage'
import { ApiError, bootstrapAdministrator, login, logout, type SessionIssuance } from '../api/client'
import { clearSession, readSession, writeSession } from './session'
import { INSTITUTION } from '../test/fixtures'

// The page is orchestration over `/auth/*`; what the endpoints do is covered by
// the backend tests, so the client is mocked.
vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return { ...actual, bootstrapAdministrator: vi.fn(), login: vi.fn(), logout: vi.fn() }
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
    // The shortcut is a *teacher*, and joining is the student's own action, so it
    // can never join — the page says so rather than offering a button that fails.
    expect(screen.getByText(/cannot join one/i)).toBeTruthy()
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

    expect(screen.getByText(/Student Seven · Student/)).toBeTruthy()
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

  // -- the first administrator (V0-022) ----------------------------------------------

  it('creates the institution’s first administrator and fills in its code for signing in', async () => {
    const user = userEvent.setup()
    vi.mocked(bootstrapAdministrator).mockResolvedValue({
      created: true,
      account: {
        account_id: 'account-root',
        institution_id: INSTITUTION,
        email: 'root@school.example',
        display_name: 'Root',
        role: 'institution_admin',
        scopes: ['account:read', 'account:write', 'class:read', 'content:read'],
        status: 'ACTIVE',
        created_at: '2026-10-16T09:00:00Z',
      },
      development_credential: 'admin-code-1',
      sessions_revoked: 0,
    })
    render(<LoginPage />)

    await user.type(await screen.findByLabelText('Administrator email'), 'root@school.example')
    await user.click(screen.getByRole('button', { name: 'Create the first administrator' }))

    await waitFor(() =>
      expect(bootstrapAdministrator).toHaveBeenCalledWith(INSTITUTION, 'root@school.example'),
    )
    // The one-time code is shown once, and the sign-in form is ready to use it: the
    // point of the panel is to get the operator to a session.
    expect(await screen.findByText(/code is filled in above/)).toBeTruthy()
    expect((screen.getByLabelText('Sign-in code') as HTMLInputElement).value).toBe('admin-code-1')
    expect((screen.getByLabelText('Email') as HTMLInputElement).value).toBe(
      'root@school.example',
    )
  })

  it('says the bootstrap is closed when the institution already has an administrator', async () => {
    const user = userEvent.setup()
    vi.mocked(bootstrapAdministrator).mockRejectedValue(
      new ApiError('CONFLICT', 'already provisioned', 'TENANT_ALREADY_PROVISIONED'),
    )
    render(<LoginPage />)

    await user.type(await screen.findByLabelText('Administrator email'), 'root@school.example')
    await user.click(screen.getByRole('button', { name: 'Create the first administrator' }))

    const banner = await screen.findByText(/already has an administrator/)
    expect(banner.textContent).toMatch(/Sign in with that account/)
  })

  it('says a hardened deployment provisions administrators elsewhere', async () => {
    const user = userEvent.setup()
    vi.mocked(bootstrapAdministrator).mockRejectedValue(
      new ApiError('NOT_FOUND', 'not exposed', 'BOOTSTRAP_DISABLED'),
    )
    render(<LoginPage />)

    await user.type(await screen.findByLabelText('Administrator email'), 'root@school.example')
    await user.click(screen.getByRole('button', { name: 'Create the first administrator' }))

    // Institutional federation owns that account, so the page points at the operator
    // rather than pretending the route is merely denied.
    expect(await screen.findByText(/does not expose the first-administrator/)).toBeTruthy()
  })

  it('hides the bootstrap once a session exists', () => {
    writeSession({
      token: 'tok-1',
      principal: ISSUANCE.principal,
      authenticator: ISSUANCE.authenticator,
      notice: ISSUANCE.notice,
      expiresAt: ISSUANCE.expires_at,
    })
    render(<LoginPage />)

    expect(screen.queryByLabelText('Administrator email')).toBeNull()
  })
})
