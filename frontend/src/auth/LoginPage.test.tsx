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

  it('says every page needs a sign-in, and that a password is what signs you in', () => {
    render(<LoginPage />)

    expect(screen.getByText(/every page needs a sign-in/i)).toBeTruthy()
    expect(screen.getByLabelText('Password')).toBeTruthy()
    // The old "development mode" affordance is gone: there is no way to skip a
    // sign-in from this page.
    expect(screen.queryByRole('link', { name: /development mode/i })).toBeNull()
  })

  it('signs in with a password, stores the session and reports who it is', async () => {
    const user = userEvent.setup()
    vi.mocked(login).mockResolvedValue(ISSUANCE)
    render(<LoginPage />)

    await user.type(screen.getByLabelText('Email'), 'student7@school.example')
    await user.type(screen.getByLabelText('Password'), 'dev-pass-7')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() =>
      expect(login).toHaveBeenCalledWith({
        institutionId: INSTITUTION,
        email: 'student7@school.example',
        password: 'dev-pass-7',
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
    await user.type(screen.getByLabelText('Password'), 'wrong')
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
    await user.type(screen.getByLabelText('Password'), 'dev-pass-7')
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
    await user.type(screen.getByLabelText('Password'), 'dev-pass-7')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(window.location.pathname).toBe('/join/class-1'))
  })

  it('refuses to be sent off-site by a hostile next parameter', async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, '', '/login?next=%2F%2Fevil.example')
    vi.mocked(login).mockResolvedValue(ISSUANCE)
    render(<LoginPage />)

    await user.type(screen.getByLabelText('Email'), 'student7@school.example')
    await user.type(screen.getByLabelText('Password'), 'dev-pass-7')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(window.location.pathname).toBe('/'))
  })

  // -- the first administrator (V0-022, V0-023) ---------------------------------------

  it('creates the institution’s first administrator with a password and fills in the form', async () => {
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
      credential_set: true,
      sessions_revoked: 0,
    })
    render(<LoginPage />)

    await user.type(await screen.findByLabelText('Administrator email'), 'root@school.example')
    await user.type(screen.getByLabelText('Administrator password'), 'admin-pass-1')
    await user.click(screen.getByRole('button', { name: 'Create the first administrator' }))

    await waitFor(() =>
      expect(bootstrapAdministrator).toHaveBeenCalledWith(
        INSTITUTION,
        'root@school.example',
        'admin-pass-1',
      ),
    )
    // The password the operator chose is filled into the sign-in form — no secret is
    // ever returned to display — so the next step is one click away.
    expect(await screen.findByText(/is now this institution's administrator/)).toBeTruthy()
    expect((screen.getByLabelText('Password') as HTMLInputElement).value).toBe('admin-pass-1')
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
    await user.type(screen.getByLabelText('Administrator password'), 'admin-pass-1')
    await user.click(screen.getByRole('button', { name: 'Create the first administrator' }))

    const banner = await screen.findByText(/already has an administrator/)
    expect(banner.textContent).toMatch(/Sign in with that account/)
  })

  it('says a deployment with the bootstrap off provisions administrators elsewhere', async () => {
    const user = userEvent.setup()
    vi.mocked(bootstrapAdministrator).mockRejectedValue(
      new ApiError('NOT_FOUND', 'not exposed', 'BOOTSTRAP_DISABLED'),
    )
    render(<LoginPage />)

    await user.type(await screen.findByLabelText('Administrator email'), 'root@school.example')
    await user.type(screen.getByLabelText('Administrator password'), 'admin-pass-1')
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
