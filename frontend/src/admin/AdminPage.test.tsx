import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AdminPage from './AdminPage'
import {
  compileArtifact,
  createCourse,
  enrollStudent,
  listClasses,
  listCourses,
  listEnrollments,
  listMaterials,
  listPublications,
  loadClass,
  loadPublication,
  publishVersion,
  scheduleClass,
  startClass,
  uploadMaterial,
  type ClassSummary,
  type ClassView,
  type Material,
  type Publication,
} from '../api/client'
import { ARTIFACT, INSTITUTION } from '../test/fixtures'

// The admin pages are orchestration over the existing API, so the client is
// mocked; what the endpoints themselves do is covered by the backend tests.
vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    compileArtifact: vi.fn(),
    createCourse: vi.fn(),
    enrollStudent: vi.fn(),
    listClasses: vi.fn(),
    listCourses: vi.fn(),
    listEnrollments: vi.fn(),
    listMaterials: vi.fn(),
    listPublications: vi.fn(),
    loadClass: vi.fn(),
    loadPublication: vi.fn(),
    publishVersion: vi.fn(),
    scheduleClass: vi.fn(),
    startClass: vi.fn(),
    uploadMaterial: vi.fn(),
  }
})

const COURSE = { course_id: 'course-1', title: 'Biology 101' }

const MATERIAL: Material = {
  artifact_id: ARTIFACT,
  version_id: 'version-1',
  version: 3,
  filename: 'chapter-8.pptx',
  media_type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  sha256: 'a'.repeat(64),
  byte_size: 2048,
  created_at: '2026-10-16T08:30:00Z',
  job_id: 'job-1',
  job_status: 'EXTRACTED',
  job_updated_at: '2026-10-16T08:31:00Z',
}

const CLASS: ClassSummary = {
  class_id: 'class-1',
  institution_id: INSTITUTION,
  course_id: 'course-1',
  title: 'Period 3',
  version_id: null,
  scheduled_for: null,
  state: 'SCHEDULED',
  created_at: '2026-10-16T09:00:00Z',
  started_at: null,
}

const STARTED: ClassView & { created: boolean } = {
  class: { ...CLASS, state: 'ACTIVE', started_at: '2026-10-16T09:05:00Z' },
  session: {
    session_id: 'session-1',
    class_id: 'class-1',
    course_id: 'course-1',
    session_plan_id: 'plan-1',
    state: 'ACTIVE',
    actor_epoch: 1,
    state_version: 1,
    event_sequence: 1,
    snapshot_id: 'snap-1',
    created_at: '2026-10-16T09:05:00Z',
    started_at: '2026-10-16T09:05:00Z',
  },
  session_plan: {
    session_plan_id: 'plan-1',
    class_id: 'class-1',
    versions: { content_package_version: 'cpv-abc', teaching_graph_version: null },
    capabilities: { renderer: 'local-structural-svg@3.1.0' },
    created_at: '2026-10-16T09:05:00Z',
  },
  created: true,
}

const PUBLICATION: Publication = {
  publication_id: 'pub-1',
  institution_id: INSTITUTION,
  course_id: 'course-1',
  version_id: 'version-1',
  course_version: 3,
  artifact_id: ARTIFACT,
  package_id: 'pkg-abc',
  content_package_version: 'cpv-abc',
  lesson_plan_versions: ['lp-abc'],
  knowledge_index_version: 'unindexed',
  teaching_graph_version: null,
  index_version_id: 'index-1',
  package_prefix: 'packages/pkg-abc',
  manifest_sha256: 'b'.repeat(64),
  content_digest: 'c'.repeat(64),
  file_count: 5,
  total_bytes: 4096,
  state: 'PUBLISHED',
  superseded_by: null,
  published_by: 'teacher@example.edu',
  created_at: '2026-10-16T10:00:00Z',
}

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
  vi.mocked(listCourses).mockResolvedValue([COURSE])
  vi.mocked(listClasses).mockResolvedValue([])
  vi.mocked(listMaterials).mockResolvedValue([])
  vi.mocked(listPublications).mockResolvedValue({ course_id: 'course-1', publications: [] })
})

