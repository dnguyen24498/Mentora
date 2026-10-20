import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import {
  loadArtifact,
  loadClass,
  loadReviewPackage,
  loadReviewState,
  loadSnapshot,
  listClasses,
  listCourses,
  listMaterials,
} from './api/client'
import { writeSession, clearSession } from './auth/session'
import { writeSelectedClass } from './institution'
import { ARTIFACT, INSTITUTION, makeArtifact, makePackage, makeState } from './test/fixtures'
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
    loadClass: vi.fn(),
    loadReviewPackage: vi.fn(),
    loadReviewState: vi.fn(),
    loadSnapshot: vi.fn(),
    postReviewDecision: vi.fn(),
    saveReviewDraft: vi.fn(),
    uploadMaterial: vi.fn(),
  }
})

const TEACHER_SCOPES = [
  'account:read',
  'class:read',
  'class:write',
  'content:read',
  'content:write',
  'enrollment:write',
  'publication:write',
  'review:write',
  'scene:read',
]

/** Sign this browser in as a teacher, the way the login page would (V0-023). */
function signInAsTeacher() {
  writeSession({
    token: 'tok-2',
    principal: {
      authenticated: true,
      institution_id: INSTITUTION,
      role: 'teacher',
      scopes: TEACHER_SCOPES,
      account_id: 'account-teacher',
      email: 'teacher@school.example',
      display_name: 'Tess Teacher',
      session_id: 'session-2',
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

/** Sign this browser in as a student, the way the login page would. */
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

/** Point the test at a URL the way a deep link or a refresh would. */
function visit(path: string) {
  window.history.replaceState({}, '', path)
}

describe('App — routing between the pages', () => {
  beforeEach(() => {
    localStorage.clear()
    clearSession()
    // These are the signed-in teacher's pages (V0-023): the guard needs a session.
    signInAsTeacher()
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
    vi.mocked(loadReviewState).mockResolvedValue(makeState())
    vi.mocked(loadArtifact).mockResolvedValue(makeArtifact())

    render(<App />)

    expect(await screen.findByRole('heading', { level: 1, name: 'Learning' })).toBeTruthy()
    expect(await screen.findByTestId('teaching-canvas')).toBeTruthy()
    expect(screen.queryByTestId('teacher-studio')).toBeNull()
  })

  it('serves the Admin area at /admin and one section at /admin/{section}', async () => {
    visit('/admin')
    render(<App />)

    expect(await screen.findByRole('heading', { level: 1, name: 'Admin' })).toBeTruthy()
    expect(await screen.findByTestId('admin-course-count')).toBeTruthy()
    // The section tabs are real links, so a section survives a refresh too.
    expect(screen.getByRole('link', { name: 'Courses & materials' }).getAttribute('href')).toBe(
      '/admin/courses',
    )
  })

  it('serves Settings at /settings and one section at /settings/{section}', async () => {
    visit('/settings/teaching')
    render(<App />)

    expect(await screen.findByRole('heading', { level: 1, name: 'Settings' })).toBeTruthy()
    // The teaching section is the one on screen, and it is honest about the audio.
    expect(await screen.findByText('Text only.')).toBeTruthy()
  })
})

describe('App — identities (V0-021, V0-023)', () => {
  beforeEach(() => {
    localStorage.clear()
    clearSession()
    vi.mocked(listCourses).mockResolvedValue([])
    vi.mocked(listClasses).mockResolvedValue([])
    vi.mocked(listMaterials).mockResolvedValue([])
  })

  it('serves the sign-in page at /login, the one public route', async () => {
    visit('/login')
    render(<App />)

    expect(await screen.findByRole('heading', { level: 1, name: 'Sign in' })).toBeTruthy()
  })

  it('sends an unauthenticated browser to sign in, remembering where it was going', async () => {
    visit('/admin/publications')
    render(<App />)

    // The guard replaced the location, so the URL says where to come back to and the
    // deep link cannot linger in the history.
    expect(window.location.pathname).toBe('/login')
    expect(window.location.search).toBe('?next=%2Fadmin%2Fpublications')
    // …and the form is actually on screen: a redirect that only rewrote the URL
    // would leave a blank page.
    expect(await screen.findByRole('heading', { level: 1, name: 'Sign in' })).toBeTruthy()
  })

  it('guards the library too: nothing opens without a session', async () => {
    visit('/')
    render(<App />)

    expect(window.location.pathname).toBe('/login')
    expect(screen.queryByRole('heading', { name: /Upload Course Material/ })).toBeNull()
  })

  it('serves a class join page to a signed-in participant', async () => {
    signInAsStudent()
    visit('/join/class-1')
    vi.mocked(loadClass).mockResolvedValue({
      class: {
        class_id: 'class-1',
        institution_id: INSTITUTION,
        course_id: 'course-1',
        title: 'Period 3',
        version_id: null,
        scheduled_for: null,
        state: 'SCHEDULED',
        created_at: '2026-10-16T09:00:00Z',
        started_at: null,
      },
      session: null,
      session_plan: null,
    })

    render(<App />)

    expect(await screen.findByRole('heading', { level: 1, name: 'Join a class' })).toBeTruthy()
  })

  it('keeps a student out of the authoring pages, and offers their class instead', async () => {
    signInAsStudent()
    writeSelectedClass('class-1')
    // A student who follows an authoring link is told so rather than shown a
    // page whose every request would answer 403.
    visit(`/studio/${ARTIFACT}`)

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Your classes' })).toBeTruthy()
    expect(screen.queryByTestId('teacher-studio')).toBeNull()
    // The landing is usable, not just a refusal: the remembered class opens.
    expect(screen.getByRole('button', { name: 'Open class' })).toBeTruthy()
    expect(screen.getByLabelText('Class id')).toBeTruthy()
  })

  it('gives a student with no remembered class a way in by id', async () => {
    signInAsStudent()
    visit('/admin')

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Your classes' })).toBeTruthy()
    // The join link's shape is shown, so a student knows what to look for.
    expect(screen.getByText(/join\/<class id>/)).toBeTruthy()
    expect((screen.getByLabelText('Class id') as HTMLInputElement).value).toBe('')
  })

  it('still lets a student reach Settings, which belongs to no role', async () => {
    signInAsStudent()
    visit('/settings')

    render(<App />)

    expect(await screen.findByRole('heading', { level: 1, name: 'Settings' })).toBeTruthy()
  })
})
