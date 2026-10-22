import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StudentClassPage from './StudentClassPage'
import {
  ApiError,
  classSceneUrl,
  issueBootstrapToken,
  loadClass,
  loadClassScenes,
  loadSnapshot,
  openNarrationRelay,
  type ClassSceneList,
  type ClassView,
} from '../api/client'
import { clearSession, writeSession } from '../auth/session'
import type { AudioSink } from '../audio/useNarrationPlayer'
import { makeSnapshot } from '../classroom/state/testing'
import { INSTITUTION } from '../test/fixtures'

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    classSceneUrl: vi.fn(),
    issueBootstrapToken: vi.fn(),
    loadClass: vi.fn(),
    loadClassScenes: vi.fn(),
    loadSnapshot: vi.fn(),
    openNarrationRelay: vi.fn(),
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

const ACTIVE: ClassView = {
  class: {
    class_id: 'class-1',
    institution_id: INSTITUTION,
    course_id: 'course-1',
    title: 'Biology 101',
    version_id: null,
    scheduled_for: null,
    state: 'ACTIVE',
    created_at: '2026-10-16T09:00:00Z',
    started_at: '2026-10-16T09:05:00Z',
  },
  session: null,
  session_plan: null,
}

function classIn(state: string): ClassView {
  return { ...ACTIVE, class: { ...ACTIVE.class, state } }
}

const WAV_B64 = btoa('RIFF....WAVEfmt ')

