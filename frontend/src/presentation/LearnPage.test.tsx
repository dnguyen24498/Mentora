import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LearnPage from './LearnPage'
import {
  ApiError,
  buildReviewPackage,
  loadArtifact,
  loadReviewPackage,
  loadReviewState,
} from '../api/client'
import { ARTIFACT, INSTITUTION, makeArtifact, makePackage, makeState } from '../test/fixtures'

// The page's job is orchestration (which package it reads, which slide it shows),
// so the API client is mocked; the server behaviour is covered by backend tests.
vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    buildReviewPackage: vi.fn(),
    loadArtifact: vi.fn(),
    loadReviewPackage: vi.fn(),
    loadReviewState: vi.fn(),
  }
})

const PACKAGE = makePackage()

function primeStoredPackage() {
  vi.mocked(loadReviewPackage).mockResolvedValue(PACKAGE)
  vi.mocked(loadArtifact).mockResolvedValue(makeArtifact())
  vi.mocked(loadReviewState).mockResolvedValue(makeState())
  vi.mocked(buildReviewPackage).mockRejectedValue(new Error('must not rebuild a stored package'))
}

function renderLearn() {
  return render(<LearnPage artifactId={ARTIFACT} loadRender={async () => 'blob:slide'} />)
}

describe('LearnPage — the deck and the teaching canvas', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('shows the stored package without re-rendering it', async () => {
    primeStoredPackage()
    renderLearn()

    expect(await screen.findByTestId('learn-slide-counter')).toBeTruthy()
    expect(loadReviewPackage).toHaveBeenCalledWith(INSTITUTION, ARTIFACT)
    expect(buildReviewPackage).not.toHaveBeenCalled()
    // The header names the deck so a page opened in its own tab is identifiable.
    expect(await screen.findByText('revised-deck.pptx')).toBeTruthy()
  })

  it('shows the slide, the teaching canvas and that slide’s teaching script', async () => {
    primeStoredPackage()
    renderLearn()

    expect((await screen.findByTestId('learn-slide-counter')).textContent).toBe('Slide 1 / 2')
    // The learning surface is the slide plus the annotation layer over it.
    expect(screen.getByTestId('teaching-canvas')).toBeTruthy()
    expect(screen.getByRole('toolbar', { name: 'Teaching canvas tools' })).toBeTruthy()
    // The script panel is the slide's own extracted content.
    expect(screen.getByText('Notes for slide 1')).toBeTruthy()
    expect(screen.getByText('Slide 1 body')).toBeTruthy()
    expect(screen.getByText('Explain slide 1')).toBeTruthy()
  })

  it('moves through the deck with the buttons and with the arrow keys', async () => {
    const user = userEvent.setup()
    primeStoredPackage()
    renderLearn()

    await screen.findByTestId('learn-slide-counter')

    await user.click(screen.getByRole('button', { name: 'Next →' }))
    expect(screen.getByTestId('learn-slide-counter').textContent).toBe('Slide 2 / 2')
    expect(screen.getByText('Notes for slide 2')).toBeTruthy()
    // The second section has no script, and the page says so instead of blank.
    expect(screen.getByText(/No script for this section/)).toBeTruthy()

    await user.keyboard('{ArrowLeft}')
    expect(screen.getByTestId('learn-slide-counter').textContent).toBe('Slide 1 / 2')

    await user.keyboard('{ArrowRight}')
    expect(screen.getByTestId('learn-slide-counter').textContent).toBe('Slide 2 / 2')

    // The ends are ends: no slide before the first or after the last.
    await user.click(screen.getByRole('button', { name: 'Next →' }))
    expect(screen.getByTestId('learn-slide-counter').textContent).toBe('Slide 2 / 2')
  })

  it('jumps to a slide from the selector', async () => {
    const user = userEvent.setup()
    primeStoredPackage()
    renderLearn()

    await screen.findByTestId('learn-slide-counter')
    await user.selectOptions(screen.getByLabelText('Jump to slide'), '1')

    expect(screen.getByTestId('learn-slide-counter').textContent).toBe('Slide 2 / 2')
  })

  it('builds a package that was never built, and says it is rendering', async () => {
    vi.mocked(loadReviewPackage).mockRejectedValue(new ApiError('NOT_FOUND', 'nothing stored yet'))
    vi.mocked(buildReviewPackage).mockResolvedValue(PACKAGE)
    vi.mocked(loadArtifact).mockResolvedValue(makeArtifact())
    vi.mocked(loadReviewState).mockResolvedValue(makeState())

    renderLearn()

    expect(await screen.findByTestId('learn-slide-counter')).toBeTruthy()
    expect(buildReviewPackage).toHaveBeenCalledWith(INSTITUTION, ARTIFACT)
  })

  it('reports a deck it cannot load instead of showing an empty page', async () => {
    vi.mocked(loadReviewPackage).mockRejectedValue(new ApiError('FORBIDDEN', 'wrong institution'))
    vi.mocked(buildReviewPackage).mockRejectedValue(new ApiError('FORBIDDEN', 'wrong institution'))

    renderLearn()

    const alert = await screen.findByTestId('learn-error')
    expect(alert.textContent).toMatch(/FORBIDDEN/)
    expect(screen.queryByTestId('teaching-canvas')).toBeNull()
  })

  it('degrades the canvas instead of breaking when the browser has no 2D context', async () => {
    primeStoredPackage()
    renderLearn()

    await screen.findByTestId('learn-slide-counter')

    // jsdom has no 2D canvas (and neither does a locked-down webview): the slide
    // is still shown, the tools are disabled, and the page says why.
    await waitFor(() => expect(screen.getByTestId('canvas-unavailable')).toBeTruthy())
    expect(screen.getByRole('button', { name: 'Draw' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('button', { name: 'Pen' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('button', { name: 'Colour Red' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('button', { name: 'Undo' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('button', { name: 'Clear' }).hasAttribute('disabled')).toBe(true)
  })

  it('remembers the deck so the shared nav can leave and come back', async () => {
    primeStoredPackage()
    renderLearn()

    await screen.findByTestId('learn-slide-counter')
    expect(localStorage.getItem('mentora.artifact')).toBe(ARTIFACT)
  })
})

describe('LearnPage — automatic teaching (text only)', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('narrates the authored script, records a transcript, and ends at the last slide', async () => {
    primeStoredPackage()
    renderLearn()
    await screen.findByTestId('learn-slide-counter')

    // No audio is produced in this version, and the page says so.
    expect(screen.getByText(/no audio is produced/i)).toBeTruthy()

    vi.useFakeTimers()
    try {
      fireEvent.click(screen.getByTestId('learn-play'))

      // The slide's own authored script is the narration, not a model's text.
      expect(screen.getByTestId('learn-caption').textContent).toBe('Explain slide 1')
      expect(screen.getByText(/narration source: lesson-script/)).toBeTruthy()
      expect(screen.getByTestId('learn-transcript').textContent).toContain('Explain slide 1')

      // After the passage's dwell it moves on by itself.
      act(() => {
        vi.advanceTimersByTime(2600)
      })
      expect(screen.getByTestId('learn-slide-counter').textContent).toBe('Slide 2 / 2')
      // Section 2 has no script, so the slide's speaker notes carry it.
      expect(screen.getByTestId('learn-caption').textContent).toBe('Notes for slide 2')
      expect(screen.getByTestId('learn-transcript').textContent).toContain('Notes for slide 2')

      // The end is the end: narration stops rather than wrapping around.
      act(() => {
        vi.advanceTimersByTime(2600)
      })
      expect(screen.getByTestId('learn-finished')).toBeTruthy()
      expect(screen.getByTestId('learn-play').textContent).toBe('Play')
      expect(screen.getByTestId('learn-slide-counter').textContent).toBe('Slide 2 / 2')
    } finally {
      vi.useRealTimers()
    }
  })

  it('plays, pauses and stops', async () => {
    primeStoredPackage()
    renderLearn()
    await screen.findByTestId('learn-slide-counter')

    const play = screen.getByTestId('learn-play')
    expect(play.textContent).toBe('Play')
    expect(screen.queryByTestId('learn-caption')).toBeNull()

    fireEvent.click(play)
    expect(play.textContent).toBe('Pause')
    expect(screen.getByTestId('learn-caption')).toBeTruthy()
    expect(screen.getByTestId('learn-transcript')).toBeTruthy()

    fireEvent.click(play)
    expect(play.textContent).toBe('Play')
    // The caption belongs to the narration, so pausing removes it.
    expect(screen.queryByTestId('learn-caption')).toBeNull()
    // The transcript stays: it is the record of what was said.
    expect(screen.getByTestId('learn-transcript')).toBeTruthy()

    // Walk forward, then stop: stop rewinds and clears the record.
    fireEvent.click(screen.getByRole('button', { name: 'Next →' }))
    expect(screen.getByTestId('learn-slide-counter').textContent).toBe('Slide 2 / 2')

    fireEvent.click(screen.getByTestId('learn-stop'))
    expect(screen.getByTestId('learn-slide-counter').textContent).toBe('Slide 1 / 2')
    expect(screen.queryByTestId('learn-transcript')).toBeNull()
  })

  it('starts narrating on open when the teacher turned autoplay on', async () => {
    localStorage.setItem(
      'mentora.settings',
      JSON.stringify({ teachingAutoplay: true, teachingCaptions: true, teachingWpm: 160 }),
    )
    primeStoredPackage()
    renderLearn()

    await screen.findByTestId('learn-slide-counter')
    await waitFor(() => expect(screen.getByTestId('learn-play').textContent).toBe('Pause'))
    expect(localStorage.getItem('mentora.settings')).toContain('"teachingAutoplay":true')
  })

  it('hides the caption when the teacher turned captions off, keeping the transcript', async () => {
    localStorage.setItem(
      'mentora.settings',
      JSON.stringify({ teachingCaptions: false, teachingAutoplay: false, teachingWpm: 160 }),
    )
    primeStoredPackage()
    renderLearn()
    await screen.findByTestId('learn-slide-counter')

    fireEvent.click(screen.getByTestId('learn-play'))

    expect(screen.queryByTestId('learn-caption')).toBeNull()
    expect(screen.getByTestId('learn-transcript')).toBeTruthy()
  })

  it('paces the narration from the words-per-minute setting', async () => {
    localStorage.setItem('mentora.settings', JSON.stringify({ teachingWpm: 240 }))
    primeStoredPackage()
    renderLearn()
    await screen.findByTestId('learn-slide-counter')

    expect(screen.getByText(/per slide at 240 wpm/)).toBeTruthy()
  })

  it('narrates the teacher’s newest draft revision when there is one', async () => {
    primeStoredPackage()
    vi.mocked(loadReviewState).mockResolvedValue(
      makeState({
        draft: {
          draft_id: 'draft-1',
          artifact_id: ARTIFACT,
          version_id: 'version-1',
          package_id: 'pkg-abc',
          content_package_version: 'cpv-abc',
          lesson_plan_version: 'lp-abc',
          revision: 2,
          sections: [
            {
              order: 0,
              section_id: 'sec-1',
              type: 'EXPLANATION',
              scene_id: 'ppt/slides/slide1.xml',
              scene_step_id: 'ppt/slides/slide1.xml#step-0',
              safe_markers: [],
              script: 'My rewritten opening',
            },
          ],
          edited_by: 'teacher@example.edu',
          created_at: '2026-10-16T11:00:00Z',
        },
      }),
    )
    renderLearn()

    await screen.findByTestId('learn-slide-counter')
    fireEvent.click(screen.getByTestId('learn-play'))

    // The revision being written wins over the package's own script, and the
    // page labels it so it cannot be mistaken for published text.
    expect(screen.getByTestId('learn-caption').textContent).toBe('My rewritten opening')
    expect(screen.getByText(/narration source: draft-script/)).toBeTruthy()
    expect(screen.getByText(/revision 2/)).toBeTruthy()
  })

  it('falls back to the package when the review overlay cannot be read', async () => {
    primeStoredPackage()
    vi.mocked(loadReviewState).mockRejectedValue(new ApiError('NOT_FOUND', 'no package yet'))
    renderLearn()

    await screen.findByTestId('learn-slide-counter')
    fireEvent.click(screen.getByTestId('learn-play'))

    // A missing overlay is not a failure: the deck still teaches from the package.
    expect(screen.getByTestId('learn-caption').textContent).toBe('Explain slide 1')
    expect(screen.getByText(/narration source: lesson-script/)).toBeTruthy()
  })
})

