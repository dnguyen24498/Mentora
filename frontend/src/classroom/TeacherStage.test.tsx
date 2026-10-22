import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import TeacherStage from './TeacherStage'
import {
  ApiError,
  classSceneUrl,
  endClass,
  loadClassScenes,
  loadPresentation,
  navigateClassScene,
  openNarrationRelay,
  pausePresentation,
  reopenClass,
  resumePresentation,
  type ClassCommandResult,
  type ClassSceneList,
  type PresentationStatus,
} from '../api/client'
import { makeSnapshot } from './state/testing'
import type { AudioSink } from '../audio/useNarrationPlayer'

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    classSceneUrl: vi.fn(),
    endClass: vi.fn(),
    loadClassScenes: vi.fn(),
    loadPresentation: vi.fn(),
    navigateClassScene: vi.fn(),
    openNarrationRelay: vi.fn(),
    pausePresentation: vi.fn(),
    reopenClass: vi.fn(),
    resumePresentation: vi.fn(),
  }
})

const WAV_B64 = btoa('RIFF....WAVEfmt ')

function narrationResponse(status: 'COMPLETED' | 'FALLBACK'): Response {
  const base = {
    class_id: 'class-1',
    scene_id: 'ppt/slides/slide1.xml',
    actor_epoch: 1,
    state_version: 1,
    generation: 7,
  }
  const events: object[] = [
    {
      ...base,
      sequence: 1,
      type: 'narration.started',
      provider: { name: 'neutral-deterministic' },
      empty: false,
    },
  ]
  if (status === 'COMPLETED') {
    events.push(
      {
        ...base,
        sequence: 2,
        type: 'audio',
        chunk_index: 0,
        content_type: 'audio/wav',
        duration_ms: 100,
        data: WAV_B64,
      },
      {
        ...base,
        sequence: 3,
        type: 'audio',
        chunk_index: 1,
        content_type: 'audio/wav',
        duration_ms: 100,
        data: WAV_B64,
      },
      {
        ...base,
        sequence: 4,
        type: 'narration.completed',
        status: 'COMPLETED',
        duration_ms: 200,
        fallback: false,
      },
    )
  } else {
    events.push(
      {
        ...base,
        sequence: 2,
        type: 'segment.fallback',
        chunk_index: 0,
        text: 'Spoken words',
        reason: 'SYNTHESIS_FAILED',
      },
      {
        ...base,
        sequence: 3,
        type: 'narration.completed',
        status: 'FALLBACK',
        duration_ms: 0,
        fallback: true,
      },
    )
  }
  return new Response(events.map((event) => JSON.stringify(event)).join('\n') + '\n')
}

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