describe('AdminPage — overview', () => {
  it('reports what the institution holds without mutating anything', async () => {
    vi.mocked(listClasses).mockResolvedValue([CLASS])
    render(<AdminPage section="overview" />)

    expect(await screen.findByTestId('admin-course-count')).toHaveProperty('textContent', '1')
    expect(screen.getByTestId('admin-class-count')).toHaveProperty('textContent', '1')
    // It links to the sections that can act, rather than acting itself.
    expect(
      screen.getByRole('link', { name: 'Manage courses & materials' }).getAttribute('href'),
    ).toBe('/admin/courses')
    expect(createCourse).not.toHaveBeenCalled()
  })
})

describe('AdminPage — courses and materials', () => {
  it('creates a course', async () => {
    const user = userEvent.setup()
    vi.mocked(createCourse).mockResolvedValue({
      course_id: 'course-9',
      institution_id: INSTITUTION,
    })
    render(<AdminPage section="courses" />)

    await user.type(await screen.findByLabelText('New course title'), 'Astronomy')
    await user.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() =>
      expect(createCourse).toHaveBeenCalledWith(INSTITUTION, 'Astronomy'),
    )
  })

  it('lists the selected course’s materials and offers the deck actions', async () => {
    vi.mocked(listMaterials).mockResolvedValue([MATERIAL])
    render(<AdminPage section="courses" />)

    expect(await screen.findByText('chapter-8.pptx')).toBeTruthy()
    expect(screen.getByText('EXTRACTED')).toBeTruthy()
    expect(screen.getByLabelText('New course title')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Studio' }).getAttribute('href')).toBe(
      `/studio/${ARTIFACT}`,
    )
    expect(screen.getByRole('link', { name: 'Learn' }).getAttribute('href')).toBe(
      `/learn/${ARTIFACT}`,
    )
    // There is no rename or delete: an artifact is immutable.
    expect(screen.queryByRole('button', { name: /delete/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /rename/i })).toBeNull()
  })

  it('uploads into the selected course and reports a deduplicated reuse', async () => {
    const user = userEvent.setup()
    vi.mocked(uploadMaterial).mockResolvedValue({
      artifact_id: ARTIFACT,
      job_id: 'job-1',
      version_id: 'version-1',
      course_id: 'course-1',
      filename: 'chapter-8.pptx',
      media_type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
      sha256: 'a'.repeat(64),
      byte_size: 2048,
      job_status: 'EXTRACTED',
      created: false,
    })
    render(<AdminPage section="courses" />)

    const file = new File(['bytes'], 'chapter-8.pptx', {
      type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    })
    await user.upload(await screen.findByLabelText('Upload a .pptx'), file)
    await user.click(screen.getByRole('button', { name: 'Upload' }))

    await waitFor(() => expect(uploadMaterial).toHaveBeenCalledWith(INSTITUTION, 'course-1', file))
    expect(await screen.findByText(/already stored/)).toBeTruthy()
    // The uploaded deck becomes the remembered one, so the shared nav can reach it.
    expect(localStorage.getItem('mentora.artifact')).toBe(ARTIFACT)
  })

  it('compiles a deck in the render mode chosen in Settings', async () => {
    const user = userEvent.setup()
    localStorage.setItem(
      'mentora.settings',
      JSON.stringify({ renderMode: 'themed', teachingWpm: 160 }),
    )
    vi.mocked(listMaterials).mockResolvedValue([MATERIAL])
    vi.mocked(compileArtifact).mockResolvedValue({
      validation: { publishable: true, requires_review: false, scene_count: 12 },
    })
    render(<AdminPage section="courses" />)

    await user.click(await screen.findByRole('button', { name: 'Compile' }))

    await waitFor(() =>
      expect(compileArtifact).toHaveBeenCalledWith(INSTITUTION, ARTIFACT, 'themed'),
    )
    expect(await screen.findByText(/12 scene\(s\), publishable/)).toBeTruthy()
  })
})

