import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SettingsPage from './SettingsPage'
import { readSettings } from './store'
import {
  ApiError,
  changePassword,
  fetchObjectUrl,
  loadHealth,
  loadRendererStatus,
  type RendererStatus,
} from '../api/client'
import { clearSession, readSession, writeSession } from '../auth/session'

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    changePassword: vi.fn(),
    fetchObjectUrl: vi.fn(),
    loadHealth: vi.fn(),
    loadRendererStatus: vi.fn(),
  }
})

const STATUS: RendererStatus = {
  default_mode: 'faithful',
  mode: 'faithful',
  modes: [
    { mode: 'faithful', label: 'Faithful' },
    { mode: 'themed', label: 'Themed' },
  ],
  identity: {
    name: 'local-structural-svg',
    version: '3.1.0',
    engine: 'stdlib-svg',
    config_hash: 'hash',
    data_region: 'local-1',
  },
  support: { native_pptx: false },
  health: { state: 'closed', consecutive_failures: 0 },
  theme: null,
}

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
  vi.mocked(loadHealth).mockResolvedValue({ status: 'ok' })
  vi.mocked(loadRendererStatus).mockResolvedValue(STATUS)
  vi.mocked(fetchObjectUrl).mockResolvedValue('blob:slide')
})

describe('SettingsPage — general', () => {
  it('reports server facts it cannot change rather than offering inputs for them', async () => {
    render(<SettingsPage section="general" />)

    expect(await screen.findByText('local-structural-svg@3.1.0')).toBeTruthy()
    expect(screen.getByText('local-1')).toBeTruthy()
    // The home region is server configuration, and the page says so.
    expect(screen.getByText(/MENTORA_HOME_REGION/)).toBeTruthy()
    // The tenant, by contrast, is a real client input.
    fireEvent.change(screen.getByLabelText('Institution id'), {
      target: { value: 'college-9' },
    })
    expect(localStorage.getItem('mentora.institution')).toBe('college-9')
  })

  it('reports an unreachable API instead of failing silently', async () => {
    vi.mocked(loadHealth).mockRejectedValue(new Error('down'))
    render(<SettingsPage section="general" />)

    expect(await screen.findByText('unreachable')).toBeTruthy()
    expect(await screen.findByRole('alert')).toBeTruthy()
  })

  it('restores the defaults', async () => {
    const user = userEvent.setup()
    localStorage.setItem(
      'mentora.settings',
      JSON.stringify({ renderMode: 'themed', teachingWpm: 240, teachingAutoplay: true }),
    )
    render(<SettingsPage section="general" />)

    await user.click(await screen.findByRole('button', { name: 'Restore defaults' }))

    expect(readSettings().renderMode).toBe('faithful')
    expect(readSettings().teachingWpm).toBe(160)
  })
})

describe('SettingsPage — rendering', () => {
  it('persists the render mode and probes the renderer in that mode', async () => {
    const user = userEvent.setup()
    render(<SettingsPage section="rendering" />)

    await user.click(await screen.findByRole('radio', { name: /Themed/ }))

    expect(readSettings().renderMode).toBe('themed')
    await waitFor(() =>
      expect(loadRendererStatus).toHaveBeenCalledWith('university-001', 'themed'),
    )
    // No renderer technology is accepted yet; the page says so instead of
    // presenting the choice as settled.
    expect(screen.getByText(/DEC-TECH-005/)).toBeTruthy()
  })

  it('says a packaged render cannot be re-moded', async () => {
    render(<SettingsPage section="rendering" />)
    expect(await screen.findByText(/pinned at build time/)).toBeTruthy()
  })
})

describe('SettingsPage — teaching', () => {
  it('persists the pacing and says the narration is text only', async () => {
    render(<SettingsPage section="teaching" />)

    const slider = await screen.findByLabelText(/words per minute/)
    fireEvent.change(slider, { target: { value: '240' } })

    expect(readSettings().teachingWpm).toBe(240)
    expect(screen.getByText('Text only.')).toBeTruthy()
    expect(screen.getByText(/no model/)).toBeTruthy()
  })

  it('persists the playback toggles', async () => {
    const user = userEvent.setup()
    render(<SettingsPage section="teaching" />)

    await user.click(
      await screen.findByRole('checkbox', { name: /Start narrating when a deck opens/ }),
    )
    expect(readSettings().teachingAutoplay).toBe(true)

    await user.click(screen.getByRole('checkbox', { name: /Show the caption line/ }))
    expect(readSettings().teachingCaptions).toBe(false)
  })

  it('persists the scheduled-class auto-start and says it is client-local', async () => {
    const user = userEvent.setup()
    render(<SettingsPage section="teaching" />)

    await user.click(
      await screen.findByRole('checkbox', {
        name: /Start a scheduled class when its time arrives/,
      }),
    )
    expect(readSettings().autoStartDueClasses).toBe(true)
    // An automatic start needs a durable scheduler, which is not decided yet, so
    // the page says the open page does it instead of implying a server timer.
    expect(screen.getByText(/Nothing runs with the page closed/)).toBeTruthy()
    // The open decision is named where the preference is set and again in the
    // summary, so both are expected.
    expect(screen.getAllByText(/DEC-TECH-003/).length).toBeGreaterThan(0)
  })
})