/** A completed generation as the teacher's relay would hand it to a student. */
function relayResponse(): Response {
  const base = {
    class_id: 'class-1',
    session_id: 'session-1',
    scene_id: 'ppt/slides/slide1.xml',
    actor_epoch: 1,
    state_version: 1,
    generation: 77,
  }
  const events: object[] = [
    {
      ...base,
      sequence: 1,
      type: 'narration.started',
      source: 'slide-text',
      chunk_count: 1,
      word_count: 1,
      voice_id: 'neutral',
      provider: { name: 'omnivoice', version: '0.1.0-prototype' },
      empty: false,
    },
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
      type: 'narration.completed',
      status: 'COMPLETED',
      duration_ms: 100,
      fallback: false,
    },
  ]
  return new Response(events.map((event) => JSON.stringify(event)).join('\n') + '\n')
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
    vi.mocked(loadClass).mockResolvedValue(ACTIVE)
    vi.mocked(issueBootstrapToken).mockResolvedValue(TOKEN)
    vi.mocked(loadClassScenes).mockResolvedValue(LISTING)
    vi.mocked(loadSnapshot).mockResolvedValue(makeSnapshot())
    vi.mocked(classSceneUrl).mockImplementation(async (_classId, order) => `blob:slide-${order}`)
    vi.mocked(openNarrationRelay).mockResolvedValue(new Response(null, { status: 204 }))
    window.history.replaceState({}, '', '/student/class-1')
  })

  it('opens on the slide the teacher is presenting, not slide one', async () => {
    vi.mocked(loadSnapshot).mockResolvedValue(
      makeSnapshot({ sceneId: 'ppt/slides/slide2.xml', sectionIndex: 1 }),
    )
    render(<StudentClassPage classId="class-1" />)

    // The join still happens first: the credential is the participant's, and the
    // server checks the same roster on every read.
    await waitFor(() => expect(issueBootstrapToken).toHaveBeenCalledWith('class-1'))
    const slide = await screen.findByRole('img', { name: 'Slide 2' })
    expect(slide.getAttribute('src')).toBe('blob:slide-1')
    expect(screen.getByTestId('student-slide-counter').textContent).toContain('Slide 2 / 3')
    expect(screen.getByText('Slide 2 body')).toBeTruthy()
  })

  it('has no slide navigation at all — not buttons, not a picker, not arrow keys', async () => {
    vi.mocked(loadSnapshot).mockResolvedValue(
      makeSnapshot({ sceneId: 'ppt/slides/slide2.xml', sectionIndex: 1 }),
    )
    render(<StudentClassPage classId="class-1" />)
    await screen.findByRole('img', { name: 'Slide 2' })

    expect(screen.queryByRole('button', { name: /previous/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /next/i })).toBeNull()
    expect(screen.queryByRole('combobox')).toBeNull()
    expect(screen.queryByLabelText('Slide')).toBeNull()

    fireEvent.keyDown(window, { key: 'ArrowRight' })
    fireEvent.keyDown(window, { key: 'PageDown' })
    expect(screen.getByRole('img', { name: 'Slide 2' })).toBeTruthy()
    expect(screen.getByTestId('student-slide-counter').textContent).toContain('Slide 2 / 3')
  })

  it('follows the teacher when the authoritative snapshot moves', async () => {
    vi.mocked(loadSnapshot)
      .mockResolvedValueOnce(makeSnapshot())
      .mockResolvedValue(
        makeSnapshot({ sceneId: 'ppt/slides/slide2.xml', sectionIndex: 1, sequence: 2 }),
      )

    render(<StudentClassPage classId="class-1" followPollMs={25} />)
    await screen.findByRole('img', { name: 'Slide 1' })

    const followed = await screen.findByRole('img', { name: 'Slide 2' })
    expect(followed.getAttribute('src')).toBe('blob:slide-1')
    expect(screen.getByTestId('student-slide-counter').textContent).toContain('Slide 2 / 3')
    await waitFor(() => expect(classSceneUrl).toHaveBeenCalledWith('class-1', 1))
  })

  it('waits for the teacher to start, then joins by itself', async () => {
    vi.mocked(loadClass)
      .mockResolvedValueOnce(classIn('SCHEDULED'))
      .mockResolvedValue(ACTIVE)

    render(<StudentClassPage classId="class-1" followPollMs={30} />)

    expect(await screen.findByText(/has not started yet/i)).toBeTruthy()
    expect(screen.queryByRole('img')).toBeNull()
    await waitFor(() => expect(issueBootstrapToken).toHaveBeenCalledWith('class-1'))
    expect(await screen.findByRole('img', { name: 'Slide 1' })).toBeTruthy()
  })

  it('locks an ended class instead of showing its last slide', async () => {
    vi.mocked(loadClass).mockResolvedValue(classIn('COMPLETED'))

    render(<StudentClassPage classId="class-1" followPollMs={30} />)

    expect(await screen.findByText(/lesson is locked until your teacher reopens it/i)).toBeTruthy()
    // The ended class shows no lesson content at all: no slide, no text, no
    // counter. The server refuses a student's snapshot/scenes reads with
    // CLASS_ENDED, so the page does not even ask for them.
    expect(screen.queryByRole('img')).toBeNull()
    expect(screen.queryByTestId('student-slide-counter')).toBeNull()
    expect(loadClassScenes).not.toHaveBeenCalled()
    expect(loadSnapshot).not.toHaveBeenCalled()
    expect(issueBootstrapToken).not.toHaveBeenCalled()
  })

  it('joins by itself when an ended class is reopened', async () => {
    vi.mocked(loadClass)
      .mockResolvedValueOnce(classIn('COMPLETED'))
      .mockResolvedValue(ACTIVE)

    render(<StudentClassPage classId="class-1" followPollMs={25} />)

    expect(await screen.findByText(/lesson is locked until your teacher reopens it/i)).toBeTruthy()
    // The metadata poll notices the reopen and joins the new epoch.
    expect(await screen.findByRole('img', { name: 'Slide 1' })).toBeTruthy()
    expect(issueBootstrapToken).toHaveBeenCalledWith('class-1')
    expect(screen.getByTestId('student-slide-counter').textContent).toContain('Slide 1 / 3')
  })

  it('locks the lesson when the teacher ends a running class', async () => {
    vi.mocked(loadClass).mockResolvedValueOnce(ACTIVE).mockResolvedValue(classIn('COMPLETED'))
    vi.mocked(loadSnapshot)
      .mockResolvedValueOnce(makeSnapshot())
      .mockResolvedValue(makeSnapshot({ state: 'COMPLETED', sequence: 2 }))

    render(<StudentClassPage classId="class-1" followPollMs={25} />)

    expect(await screen.findByRole('img', { name: 'Slide 1' })).toBeTruthy()
    expect(await screen.findByText(/lesson is locked until your teacher reopens it/i)).toBeTruthy()
    expect(screen.queryByRole('img')).toBeNull()
    expect(screen.queryByTestId('student-slide-counter')).toBeNull()
  })

  it('says why a join was refused, and points back at the join page', async () => {
    vi.mocked(loadClass).mockRejectedValue(
      new ApiError('NOT_ENROLLED', 'this account is not enrolled in this class', 'NOT_ENROLLED'),
    )
    render(<StudentClassPage classId="class-1" />)

    expect(await screen.findByText(/NOT_ENROLLED/)).toBeTruthy()
    expect(screen.getByRole('link', { name: /open the join page/i }).getAttribute('href')).toBe(
      '/join/class-1',
    )
    // Nothing was read from the package: an unauthorized student reads no content.
    expect(loadClassScenes).not.toHaveBeenCalled()
    expect(issueBootstrapToken).not.toHaveBeenCalled()
  })

  it('surfaces a slide that cannot be read rather than showing a blank frame', async () => {
    vi.mocked(classSceneUrl).mockRejectedValue(
      new ApiError('STORAGE_FAILURE', 'a pinned file no longer matches', 'SCENE_CHECKSUM_MISMATCH'),
    )
    render(<StudentClassPage classId="class-1" />)

    expect(await screen.findByText(/SCENE_CHECKSUM_MISMATCH/)).toBeTruthy()
    expect(screen.getByText(/cannot be shown/i)).toBeTruthy()
  })

  it('reports the slides it loaded once; polling does not re-read the package', async () => {
    render(<StudentClassPage classId="class-1" followPollMs={20} />)

    await screen.findByRole('img', { name: 'Slide 1' })
    // Let the snapshot poll run at least once (waitFor keeps React updates inside act).
    await waitFor(() =>
      expect(vi.mocked(loadSnapshot).mock.calls.length).toBeGreaterThanOrEqual(2),
    )
    expect(loadClassScenes).toHaveBeenCalledTimes(1)
  })

  it('does not show a transcript by default; the slide text is a collapsed disclosure', async () => {
    render(<StudentClassPage classId="class-1" />)
    await screen.findByRole('img', { name: 'Slide 1' })

    const details = screen.getByTestId('student-slide-text') as HTMLDetailsElement
    expect(details.open).toBe(false)
    expect(screen.queryByRole('heading', { name: /in text/i })).toBeNull()
    expect(screen.getByTestId('student-voice-note').textContent).toMatch(/relayed to this page/i)
  })

  it('plays the teacher\'s live relayed voice and names the prototype provider', async () => {
    vi.mocked(openNarrationRelay)
      .mockResolvedValueOnce(relayResponse())
      .mockResolvedValue(new Response(null, { status: 204 }))
    const played: Blob[] = []
    const sink: AudioSink = {
      play: async (blob) => {
        played.push(blob)
      },
      stop: () => undefined,
    }

    render(
      <StudentClassPage
        classId="class-1"
        narrationRetryMs={20}
        createAudioSink={() => sink}
      />,
    )

    await screen.findByRole('img', { name: 'Slide 1' })
    await waitFor(() => expect(played).toHaveLength(1))
    expect(played[0].type).toBe('audio/wav')
    expect(screen.getByTestId('student-voice').textContent).toContain('OmniVoice')
    expect(openNarrationRelay).toHaveBeenCalledWith(
      'class-1',
      expect.objectContaining({
        signal: expect.anything(),
        expectedSceneId: 'ppt/slides/slide1.xml',
      }),
    )
    // After consuming the completed generation, the page waits with that exact
    // generation so the same slide is not replayed in a loop.
    await waitFor(() =>
      expect(openNarrationRelay).toHaveBeenCalledWith(
        'class-1',
        expect.objectContaining({
          afterGeneration: 77,
          expectedSceneId: 'ppt/slides/slide1.xml',
        }),
      ),
    )
  })

  it('asks for a click when the browser blocks the relayed voice', async () => {
    vi.mocked(openNarrationRelay)
      .mockResolvedValueOnce(relayResponse())
      .mockResolvedValue(new Response(null, { status: 204 }))
    const blocked = Object.assign(new Error('blocked'), { name: 'NotAllowedError' })

    render(
      <StudentClassPage
        classId="class-1"
        narrationRetryMs={20}
        createAudioSink={() => ({
          play: () => Promise.reject(blocked),
          stop: () => undefined,
        })}
      />,
    )

    expect(await screen.findByRole('button', { name: 'Enable sound' })).toBeTruthy()
    expect(screen.getByTestId('student-voice').textContent).toMatch(/blocked sound/i)
  })
})
