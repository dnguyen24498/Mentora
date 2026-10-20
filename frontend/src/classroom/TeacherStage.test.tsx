import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TeacherStage from './TeacherStage'
import {
  ApiError,
  classSceneUrl,
  loadClassScenes,
  navigateClassScene,
  type ClassCommandResult,
  type ClassSceneList,
} from '../api/client'
import { makeSnapshot } from './state/testing'

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    classSceneUrl: vi.fn(),
    loadClassScenes: vi.fn(),
    navigateClassScene: vi.fn(),
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
    {
      order: 2,
      scene_id: 'ppt/slides/slide3.xml',
      fidelity: 'STRUCTURAL_RENDERED',
      notes: null,
      text: ['Slide 3 body'],
      warnings: [],
      object_count: 1,
      step_count: 1,
    },
  ],
}

function movedToSlideThree(): ClassCommandResult {
  return {
    result: {
      command_id: 'cmd-1',
      accepted: true,
      issue_code: null,
      state_version: 2,
      event_sequence: 2,
      duplicate: false,
      events: [],
    },
    session: null,
    snapshot: makeSnapshot({
      sceneId: 'ppt/slides/slide3.xml',
      sectionIndex: 2,
      sequence: 2,
    }),
  }
}

describe('TeacherStage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(loadClassScenes).mockResolvedValue(LISTING)
    vi.mocked(classSceneUrl).mockImplementation(async (_classId, order) => `blob:slide-${order}`)
    vi.mocked(navigateClassScene).mockResolvedValue(movedToSlideThree())
  })

  it('shows the pinned slide the class is on and advances it', async () => {
    const user = userEvent.setup()
    const onSnapshot = vi.fn()
    const onResync = vi.fn()
    render(
      <TeacherStage
        classId="class-1"
        sessionState="ACTIVE"
        currentSceneId="ppt/slides/slide2.xml"
        currentSectionIndex={1}
        stateVersion={1}
        onSnapshot={onSnapshot}
        onResync={onResync}
      />,
    )

    const slide = await screen.findByRole('img', { name: 'Slide 2' })
    expect(slide.getAttribute('src')).toBe('blob:slide-1')
    expect(screen.getByTestId('teacher-slide-counter').textContent).toBe('Slide 2 of 3')

    await user.click(screen.getByRole('button', { name: /next slide/i }))

    await waitFor(() =>
      expect(navigateClassScene).toHaveBeenCalledWith(
        'class-1',
        expect.objectContaining({
          order: 2,
          expected_state_version: 1,
          command_id: expect.any(String),
        }),
      ),
    )
    expect(onSnapshot).toHaveBeenCalledWith(
      expect.objectContaining({ state_version: 2, document: expect.anything() }),
    )
    expect(onResync).not.toHaveBeenCalled()
  })

  it('jumps to a chosen slide', async () => {
    const user = userEvent.setup()
    render(
      <TeacherStage
        classId="class-1"
        sessionState="ACTIVE"
        currentSceneId="ppt/slides/slide1.xml"
        currentSectionIndex={0}
        stateVersion={1}
        onSnapshot={vi.fn()}
        onResync={vi.fn()}
      />,
    )
    await screen.findByRole('img', { name: 'Slide 1' })

    await user.selectOptions(screen.getByLabelText('Slide'), '2')

    await waitFor(() =>
      expect(navigateClassScene).toHaveBeenCalledWith(
        'class-1',
        expect.objectContaining({ order: 2, expected_state_version: 1 }),
      ),
    )
  })

  it('reports a stale command and asks the page to resynchronise', async () => {
    vi.mocked(navigateClassScene).mockRejectedValue(
      new ApiError('CONFLICT', 'this view is behind the class', 'STALE_STATE_VERSION'),
    )
    const user = userEvent.setup()
    const onResync = vi.fn()
    render(
      <TeacherStage
        classId="class-1"
        sessionState="ACTIVE"
        currentSceneId="ppt/slides/slide1.xml"
        currentSectionIndex={0}
        stateVersion={1}
        onSnapshot={vi.fn()}
        onResync={onResync}
      />,
    )
    await screen.findByRole('img', { name: 'Slide 1' })

    await user.click(screen.getByRole('button', { name: /next slide/i }))

    expect(await screen.findByText(/STALE_STATE_VERSION/)).toBeTruthy()
    expect(onResync).toHaveBeenCalled()
  })

  it('does not offer slides before the class starts', async () => {
    render(
      <TeacherStage
        classId="class-1"
        sessionState={null}
        currentSceneId={null}
        currentSectionIndex={null}
        stateVersion={0}
        onSnapshot={vi.fn()}
        onResync={vi.fn()}
      />,
    )

    expect(screen.getByText(/has not started/i)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /slide/i })).toBeNull()
    expect(loadClassScenes).not.toHaveBeenCalled()
  })

  it('keeps the last slide visible after the class ends, without controls', async () => {
    render(
      <TeacherStage
        classId="class-1"
        sessionState="COMPLETED"
        currentSceneId="ppt/slides/slide3.xml"
        currentSectionIndex={2}
        stateVersion={2}
        onSnapshot={vi.fn()}
        onResync={vi.fn()}
      />,
    )

    expect(await screen.findByRole('img', { name: 'Slide 3' })).toBeTruthy()
    expect(screen.getByText(/class has ended/i)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /previous slide|next slide/i })).toBeNull()
  })
})