describe('SettingsPage — accessibility', () => {
  it('edits the classroom’s own preferences rather than a second copy', async () => {
    const user = userEvent.setup()
    render(<SettingsPage section="accessibility" />)

    await user.click(await screen.findByRole('checkbox', { name: /Reduce motion/ }))

    // The classroom store owns the key; the settings page is a second way in.
    expect(JSON.parse(localStorage.getItem('mentora.classroom.prefs') ?? '{}')).toMatchObject({
      reducedMotion: true,
    })
  })
})

/**
 * Security settings are the signed-in account changing its *own* password
 * (V0-023). The current password is verified exactly as a sign-in is, so a
 * mistyped field is not a sign-out, and the server revokes the account's other
 * live sessions while keeping the caller's.
 */
describe('SettingsPage — security', () => {
  beforeEach(() => {
    clearSession()
    writeSession({
      token: 'tok-1',
      principal: {
        authenticated: true,
        institution_id: 'university-001',
        role: 'teacher',
        scopes: ['content:read', 'content:write', 'class:read', 'class:write', 'scene:read'],
        account_id: 'account-teacher',
        email: 'teacher@school.example',
        display_name: 'Tess Teacher',
        session_id: 'session-1',
      },
      authenticator: {
        id: 'local-credentials@1.0.0',
        name: 'local-credentials',
        version: '1.0.0',
        kind: 'DEVELOPMENT_MOCK',
      },
      notice: 'mock',
      expiresAt: new Date(Date.now() + 3_600_000).toISOString(),
    })
  })

  it('changes the signed-in account’s password and revokes the others', async () => {
    const user = userEvent.setup()
    vi.mocked(changePassword).mockResolvedValue({ changed: true, sessions_revoked: 2 })
    render(<SettingsPage section="security" />)

    await user.type(await screen.findByLabelText('Current password'), 'old-pass-1')
    await user.type(screen.getByLabelText('New password'), 'new-pass-2')
    await user.type(screen.getByLabelText('Confirm new password'), 'new-pass-2')
    await user.click(screen.getByRole('button', { name: 'Change password' }))

    await waitFor(() => expect(changePassword).toHaveBeenCalledWith('old-pass-1', 'new-pass-2'))
    expect(await screen.findByText(/2 other live session/)).toBeTruthy()
    // The fields are cleared, and the caller is still signed in.
    expect((screen.getByLabelText('Current password') as HTMLInputElement).value).toBe('')
    expect(readSession()?.token).toBe('tok-1')
  })

  it('refuses a mismatch before it troubles the server', async () => {
    const user = userEvent.setup()
    render(<SettingsPage section="security" />)

    await user.type(await screen.findByLabelText('Current password'), 'old-pass-1')
    await user.type(screen.getByLabelText('New password'), 'new-pass-2')
    await user.type(screen.getByLabelText('Confirm new password'), 'new-pass-3')

    const submit = screen.getByRole('button', { name: 'Change password' })
    expect((submit as HTMLButtonElement).disabled).toBe(true)
    await user.click(submit)
    expect(changePassword).not.toHaveBeenCalled()
    expect(screen.getByText(/do not match/)).toBeTruthy()
  })

  it('keeps the session when the current password is wrong', async () => {
    const user = userEvent.setup()
    vi.mocked(changePassword).mockRejectedValue(
      new ApiError('AUTHENTICATION_FAILED', 'credentials were not accepted', 'INVALID_CREDENTIALS'),
    )
    render(<SettingsPage section="security" />)

    await user.type(await screen.findByLabelText('Current password'), 'wrong')
    await user.type(screen.getByLabelText('New password'), 'new-pass-2')
    await user.type(screen.getByLabelText('Confirm new password'), 'new-pass-2')
    await user.click(screen.getByRole('button', { name: 'Change password' }))

    // A mistyped field is not a sign-out: the refusal names the cause and the
    // session stands.
    expect(await screen.findByText(/INVALID_CREDENTIALS/)).toBeTruthy()
    expect(readSession()?.token).toBe('tok-1')
  })

  it('says the credential mechanism is not a decided technology', () => {
    render(<SettingsPage section="security" />)

    expect(screen.getByText(/not a decided technology/)).toBeTruthy()
    expect(screen.getByText(/institutional federation/)).toBeTruthy()
  })
})