const PRESENTING: PresentationStatus = {
  class_id: 'class-1',
  available: true,
  running: true,
  paused: false,
  at_end: false,
  scene_order: 0,
  scene_id: 'ppt/slides/slide1.xml',
  actor_epoch: 1,
  state_version: 1,
  issue_code: null,
  message: null,
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

function lifecycleResult(
  state: 'ACTIVE' | 'COMPLETED',
  sequence: number,
  sceneId = 'ppt/slides/slide1.xml',
  sectionIndex = 0,
): ClassCommandResult {
  return {
    result: {
      command_id: `cmd-${state.toLowerCase()}`,
      accepted: true,
      issue_code: null,
      state_version: sequence,
      event_sequence: sequence,
      duplicate: false,
      events: [],
    },
    session: null,
    snapshot: makeSnapshot({ state, sceneId, sectionIndex, sequence }),
  }
}

describe('TeacherStage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(loadClassScenes).mockResolvedValue(LISTING)
    vi.mocked(classSceneUrl).mockImplementation(async (_classId, order) => `blob:slide-${order}`)
    vi.mocked(loadPresentation).mockResolvedValue(PRESENTING)
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
    expect(await screen.findByText('Auto-presenting')).toBeTruthy()

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
    expect(loadPresentation).not.toHaveBeenCalled()
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
    expect(screen.getByRole('button', { name: 'Reopen class' })).toBeTruthy()
  })

  it('ends the class and applies the completed snapshot', async () => {
    const user = userEvent.setup()
    const onSnapshot = vi.fn()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.mocked(endClass).mockResolvedValue(
      lifecycleResult('COMPLETED', 2, 'ppt/slides/slide3.xml', 2),
    )

    render(
      <TeacherStage
        classId="class-1"
        sessionState="ACTIVE"
        currentSceneId="ppt/slides/slide3.xml"
        currentSectionIndex={2}
        stateVersion={1}
        onSnapshot={onSnapshot}
        onResync={vi.fn()}
      />,
    )
    await screen.findByRole('img', { name: 'Slide 3' })

    await user.click(screen.getByRole('button', { name: 'End class' }))

    await waitFor(() =>
      expect(endClass).toHaveBeenCalledWith(
        'class-1',
        expect.objectContaining({
          expected_state_version: 1,
          command_id: expect.any(String),
        }),
      ),
    )
    expect(onSnapshot).toHaveBeenCalledWith(
      expect.objectContaining({
        document: expect.objectContaining({ state: 'COMPLETED' }),
      }),
    )
    expect(confirm).toHaveBeenCalled()
    confirm.mockRestore()
  })

  it('reopens an ended class and applies the new first-slide snapshot', async () => {
    const user = userEvent.setup()
    const onSnapshot = vi.fn()
    vi.mocked(reopenClass).mockResolvedValue(lifecycleResult('ACTIVE', 3))

    render(
      <TeacherStage
        classId="class-1"
        sessionState="COMPLETED"
        currentSceneId="ppt/slides/slide3.xml"
        currentSectionIndex={2}
        stateVersion={2}
        onSnapshot={onSnapshot}
        onResync={vi.fn()}
      />,
    )
    await screen.findByRole('img', { name: 'Slide 3' })

    await user.click(screen.getByRole('button', { name: 'Reopen class' }))

    await waitFor(() =>
      expect(reopenClass).toHaveBeenCalledWith(
        'class-1',
        expect.objectContaining({
          expected_state_version: 2,
          command_id: expect.any(String),
        }),
      ),
    )
    expect(onSnapshot).toHaveBeenCalledWith(
      expect.objectContaining({
        document: expect.objectContaining({
          state: 'ACTIVE',
          lesson: expect.objectContaining({ section_index: 0 }),
        }),
      }),
    )
  })

  describe('background presentation (V0-028)', () => {
    afterEach(() => {
      vi.useRealTimers()
    })

    it('follows the class server instead of moving the slides itself', async () => {
      vi.useFakeTimers()
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
      await act(async () => {
        await vi.advanceTimersByTimeAsync(60_000)
      })

      expect(navigateClassScene).not.toHaveBeenCalled()
      expect(screen.getByTestId('presentation-status').textContent).toBe('Auto-presenting')
    })

    it('pauses and resumes the class-level presentation', async () => {
      const user = userEvent.setup()
      vi.mocked(pausePresentation).mockResolvedValue({
        ...PRESENTING,
        paused: true,
      })
      vi.mocked(resumePresentation).mockResolvedValue(PRESENTING)

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
      await screen.findByTestId('presentation-status')

      await user.click(await screen.findByRole('button', { name: 'Pause' }))
      expect(pausePresentation).toHaveBeenCalledWith('class-1')
      expect(await screen.findByText('Paused')).toBeTruthy()

      await user.click(screen.getByRole('button', { name: 'Resume' }))
      expect(resumePresentation).toHaveBeenCalledWith('class-1')
      expect(await screen.findByText('Auto-presenting')).toBeTruthy()
    })

    it('offers to start the presenter again after an API restart', async () => {
      const user = userEvent.setup()
      vi.mocked(loadPresentation).mockResolvedValue({
        ...PRESENTING,
        running: false,
        scene_order: null,
      })
      vi.mocked(resumePresentation).mockResolvedValue(PRESENTING)

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

      expect(await screen.findByText('Not presenting')).toBeTruthy()
      await user.click(screen.getByRole('button', { name: 'Start presentation' }))
      expect(resumePresentation).toHaveBeenCalledWith('class-1')
      expect(await screen.findByText('Auto-presenting')).toBeTruthy()
    })

    it('holds at the last slide and stops offering Pause', async () => {
      vi.mocked(loadPresentation).mockResolvedValue({
        ...PRESENTING,
        scene_order: 2,
        at_end: true,
      })

      render(
        <TeacherStage
          classId="class-1"
          sessionState="ACTIVE"
          currentSceneId="ppt/slides/slide3.xml"
          currentSectionIndex={2}
          stateVersion={3}
          onSnapshot={vi.fn()}
          onResync={vi.fn()}
        />,
      )

      expect(await screen.findByText('At the last slide')).toBeTruthy()
      expect(screen.queryByRole('button', { name: 'Pause' })).toBeNull()
    })

    it('plays the server relay without starting another synthesis', async () => {
      vi.mocked(openNarrationRelay)
        .mockResolvedValueOnce(narrationResponse('COMPLETED'))
        .mockResolvedValue(new Response(null, { status: 204 }))
      const played: Blob[] = []
      const sink = (): AudioSink => ({
        play: async (blob) => void played.push(blob),
        stop: () => {},
      })

      render(
        <TeacherStage
          classId="class-1"
          sessionState="ACTIVE"
          currentSceneId="ppt/slides/slide1.xml"
          currentSectionIndex={0}
          stateVersion={1}
          onSnapshot={vi.fn()}
          onResync={vi.fn()}
          createAudioSink={sink}
        />,
      )

      await waitFor(() => expect(played).toHaveLength(2))
      expect(played[0].type).toBe('audio/wav')
      expect(openNarrationRelay).toHaveBeenCalledWith(
        'class-1',
        expect.objectContaining({ expectedSceneId: 'ppt/slides/slide1.xml' }),
      )
      // The teacher's page never asks the API to synthesize a second generation.
      expect(navigateClassScene).not.toHaveBeenCalled()
    })

    it('asks for a click when the browser blocks relayed sound', async () => {
      vi.mocked(openNarrationRelay)
        .mockResolvedValueOnce(narrationResponse('COMPLETED'))
        .mockResolvedValue(new Response(null, { status: 204 }))
      const blocked = Object.assign(new Error('blocked'), { name: 'NotAllowedError' })

      render(
        <TeacherStage
          classId="class-1"
          sessionState="ACTIVE"
          currentSceneId="ppt/slides/slide1.xml"
          currentSectionIndex={0}
          stateVersion={1}
          onSnapshot={vi.fn()}
          onResync={vi.fn()}
          createAudioSink={() => ({ play: () => Promise.reject(blocked), stop: () => {} })}
        />,
      )

      expect(await screen.findByRole('button', { name: 'Enable sound' })).toBeTruthy()
      expect(navigateClassScene).not.toHaveBeenCalled()
    })

    it('shows the relayed script when speech falls back', async () => {
      vi.mocked(openNarrationRelay)
        .mockResolvedValueOnce(narrationResponse('FALLBACK'))
        .mockResolvedValue(new Response(null, { status: 204 }))

      render(
        <TeacherStage
          classId="class-1"
          sessionState="ACTIVE"
          currentSceneId="ppt/slides/slide1.xml"
          currentSectionIndex={0}
          stateVersion={1}
          onSnapshot={vi.fn()}
          onResync={vi.fn()}
          createAudioSink={() => ({ play: async () => {}, stop: () => {} })}
        />,
      )

      expect(await screen.findByTestId('teacher-voice-fallback')).toBeTruthy()
      expect(screen.getByTestId('teacher-voice-fallback').textContent).toContain('Spoken words')
      expect(navigateClassScene).not.toHaveBeenCalled()
    })
  })
})
