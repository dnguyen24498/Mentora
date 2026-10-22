import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ClassroomPage from './ClassroomPage'
import {
  ApiError,
  classSceneUrl,
  loadClassScenes,
  loadPresentation,
  navigateClassScene,
  openNarrationRelay,
  type ClassCommandResult,
  type ClassSceneList,
  type PresentationStatus,
} from '../api/client'
import { clearSession, writeSession } from '../auth/session'
import { ScriptedTransport, TEST_CLASS, makeSnapshot } from './state/testing'
import { INSTITUTION } from '../test/fixtures'

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    classSceneUrl: vi.fn(),
    loadClassScenes: vi.fn(),
    loadPresentation: vi.fn(),
    navigateClassScene: vi.fn(),
    openNarrationRelay: vi.fn(),
  }
})

const PRESENTING: PresentationStatus = {
  class_id: TEST_CLASS,
  available: true,
  running: true,
  paused: false,
  at_end: false,
  scene_order: 0,
  scene_id: 'ppt/slides/slide1.xml',
  actor_epoch: 1,
  state_version: 2,
  issue_code: null,
  message: null,
}

const LISTING: ClassSceneList = {
  class_id: TEST_CLASS,
  package_id: 'pkg-abc',
  content_digest: 'sha256:sealed',
  scene_count: 2,
  scenes: [
    {
      order: 0,
      scene_id: 'ppt/slides/slide1.xml',
      fidelity: 'STRUCTURAL_RENDERED',
      notes: null,
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
  ],
}

function signInAsTeacher() {
  writeSession({
    token: 'tok-teacher',
    principal: {
      authenticated: true,
      institution_id: INSTITUTION,
      role: 'teacher',
      scopes: [
        'class:read',
        'class:write',
        'content:read',
        'content:write',
        'review:write',
        'publication:write',
        'enrollment:write',
        'scene:read',
      ],
      account_id: 'account-teacher',
      email: 'teacher@school.example',
      display_name: 'Teacher One',
      session_id: 'session-teacher',
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

function moved(): ClassCommandResult {
  return {
    result: {
      command_id: 'cmd-1',
      accepted: true,
      issue_code: null,
      state_version: 3,
      event_sequence: 3,
      duplicate: false,
      events: [],
    },
    session: null,
    snapshot: makeSnapshot({
      sceneId: 'ppt/slides/slide2.xml',
      sectionIndex: 1,
      sequence: 3,
      stateVersion: 3,
    }),
  }
}

describe('ClassroomPage — the teacher presents', () => {
  beforeEach(() => {
    localStorage.clear()
    clearSession()
    vi.clearAllMocks()
    signInAsTeacher()
    vi.mocked(loadClassScenes).mockResolvedValue(LISTING)
    vi.mocked(classSceneUrl).mockImplementation(async (_classId, order) => `blob:slide-${order}`)
    vi.mocked(loadPresentation).mockResolvedValue(PRESENTING)
    vi.mocked(navigateClassScene).mockResolvedValue(moved())
    vi.mocked(openNarrationRelay).mockResolvedValue(new Response(null, { status: 204 }))
    window.history.replaceState({}, '', `/classroom/${TEST_CLASS}`)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows the teacher stage and lets the teacher advance the pinned slide', async () => {
    const user = userEvent.setup()
    const transport = new ScriptedTransport({
      snapshot: makeSnapshot({
        sceneId: 'ppt/slides/slide1.xml',
        sectionIndex: 0,
        sequence: 2,
        stateVersion: 2,
      }),
    })
    render(<ClassroomPage classId={TEST_CLASS} createTransport={() => transport} />)

    const stage = await screen.findByTestId('teacher-stage')
    expect(stage).toBeTruthy()
    expect(await screen.findByRole('img', { name: 'Slide 1' })).toBeTruthy()
    // The teacher gets real slide controls; the runtime scene controls are hidden.
    expect(screen.getByRole('button', { name: /next slide/i })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Next scene' })).toBeNull()

    await user.click(screen.getByRole('button', { name: /next slide/i }))

    await waitFor(() =>
      expect(navigateClassScene).toHaveBeenCalledWith(
        TEST_CLASS,
        expect.objectContaining({ order: 1, expected_state_version: 2 }),
      ),
    )
    // Applying the returned snapshot moves the stage itself.
    expect(await screen.findByRole('img', { name: 'Slide 2' })).toBeTruthy()
    expect(screen.getByTestId('teacher-slide-counter').textContent).toBe('Slide 2 of 2')
  })

  it('follows the background presenter without being the clock', async () => {
    const transport = new ScriptedTransport({
      snapshot: makeSnapshot({
        sceneId: 'ppt/slides/slide1.xml',
        sectionIndex: 0,
        sequence: 2,
        stateVersion: 2,
      }),
    })
    render(<ClassroomPage classId={TEST_CLASS} createTransport={() => transport} />)
    await screen.findByRole('img', { name: 'Slide 1' })

    // The server presents and advances the class; this page only observes the
    // authoritative snapshot. Switch the scripted transport's position and let
    // the quiet poll (1.5 s) deliver it.
    transport.current = makeSnapshot({
      sceneId: 'ppt/slides/slide2.xml',
      sectionIndex: 1,
      sequence: 3,
      stateVersion: 3,
    })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 1_700))
    })

    expect(screen.getByRole('img', { name: 'Slide 2' })).toBeTruthy()
    expect(screen.getByTestId('teacher-slide-counter').textContent).toBe('Slide 2 of 2')
    // Following is a read: the page did not move the class itself.
    expect(navigateClassScene).not.toHaveBeenCalled()
  })

  it('reports a presentation refusal and resynchronises', async () => {
    vi.mocked(navigateClassScene).mockRejectedValue(
      new ApiError('CONFLICT', 'the class ended', 'INVALID_TRANSITION'),
    )
    const user = userEvent.setup()
    const transport = new ScriptedTransport({
      snapshot: makeSnapshot({
        sceneId: 'ppt/slides/slide1.xml',
        sectionIndex: 0,
        sequence: 2,
        stateVersion: 2,
      }),
    })
    render(<ClassroomPage classId={TEST_CLASS} createTransport={() => transport} />)
    await screen.findByRole('img', { name: 'Slide 1' })

    await user.click(screen.getByRole('button', { name: /next slide/i }))

    expect(await screen.findByText(/INVALID_TRANSITION/)).toBeTruthy()
    await waitFor(() => expect(transport.loadCount).toBeGreaterThan(1))
  })
})
