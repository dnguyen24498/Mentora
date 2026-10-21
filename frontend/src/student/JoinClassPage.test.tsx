import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import JoinClassPage from './JoinClassPage'
import {
  ApiError,
  issueBootstrapToken,
  loadClass,
  type ClassView,
} from '../api/client'
import { clearSession, writeSession } from '../auth/session'
import { INSTITUTION } from '../test/fixtures'

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return { ...actual, issueBootstrapToken: vi.fn(), loadClass: vi.fn() }
})

const CLASS_VIEW: ClassView = {
  class: {
    class_id: 'class-1',
    institution_id: INSTITUTION,
    course_id: 'course-1',
    title: 'Period 3',
    version_id: null,
    scheduled_for: null,
    state: 'ACTIVE',
    created_at: '2026-10-16T09:00:00Z',
    started_at: '2026-10-16T09:05:00Z',
  },
  session: null,
  session_plan: null,
}

const TOKEN = {
  token: 'join-token-1',
  class_id: 'class-1',
  session_id: 'session-1',
  student_id: 'account-7',
  actor_epoch: 1,
  nonce: 'nonce-1',
  scopes: ['subscribe'],
  issued_at: '2026-10-16T09:06:00Z',
  expires_at: '2026-10-16T09:21:00Z',
}

function signInAsStudent() {
  writeSession({
    token: 'tok-1',
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
    notice: 'mock',
    expiresAt: new Date(Date.now() + 3_600_000).toISOString(),
  })
}

describe('JoinClassPage', () => {
  beforeEach(() => {
    localStorage.clear()
    clearSession()
    vi.clearAllMocks()
    vi.mocked(loadClass).mockResolvedValue(CLASS_VIEW)
    window.history.replaceState({}, '', '/join/class-1')
  })

  it('shows the class it is about', async () => {
    render(<JoinClassPage classId="class-1" />)

    expect(screen.getByRole('heading', { level: 1, name: 'Join a class' })).toBeTruthy()
    // The title is in the class panel and in the header's qualifier, so it
    // legitimately appears more than once.
    expect((await screen.findAllByText('Period 3')).length).toBeGreaterThan(0)
    expect(screen.getByText('Live')).toBeTruthy()
  })

  it('shows an ended class as locked and keeps Join disabled', async () => {
    signInAsStudent()
    vi.mocked(loadClass).mockResolvedValue({
      ...CLASS_VIEW,
      class: { ...CLASS_VIEW.class, state: 'COMPLETED' },
    })

    render(<JoinClassPage classId="class-1" />)

    expect(await screen.findByText('Ended')).toBeTruthy()
    const button = await screen.findByRole('button', { name: 'Class ended' })
    expect((button as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText(/locked until your teacher reopens/i)).toBeTruthy()
    expect(issueBootstrapToken).not.toHaveBeenCalled()
  })

  it('asks a signed-out visitor to sign in, and says development mode cannot join', async () => {
    render(<JoinClassPage classId="class-1" />)

    expect(await screen.findByRole('heading', { name: 'Sign in to join' })).toBeTruthy()
    expect(screen.getByText(/bound to/i)).toBeTruthy()
    // The sign-in link remembers where to come back to. The header carries a
    // plain "Sign in" chip too, so the panel's is the one with `next`.
    const signInLinks = screen.getAllByRole('link', { name: 'Sign in' })
    expect(signInLinks.map((link) => link.getAttribute('href'))).toContain(
      '/login?next=%2Fjoin%2Fclass-1',
    )
    // No join button while unsigned: it could only fail.
    expect(screen.queryByRole('button', { name: 'Join class' })).toBeNull()
  })

  it('joins and goes to the class in the classroom hub', async () => {
    const user = userEvent.setup()
    signInAsStudent()
    vi.mocked(issueBootstrapToken).mockResolvedValue(TOKEN)
    render(<JoinClassPage classId="class-1" />)

    await user.click(await screen.findByRole('button', { name: 'Join class' }))

    await waitFor(() => expect(issueBootstrapToken).toHaveBeenCalledWith('class-1'))
    await waitFor(() => expect(window.location.pathname).toBe('/classroom/class-1'))
  })

  it('reports a refusal with its precise reason', async () => {
    const user = userEvent.setup()
    signInAsStudent()
    vi.mocked(issueBootstrapToken).mockRejectedValue(
      new ApiError('NOT_ENROLLED', 'not on the roster'),
    )
    render(<JoinClassPage classId="class-1" />)

    await user.click(await screen.findByRole('button', { name: 'Join class' }))

    expect(await screen.findByText(/NOT_ENROLLED/)).toBeTruthy()
    // The student stays on the page rather than entering a class they cannot join.
    expect(window.location.pathname).toBe('/join/class-1')
  })

  it('reports a class that has not started as not ready, not as a failure', async () => {
    const user = userEvent.setup()
    signInAsStudent()
    vi.mocked(issueBootstrapToken).mockRejectedValue(
      new ApiError('CLASS_NOT_READY', 'the class has not started', 'NOT_STARTED'),
    )
    render(<JoinClassPage classId="class-1" />)

    await user.click(await screen.findByRole('button', { name: 'Join class' }))

    expect(await screen.findByText(/CLASS_NOT_READY/)).toBeTruthy()
    expect(screen.getByText(/NOT_STARTED/)).toBeTruthy()
  })

  it('tells a teacher that joining is a student capability', async () => {
    writeSession({
      token: 'tok-1',
      principal: {
        authenticated: true,
        institution_id: INSTITUTION,
        role: 'teacher',
        // A teacher's set has no `join`: only students join.
        scopes: ['class:read', 'class:write', 'scene:read'],
        account_id: 'account-1',
        email: 'teacher@school.example',
        display_name: null,
        session_id: 'session-2',
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
    render(<JoinClassPage classId="class-1" />)

    expect(await screen.findByText(/cannot request a class join/i)).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Join class' })).toBeNull()
  })

  it('waits for the teacher instead of offering a join the server would refuse', async () => {
    signInAsStudent()
    vi.mocked(loadClass).mockResolvedValue({
      ...CLASS_VIEW,
      class: { ...CLASS_VIEW.class, state: 'SCHEDULED', started_at: null },
    })
    render(<JoinClassPage classId="class-1" />)

    const waiting = await screen.findByRole('button', { name: 'Waiting for your teacher' })
    expect(waiting.getAttribute('disabled')).not.toBeNull()
    expect(screen.getByText(/only your teacher can start/i)).toBeTruthy()
    // Nothing was asked of the server: the class is not running.
    expect(issueBootstrapToken).not.toHaveBeenCalled()
  })

  it('reports a class that cannot be read at all', async () => {
    vi.mocked(loadClass).mockRejectedValue(new ApiError('NOT_FOUND', 'unknown class'))
    render(<JoinClassPage classId="class-1" />)

    expect(await screen.findByText(/NOT_FOUND/)).toBeTruthy()
  })
})
