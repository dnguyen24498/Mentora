import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import {
  loadArtifact,
  loadReviewPackage,
  loadReviewState,
  loadSnapshot,
  listClasses,
  listCourses,
  listMaterials,
} from './api/client'
import { ARTIFACT, makeArtifact, makePackage, makeState } from './test/fixtures'
import { TEST_CLASS, makeSnapshot } from './classroom/state/testing'

vi.mock('./api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api/client')>()
  return {
    ...actual,
    buildReviewPackage: vi.fn(),
    createCourse: vi.fn(),
    extractArtifact: vi.fn(),
    listCourses: vi.fn(),
    listClasses: vi.fn(),
    listMaterials: vi.fn(),
    loadArtifact: vi.fn(),
    loadReviewPackage: vi.fn(),
    loadReviewState: vi.fn(),
    loadSnapshot: vi.fn(),
    postReviewDecision: vi.fn(),
    saveReviewDraft: vi.fn(),
    uploadMaterial: vi.fn(),
  }
})

/** Point the test at a URL the way a deep link or a refresh would. */
function visit(path: string) {
  window.history.replaceState({}, '', path)
}

describe('App — routing between the pages', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.mocked(listCourses).mockResolvedValue([])
    vi.mocked(listClasses).mockResolvedValue([])
    vi.mocked(listMaterials).mockResolvedValue([])
  })

  it('serves the material library at /', async () => {
    visit('/')
    render(<App />)

    expect(await screen.findByRole('heading', { name: /Upload Course Material/ })).toBeTruthy()
    expect(screen.queryByTestId('teacher-studio')).toBeNull()
  })

  it('serves the Teacher Studio as its own page at /studio/{artifactId}', async () => {
    visit(`/studio/${ARTIFACT}`)
    vi.mocked(loadReviewPackage).mockResolvedValue(makePackage())
    vi.mocked(loadReviewState).mockResolvedValue(makeState())
    vi.mocked(loadArtifact).mockResolvedValue(makeArtifact())

    render(<App />)

    // A deep link (a new tab, a refresh, a bookmark) loads the studio directly.
    expect(await screen.findByTestId('teacher-studio')).toBeTruthy()
    expect(screen.getByRole('heading', { level: 1, name: 'Teacher Studio' })).toBeTruthy()
    expect(screen.queryByRole('heading', { name: /Upload Course Material/ })).toBeNull()
  })

  it('renders its own not-found view for an unknown path', async () => {
    visit('/somewhere/else')
    render(<App />)

    expect(await screen.findByRole('heading', { name: /Page not found/ })).toBeTruthy()
  })

  it('serves the Classroom as its own page at /classroom/{classId}', async () => {
    visit(`/classroom/${TEST_CLASS}`)
    vi.mocked(loadSnapshot).mockResolvedValue(makeSnapshot())

    render(<App />)

    expect(await screen.findByTestId('classroom-shell')).toBeTruthy()
    expect(screen.getByRole('heading', { level: 1, name: 'Classroom' })).toBeTruthy()
    expect(screen.queryByRole('heading', { name: /Upload Course Material/ })).toBeNull()
  })

  it('serves the Learning page at /learn/{artifactId}', async () => {
    visit(`/learn/${ARTIFACT}`)
    vi.mocked(loadReviewPackage).mockResolvedValue(makePackage())
    vi.mocked(loadArtifact).mockResolvedValue(makeArtifact())

    render(<App />)

    expect(await screen.findByRole('heading', { level: 1, name: 'Learning' })).toBeTruthy()
    expect(await screen.findByTestId('teaching-canvas')).toBeTruthy()
    expect(screen.queryByTestId('teacher-studio')).toBeNull()
  })
})
