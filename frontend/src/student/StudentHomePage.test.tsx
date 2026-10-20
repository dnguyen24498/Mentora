import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StudentHomePage from './StudentHomePage'
import { listClasses, type ClassSummary } from '../api/client'
import { clearSession, writeSession } from '../auth/session'
import { INSTITUTION } from '../test/fixtures'

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return { ...actual, listClasses: vi.fn() }
})

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

describe('StudentHomePage', () => {
  beforeEach(() => {
    localStorage.clear()
    clearSession()
    vi.clearAllMocks()
    window.history.replaceState({}, '', '/student')
  })

  it('lists only the classes the server returned, with a join link once running', async () => {
    signInAsStudent()
    vi.mocked(listClasses).mockResolvedValue([
      klass({ class_id: 'class-live', title: 'Live lesson', state: 'ACTIVE' }),
    ])

    render(<StudentHomePage />)

    expect(await screen.findByRole('heading', { level: 1, name: 'My classes' })).toBeTruthy()
    expect(await screen.findByText('Live lesson')).toBeTruthy()
    const join = screen.getByRole('link', { name: 'Join class' })
    expect(join.getAttribute('href')).toBe('/join/class-live')
  })

  it('says a scheduled class is waiting and offers no join link yet', async () => {
    signInAsStudent()
    vi.mocked(listClasses).mockResolvedValue([
      klass({ class_id: 'class-soon', title: 'Later today', state: 'SCHEDULED' }),
    ])

    render(<StudentHomePage />)

    expect(await screen.findByText('Later today')).toBeTruthy()
    expect(screen.getByText(/waiting for your teacher to start/i)).toBeTruthy()
    expect(screen.queryByRole('link', { name: 'Join class' })).toBeNull()
  })

  it('explains an empty roster rather than showing a blank page', async () => {
    signInAsStudent()
    vi.mocked(listClasses).mockResolvedValue([])

    render(<StudentHomePage />)

    expect(await screen.findByText(/No classes yet/i)).toBeTruthy()
    expect(screen.getByText(/teacher adds you to a class/i)).toBeTruthy()
  })

  it('reports a refusal from the class list', async () => {
    signInAsStudent()
    vi.mocked(listClasses).mockRejectedValue(new Error('network down'))

    render(<StudentHomePage />)

    expect(await screen.findByText(/network down/i)).toBeTruthy()
  })
})
