import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StudentClassPage from './StudentClassPage'
import {
  ApiError,
  classSceneUrl,
  issueBootstrapToken,
  loadClassScenes,
  type ClassSceneList,
} from '../api/client'
import { clearSession, writeSession } from '../auth/session'
import { INSTITUTION } from '../test/fixtures'

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    classSceneUrl: vi.fn(),
    issueBootstrapToken: vi.fn(),
    loadClassScenes: vi.fn(),
  }
})

const LISTING: ClassSceneList = {
  class_id: 'class-1',
  package_id: 'pkg-abc',
  content_digest: 'sha256:sealed',
  scene_count: 3,
  scenes: [
    {
      order: 0,
      scene_id: 'ppt/slides/slide1.xml',
      fidelity: 'STRUCTURAL_RENDERED',
      notes: 'Notes for slide 1',
      text: ['Slide 1 body'],
      warnings: [],
      object_count: 1,
      step_count: 1,
    },
    {
      order: 1,
      scene_id: 'ppt/slides/slide2.xml',
      fidelity: 'STRUCTURAL_RENDERED',
      notes: null,
      text: ['Slide 2 body'],
      warnings: [],
      object_count: 1,
      step_count: 1,
    },
    {
      order: 2,
      scene_id: 'ppt/slides/slide3.xml',
      fidelity: 'DEGRADED_RENDERED',
      notes: null,
      text: [],
      warnings: ['UNSUPPORTED_OBJECT:chart'],
      object_count: 1,
      step_count: 0,
    },
  ],
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

describe('StudentClassPage', () => {
  beforeEach(() => {
    localStorage.clear()
    clearSession()
    vi.clearAllMocks()
    signInAsStudent()
    vi.mocked(issueBootstrapToken).mockResolvedValue(TOKEN)
    vi.mocked(loadClassScenes).mockResolvedValue(LISTING)
    vi.mocked(classSceneUrl).mockImplementation(async (_classId, order) => `blob:slide-${order}`)
    window.history.replaceState({}, '', '/student/class-1')
  })

  it('joins on open and shows the first slide full-width', async () => {
    render(<StudentClassPage classId="class-1" />)

    // The credential is requested before the slides are read, so the read is
    // authorized by the join rather than the other way round.
    await waitFor(() => expect(issueBootstrapToken).toHaveBeenCalledWith('class-1'))
    await waitFor(() => expect(classSceneUrl).toHaveBeenCalledWith('class-1', 0))

    const slide = await screen.findByRole('img', { name: 'Slide 1' })
    expect(slide.getAttribute('src')).toBe('blob:slide-0')
    expect(screen.getByTestId('student-slide-counter').textContent).toBe('Slide 1 / 3')
  })

  it('navigates slides by button', async () => {
    const user = userEvent.setup()
    render(<StudentClassPage classId="class-1" />)
    await screen.findByRole('img', { name: 'Slide 1' })

    await user.click(screen.getByRole('button', { name: /Next/ }))

    await waitFor(() => expect(classSceneUrl).toHaveBeenCalledWith('class-1', 1))
    expect(screen.getByTestId('student-slide-counter').textContent).toBe('Slide 2 / 3')
    // Previous is live again; Next stays live until the last slide.
    expect((screen.getByRole('button', { name: /Previous/ }) as HTMLButtonElement).disabled).toBe(
      false,
    )
  })

  it('disables the ends of the deck rather than wrapping around', async () => {
    render(<StudentClassPage classId="class-1" />)
    await screen.findByRole('img', { name: 'Slide 1' })

    expect((screen.getByRole('button', { name: /Previous/ }) as HTMLButtonElement).disabled).toBe(
      true,
    )
    expect((screen.getByRole('button', { name: /Next/ }) as HTMLButtonElement).disabled).toBe(false)
  })

  it('shows the slide’s own text and notes, and says it is text only and not live', async () => {
    render(<StudentClassPage classId="class-1" />)
    await screen.findByRole('img', { name: 'Slide 1' })

    expect(screen.getByText('Slide 1 body')).toBeTruthy()
    expect(screen.getByText('Notes for slide 1')).toBeTruthy()
    // The page must not imply a model wrote it, or that it follows the teacher.
    expect(screen.getByRole('heading', { name: /in text/i })).toBeTruthy()
    expect(screen.getByText(/no model wrote it/i)).toBeTruthy()
    expect(screen.getByText(/not live/i)).toBeTruthy()
  })

  it('flags a degraded slide instead of hiding it', async () => {
    const user = userEvent.setup()
    render(<StudentClassPage classId="class-1" />)
    await screen.findByRole('img', { name: 'Slide 1' })

    await user.click(screen.getByRole('button', { name: /Next/ }))
    await user.click(screen.getByRole('button', { name: /Next/ }))

    expect(await screen.findByText('DEGRADED_RENDERED')).toBeTruthy()
    // A slide with no text of its own says so rather than showing nothing.
    expect(screen.getByText(/no text of its own/i)).toBeTruthy()
  })

  it('says why a join was refused, and points back at the join page', async () => {
    vi.mocked(issueBootstrapToken).mockRejectedValue(
      new ApiError('NOT_ENROLLED', 'this account is not enrolled in this class'),
    )
    render(<StudentClassPage classId="class-1" />)

    expect(await screen.findByText(/NOT_ENROLLED/)).toBeTruthy()
    expect(screen.getByRole('link', { name: /open the join page/i }).getAttribute('href')).toBe(
      '/join/class-1',
    )
    // Nothing was read from the package: an unauthorized join reads no content.
    expect(loadClassScenes).not.toHaveBeenCalled()
  })

  it('surfaces a slide that cannot be read rather than showing a blank frame', async () => {
    vi.mocked(classSceneUrl).mockRejectedValue(
      new ApiError('STORAGE_FAILURE', 'a pinned file no longer matches', 'SCENE_CHECKSUM_MISMATCH'),
    )
    render(<StudentClassPage classId="class-1" />)

    expect(await screen.findByText(/SCENE_CHECKSUM_MISMATCH/)).toBeTruthy()
  })

  it('reports the slides it loaded, not a re-render of them', async () => {
    render(<StudentClassPage classId="class-1" />)

    await screen.findByRole('img', { name: 'Slide 1' })
    // The list is read once; each slide's asset is fetched as it is shown.
    expect(loadClassScenes).toHaveBeenCalledTimes(1)
  })
})
