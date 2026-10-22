import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ClassroomHomePage from './ClassroomHomePage'
import { listClasses, reopenClass, startClass, type ClassSummary } from '../api/client'
import { clearSession, writeSession } from '../auth/session'
import { INSTITUTION } from '../test/fixtures'

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return { ...actual, listClasses: vi.fn(), reopenClass: vi.fn(), startClass: vi.fn() }
})

function signIn(role: 'teacher' | 'student' | 'institution_admin') {
  writeSession({
    token: 'tok-1',
    principal: {
      authenticated: true,
      institution_id: INSTITUTION,
      role,
      scopes:
        role === 'student'
          ? ['class:read', 'scene:read', 'join']
          : role === 'institution_admin'
            ? ['account:read', 'account:write', 'content:read', 'class:read']
            : [
                'account:read',
                'class:read',
                'class:write',
                'content:read',
                'content:write',
                'enrollment:write',
                'publication:write',
                'review:write',
                'scene:read',
              ],
      account_id: `account-${role}`,
      email: `${role}@school.example`,
      display_name: role === 'student' ? 'Student Seven' : 'Tess Teacher',
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

function klass(overrides: Partial<ClassSummary>): ClassSummary {
  return {
    class_id: 'class-1',
    institution_id: INSTITUTION,
    course_id: 'course-1',
    title: 'Period 3',
    version_id: null,
    scheduled_for: null,
    state: 'SCHEDULED',
    created_at: '2026-10-16T09:00:00Z',
    started_at: null,
    ...overrides,
  }
}

describe('ClassroomHomePage (V0-026)', () => {
  beforeEach(() => {
    localStorage.clear()
    clearSession()
    vi.clearAllMocks()
    window.history.replaceState({}, '', '/classroom')
  })

  it('starts a scheduled class in the background and refreshes the list', async () => {
    signIn('teacher')
    vi.mocked(listClasses).mockResolvedValue([
      klass({ class_id: 'class-soon', title: 'Later today' }),
    ])
    vi.mocked(startClass).mockResolvedValue({
      class: {
        class_id: 'class-soon',
        institution_id: INSTITUTION,
        course_id: 'course-1',
        title: 'Later today',
        version_id: null,
        scheduled_for: null,
        state: 'ACTIVE',
        created_at: '2026-10-16T09:00:00Z',
        started_at: '2026-10-16T09:05:00Z',
      },
      session: null,
      session_plan: null,
      created: true,
    })

    const user = userEvent.setup()
    render(<ClassroomHomePage />)

    expect(await screen.findByText('Later today')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Start class' }))

    await waitFor(() => expect(startClass).toHaveBeenCalledWith(INSTITUTION, 'class-soon'))
    // The server runs the presentation; starting refreshes the hub instead of
    // navigating to a page that would have to stay open.
    await waitFor(() => expect(listClasses).toHaveBeenCalledTimes(2))
    expect(`${window.location.pathname}${window.location.search}`).toBe('/classroom')
  })

  it('offers a teacher the running class in the hub', async () => {
    signIn('teacher')
    vi.mocked(listClasses).mockResolvedValue([
      klass({ class_id: 'class-live', title: 'Live lesson', state: 'ACTIVE' }),
    ])

    render(<ClassroomHomePage />)

    const open = await screen.findByRole('link', { name: 'Open classroom' })
    expect(open.getAttribute('href')).toBe('/classroom/class-live')
    // A running class has nothing to start.
    expect(screen.queryByRole('button', { name: 'Start class' })).toBeNull()
  })

  it('gives a student a join link only once their class is running', async () => {
    signIn('student')
    vi.mocked(listClasses).mockResolvedValue([
      klass({ class_id: 'class-live', title: 'Live lesson', state: 'ACTIVE' }),
      klass({ class_id: 'class-soon', title: 'Later today', state: 'SCHEDULED' }),
    ])

    render(<ClassroomHomePage />)

    const join = await screen.findByRole('link', { name: 'Join class' })
    expect(join.getAttribute('href')).toBe('/classroom/class-live')
    expect(screen.getByText(/waiting for your teacher to start/i)).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Start class' })).toBeNull()
  })

  it('shows an institution administrator the schedule without a lesson link', async () => {
    signIn('institution_admin')
    vi.mocked(listClasses).mockResolvedValue([
      klass({ class_id: 'class-live', title: 'Live lesson', state: 'ACTIVE' }),
    ])

    render(<ClassroomHomePage />)

    expect(await screen.findByText('Live lesson')).toBeTruthy()
    // Oversight is not authorship: the administrator holds `class:read` but not
    // `scene:read`, so there is no join/open link and no start button.
    expect(screen.queryByRole('link', { name: /join class|open classroom/i })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Start class' })).toBeNull()
  })

  it('puts Refresh in the app bar actions, not in a stray second row', async () => {
    signIn('teacher')
    vi.mocked(listClasses).mockResolvedValue([])

    render(<ClassroomHomePage />)

    const refresh = await screen.findByRole('button', { name: 'Refresh' })
    // The actions slot is the tenant group: the page action belongs beside the
    // institution field, as on every other page — not under the header.
    const actions = refresh.parentElement
    expect(actions?.contains(screen.getByLabelText('Institution'))).toBe(true)
  })

  it('explains an empty roster rather than showing a blank page', async () => {
    signIn('student')
    vi.mocked(listClasses).mockResolvedValue([])

    render(<ClassroomHomePage />)

    expect(await screen.findByText(/No classes yet/i)).toBeTruthy()
    expect(screen.getByText(/teacher adds you to a class/i)).toBeTruthy()
  })

  it('reports a start refusal on the class rather than pretending it started', async () => {
    signIn('teacher')
    vi.mocked(listClasses).mockResolvedValue([
      klass({ class_id: 'class-soon', title: 'Later today' }),
    ])
    vi.mocked(startClass).mockRejectedValue(new Error('VERSION_NOT_PUBLISHED'))

    const user = userEvent.setup()
    render(<ClassroomHomePage />)

    await screen.findByText('Later today')
    await user.click(screen.getByRole('button', { name: 'Start class' }))

    expect(await screen.findByText(/VERSION_NOT_PUBLISHED/)).toBeTruthy()
    expect(window.location.pathname).toBe('/classroom')
  })

  it('shows an ended class as Ended and lets a teacher reopen the same class', async () => {
    signIn('teacher')
    vi.mocked(listClasses).mockResolvedValue([
      klass({ class_id: 'class-done', title: 'Yesterday', state: 'COMPLETED' }),
    ])
    vi.mocked(reopenClass).mockResolvedValue({
      result: {
        command_id: 'cmd-reopen',
        accepted: true,
        issue_code: null,
        state_version: 7,
        event_sequence: 7,
        duplicate: false,
        events: [],
      },
      session: null,
      snapshot: null,
    })

    const user = userEvent.setup()
    render(<ClassroomHomePage />)

    expect(await screen.findByText('Ended')).toBeTruthy()
    expect(screen.getByText(/students are locked out/i)).toBeTruthy()
    // An ended class cannot be started; it is reopened.
    expect(screen.queryByRole('button', { name: 'Start class' })).toBeNull()

    await user.click(screen.getByRole('button', { name: 'Reopen class' }))

    await waitFor(() => expect(reopenClass).toHaveBeenCalledWith('class-done'))
    await waitFor(() => expect(listClasses).toHaveBeenCalledTimes(2))
    expect(`${window.location.pathname}${window.location.search}`).toBe('/classroom')
  })

  it('locks an ended class for a student: Ended, no lesson link, no slide', async () => {
    signIn('student')
    vi.mocked(listClasses).mockResolvedValue([
      klass({ class_id: 'class-done', title: 'Yesterday', state: 'COMPLETED' }),
    ])

    render(<ClassroomHomePage />)

    expect(await screen.findByText('Ended')).toBeTruthy()
    expect(screen.getByText(/locked until your teacher reopens it/i)).toBeTruthy()
    expect(screen.queryByRole('link', { name: /last slide|join class|open classroom/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /reopen|start class/i })).toBeNull()
  })
})