describe('AdminPage — classes', () => {
  it('schedules a class onto a course', async () => {
    const user = userEvent.setup()
    vi.mocked(scheduleClass).mockResolvedValue(CLASS)
    render(<AdminPage section="classes" />)

    await user.type(await screen.findByLabelText('Title'), 'Period 3')
    await user.click(screen.getByRole('button', { name: 'Schedule class' }))

    await waitFor(() =>
      expect(scheduleClass).toHaveBeenCalledWith(INSTITUTION, {
        course_id: 'course-1',
        title: 'Period 3',
        version_id: null,
        scheduled_for: null,
      }),
    )
    // Scheduling is not starting: the page says nothing runs yet.
    expect(await screen.findByText(/nothing runs until you start it/)).toBeTruthy()
  })

  it('starts a class and enrols students', async () => {
    const user = userEvent.setup()
    vi.mocked(listClasses).mockResolvedValue([CLASS])
    vi.mocked(loadClass).mockResolvedValue({
      class: CLASS,
      session: null,
      session_plan: null,
    })
    vi.mocked(listEnrollments).mockResolvedValue({ class_id: 'class-1', enrollments: [] })
    vi.mocked(startClass).mockResolvedValue(STARTED)
    vi.mocked(enrollStudent).mockResolvedValue({
      enrollment_id: 'enrollment-1',
      institution_id: INSTITUTION,
      class_id: 'class-1',
      student_id: 'student-7',
      created_at: '2026-10-16T09:06:00Z',
      created: true,
    })
    render(<AdminPage section="classes" />)

    await user.click(await screen.findByRole('button', { name: /Period 3/ }))
    await waitFor(() => expect(loadClass).toHaveBeenCalledWith(INSTITUTION, 'class-1'))

    await user.click(screen.getByRole('button', { name: 'Start' }))
    await waitFor(() => expect(startClass).toHaveBeenCalledWith(INSTITUTION, 'class-1'))
    expect(await screen.findByText(/runtime tuple is now pinned/)).toBeTruthy()

    await user.type(screen.getByLabelText('Student id'), 'student-7')
    await user.click(screen.getByRole('button', { name: 'Enrol' }))
    await waitFor(() =>
      expect(enrollStudent).toHaveBeenCalledWith(INSTITUTION, 'class-1', 'student-7'),
    )
    expect(await screen.findByText(/Enrolled student-7/)).toBeTruthy()
  })
})

describe('AdminPage — publications', () => {
  it('publishes a version and reports that a replay is idempotent', async () => {
    const user = userEvent.setup()
    vi.mocked(publishVersion).mockResolvedValue({ ...PUBLICATION, created: false })
    render(<AdminPage section="publications" />)

    await user.type(await screen.findByLabelText('Course version'), 'version-1')
    await user.click(screen.getByRole('button', { name: 'Publish' }))

    await waitFor(() =>
      expect(publishVersion).toHaveBeenCalledWith(INSTITUTION, 'version-1', undefined),
    )
    expect(await screen.findByText(/already published/)).toBeTruthy()
  })

  it('verifies a publication against the digest recorded at seal time', async () => {
    const user = userEvent.setup()
    vi.mocked(listPublications).mockResolvedValue({
      course_id: 'course-1',
      publications: [PUBLICATION],
    })
    vi.mocked(loadPublication).mockResolvedValue({
      ...PUBLICATION,
      integrity: {
        state: 'VERIFIED',
        package_id: 'pkg-abc',
        expected_digest: 'c'.repeat(64),
      },
    })
    render(<AdminPage section="publications" />)

    expect(await screen.findByText('pub-1')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Verify integrity' }))

    await waitFor(() =>
      expect(loadPublication).toHaveBeenCalledWith(INSTITUTION, 'pub-1', true),
    )
    expect(await screen.findByText(/Integrity of pub-1: VERIFIED/)).toBeTruthy()
  })
})
