import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import UploadPage from './UploadPage'
import {
  autoPublishArtifact,
  extractArtifact,
  listClasses,
  listCourses,
  listMaterials,
  uploadMaterial,
  type AutoPublicationResult,
  type ContentIR,
  type UploadResult,
} from '../api/client'
import { ARTIFACT, INSTITUTION, makeState } from '../test/fixtures'

// The page's job here is orchestration: after storing a deck it must ask the
// server to auto-publish it and report the policy outcome truthfully.
vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    autoPublishArtifact: vi.fn(),
    createCourse: vi.fn(),
    extractArtifact: vi.fn(),
    listClasses: vi.fn(),
    listCourses: vi.fn(),
    listMaterials: vi.fn(),
    uploadMaterial: vi.fn(),
  }
})

const COURSE = { course_id: 'course-1', title: 'Neural Networks' }
const DECK = new File(['pptx-bytes'], 'lecture.pptx', {
  type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
})

const IR: ContentIR = {
  schema_version: 'content-ir/1.2.0',
  slide_count: 0,
  slides: [],
  warnings: [],
  provenance: {},
}

const UPLOADED: UploadResult = {
  artifact_id: ARTIFACT,
  job_id: 'job-1',
  version_id: 'version-1',
  course_id: COURSE.course_id,
  filename: DECK.name,
  media_type: DECK.type,
  sha256: 'a'.repeat(64),
  byte_size: DECK.size,
  job_status: 'PENDING',
  created: true,
}

function autoResult(overrides: Partial<AutoPublicationResult> = {}): AutoPublicationResult {
  return {
    artifact_id: ARTIFACT,
    version_id: 'version-1',
    package_id: 'pkg-abc',
    content_package_version: 'cpv-abc',
    state: 'READY',
    published: true,
    created: true,
    requires_review: false,
    publication: {
      course_version: 3,
      state: 'PUBLISHED',
      published_by: 'teacher@uni.test',
    } as unknown as AutoPublicationResult['publication'],
    review_state: makeState({ version_status: 'PUBLISHED' }),
    ...overrides,
  }
}

async function uploadOneDeck() {
  render(<UploadPage />)
  // The first course is selected once the list arrives; the file input is the
  // hidden control behind the drop zone.
  await screen.findByRole('option', { name: COURSE.title })
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  await userEvent.upload(input, DECK)
  await userEvent.click(screen.getByRole('button', { name: 'Upload' }))
}

beforeEach(() => {
  localStorage.clear()
  vi.mocked(listCourses).mockResolvedValue([COURSE])
  vi.mocked(listMaterials).mockResolvedValue([])
  vi.mocked(listClasses).mockResolvedValue([])
  vi.mocked(uploadMaterial).mockResolvedValue(UPLOADED)
  vi.mocked(extractArtifact).mockResolvedValue(IR)
  vi.mocked(autoPublishArtifact).mockResolvedValue(autoResult())
})

describe('UploadPage auto-publication', () => {
  it('publishes a stored deck automatically and says so', async () => {
    await uploadOneDeck()

    await waitFor(() =>
      expect(autoPublishArtifact).toHaveBeenCalledWith(INSTITUTION, ARTIFACT),
    )
    expect(
      await screen.findByText(/Published automatically as version 3/),
    ).toBeTruthy()
    expect(screen.getByText(/ready to use in a class/)).toBeTruthy()
  })

  it('leaves a human-required deck unpublished and points at Teacher Studio', async () => {
    vi.mocked(autoPublishArtifact).mockResolvedValue(
      autoResult({
        state: 'REVIEW_REQUIRED',
        published: false,
        created: false,
        requires_review: true,
        publication: null,
        review_state: makeState({ state: 'REVIEW_REQUIRED', requires_review: true }),
      }),
    )

    await uploadOneDeck()

    expect(
      await screen.findByText(/needs a teacher review before publication/),
    ).toBeTruthy()
    expect(screen.getByText(/Open Teacher Studio to review it/)).toBeTruthy()
    expect(screen.getByText(/publish it from Admin → Publications/)).toBeTruthy()
  })

  it('keeps the upload when automatic publication itself fails', async () => {
    vi.mocked(autoPublishArtifact).mockRejectedValue(
      new Error('publication service unavailable'),
    )

    await uploadOneDeck()

    expect(await screen.findByText(/automatic publication did not complete/)).toBeTruthy()
    // The failure is still reported precisely; the stored deck is not lost.
    expect(await screen.findByText('ERROR')).toBeTruthy()
    expect(screen.getByText(/publication service unavailable/)).toBeTruthy()
  })
})
