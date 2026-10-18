import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LearnPage from './LearnPage'
import { ApiError, buildReviewPackage, loadArtifact, loadReviewPackage } from '../api/client'
import { ARTIFACT, INSTITUTION, makeArtifact, makePackage } from '../test/fixtures'

// The page's job is orchestration (which package it reads, which slide it shows),
// so the API client is mocked; the server behaviour is covered by backend tests.
vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    buildReviewPackage: vi.fn(),
    loadArtifact: vi.fn(),
    loadReviewPackage: vi.fn(),
  }
})

const PACKAGE = makePackage()

function primeStoredPackage() {
  vi.mocked(loadReviewPackage).mockResolvedValue(PACKAGE)
  vi.mocked(loadArtifact).mockResolvedValue(makeArtifact())
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
