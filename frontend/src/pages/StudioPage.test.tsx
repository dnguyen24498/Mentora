import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StudioPage from './StudioPage'
import {
  ApiError,
  buildReviewPackage,
  loadArtifact,
  loadReviewPackage,
  loadReviewState,
  postReviewDecision,
  saveReviewDraft,
  type ReviewPackage,
} from '../api/client'
import { ARTIFACT, INSTITUTION, makeArtifact, makePackage, makeState } from '../test/fixtures'

// The page's job is *orchestration* (what it asks the API for and in what order),
// so the client is mocked; the server behaviour is covered by the backend tests.
vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    buildReviewPackage: vi.fn(),
    loadArtifact: vi.fn(),
    loadReviewPackage: vi.fn(),
    loadReviewState: vi.fn(),
    postReviewDecision: vi.fn(),
    saveReviewDraft: vi.fn(),
  }
})

const PACKAGE = makePackage()
const STATE = makeState()

/** The happy path: a package is already built, so opening the page must not render. */
function primeStoredPackage() {
  vi.mocked(loadReviewPackage).mockResolvedValue(PACKAGE)
  vi.mocked(loadReviewState).mockResolvedValue(STATE)
  vi.mocked(loadArtifact).mockResolvedValue(makeArtifact())
  vi.mocked(buildReviewPackage).mockRejectedValue(new Error('must not rebuild a stored package'))
}

function renderStudio() {
  return render(<StudioPage artifactId={ARTIFACT} loadRender={async () => 'blob:slide'} />)
}

describe('StudioPage — loading the reviewed package', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('shows the stored package without re-rendering it', async () => {
    primeStoredPackage()
    renderStudio()

    expect(await screen.findByTestId('teacher-studio')).toBeTruthy()
    expect(loadReviewPackage).toHaveBeenCalledWith(INSTITUTION, ARTIFACT)
    expect(buildReviewPackage).not.toHaveBeenCalled()
    // The header names the deck, so a page opened in its own tab is identifiable.
    expect(await screen.findByText('revised-deck.pptx')).toBeTruthy()
    expect((await screen.findByTestId('studio-notice')).textContent).toMatch(/no re-render/)
  })

  it('builds a package that was never built, and says it is rendering', async () => {
    let finishBuild: (value: ReviewPackage) => void = () => {}
    vi.mocked(loadReviewPackage).mockRejectedValue(new ApiError('NOT_FOUND', 'nothing stored yet'))
    vi.mocked(buildReviewPackage).mockReturnValue(
      new Promise<ReviewPackage>((resolve) => {
        finishBuild = resolve
      }),
    )
    vi.mocked(loadReviewState).mockResolvedValue(STATE)
    vi.mocked(loadArtifact).mockResolvedValue(makeArtifact())

    renderStudio()

    // Building renders every slide, so it is a visible phase, not a blank page.
    expect(await screen.findByText(/Rendering every slide/)).toBeTruthy()
    expect(screen.queryByTestId('teacher-studio')).toBeNull()

    await act(async () => {
      finishBuild(PACKAGE)
    })
    expect(await screen.findByTestId('teacher-studio')).toBeTruthy()
    expect(buildReviewPackage).toHaveBeenCalledWith(INSTITUTION, ARTIFACT)
  })

  it('reports a package it cannot load instead of showing an empty studio', async () => {
    vi.mocked(loadReviewPackage).mockRejectedValue(new ApiError('FORBIDDEN', 'wrong institution'))
    vi.mocked(buildReviewPackage).mockRejectedValue(new ApiError('FORBIDDEN', 'wrong institution'))

    renderStudio()

    const alert = await screen.findByTestId('studio-error')
    expect(alert.textContent).toMatch(/FORBIDDEN/)
    expect(screen.queryByTestId('teacher-studio')).toBeNull()
  })

  it('reports a deep link to an artifact that does not exist', async () => {
    vi.mocked(loadReviewPackage).mockRejectedValue(new ApiError('NOT_FOUND', 'no artifact'))
    vi.mocked(buildReviewPackage).mockRejectedValue(new ApiError('NOT_FOUND', 'no artifact'))

    renderStudio()

    expect((await screen.findByTestId('studio-error')).textContent).toMatch(/NOT_FOUND/)
  })

  it('rebuilds on request, which re-renders every slide', async () => {
    const user = userEvent.setup()
    primeStoredPackage()
    vi.mocked(buildReviewPackage).mockResolvedValue(PACKAGE)

    renderStudio()
    await screen.findByTestId('teacher-studio')

    await user.click(screen.getByRole('button', { name: 'Rebuild package' }))
    await waitFor(() => expect(buildReviewPackage).toHaveBeenCalledTimes(1))
    expect((await screen.findByTestId('studio-notice')).textContent).toMatch(/Rebuilt the package/)
  })
})

describe('StudioPage — review actions', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('approves through the server and shows the version it moved to', async () => {
    const user = userEvent.setup()
    primeStoredPackage()
    vi.mocked(postReviewDecision).mockResolvedValue(makeState({ version_status: 'APPROVED' }))

    renderStudio()
    await screen.findByTestId('teacher-studio')

    await user.click(screen.getByRole('button', { name: 'Approve' }))

    await waitFor(() =>
      expect(postReviewDecision).toHaveBeenCalledWith(INSTITUTION, ARTIFACT, {
        decision: 'APPROVE',
        reviewer: undefined,
      }),
    )
    // The decision response *is* the new overlay: the version moves to APPROVED.
    expect(await screen.findByText('version APPROVED')).toBeTruthy()
    expect(await screen.findByText(/course version is now APPROVED/)).toBeTruthy()
  })

  it('surfaces the server refusal to approve a blocked document', async () => {
    const user = userEvent.setup()
    primeStoredPackage()
    vi.mocked(postReviewDecision).mockRejectedValue(
      new ApiError('PUBLICATION_BLOCKED', 'a slide failed to render'),
    )

    renderStudio()
    await screen.findByTestId('teacher-studio')

    await user.click(screen.getByRole('button', { name: 'Approve' }))

    expect(await screen.findByText(/PUBLICATION_BLOCKED/)).toBeTruthy()
  })

  it('saves a lesson-order draft without touching the package', async () => {
    const user = userEvent.setup()
    primeStoredPackage()
    vi.mocked(saveReviewDraft).mockResolvedValue({
      draft_id: 'draft-1',
      artifact_id: ARTIFACT,
      version_id: 'version-1',
      package_id: 'pkg-abc',
      content_package_version: 'cpv-abc',
      lesson_plan_version: 'lp-abc',
      revision: 1,
      sections: [],
      edited_by: INSTITUTION,
      created_at: '2026-10-16T10:00:00Z',
    })

    renderStudio()
    await screen.findByTestId('teacher-studio')

    await user.click(screen.getByRole('button', { name: 'Move section 1 (explanation) down' }))
    await user.click(screen.getByRole('button', { name: 'Save draft' }))

    await waitFor(() => expect(saveReviewDraft).toHaveBeenCalledTimes(1))
    expect(vi.mocked(saveReviewDraft).mock.calls[0][2].sections.map((item) => item.section_id)).toEqual([
      'sec-2',
      'sec-1',
    ])
    // The action is data about the package: the package is never rebuilt or edited.
    expect(buildReviewPackage).not.toHaveBeenCalled()
    expect(await screen.findByText(/the built package is unchanged/i)).toBeTruthy()
  })
})
