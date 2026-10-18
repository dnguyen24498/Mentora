import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AdminPage from './AdminPage'
import {
  ApiError,
  compileArtifact,
  createCourse,
  enrollStudentByEmail,
  listClasses,
  listCourses,
  listMaterials,
  listPublications,
  loadClass,
  loadPublication,
  loadRoster,
  publishVersion,
  scheduleClass,
  startClass,
  uploadMaterial,
  type Account,
  type ClassSummary,
  type ClassView,
  type Material,
  type Publication,
} from '../api/client'
import { fromDateTimeLocalValue } from '../time'
import { ARTIFACT, INSTITUTION } from '../test/fixtures'

// The admin pages are orchestration over the existing API, so the client is
// mocked; what the endpoints themselves do is covered by the backend tests.
vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    compileArtifact: vi.fn(),
    createCourse: vi.fn(),
    enrollStudentByEmail: vi.fn(),
    listClasses: vi.fn(),
    listCourses: vi.fn(),
    listMaterials: vi.fn(),
    listPublications: vi.fn(),
    loadClass: vi.fn(),
    loadPublication: vi.fn(),
    loadRoster: vi.fn(),
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

const STUDENT: Account = {
  account_id: 'account-7',
  institution_id: INSTITUTION,
  email: 'student7@school.example',
  display_name: 'Student Seven',
  role: 'student',
  scopes: ['class:read', 'scene:read', 'join'],
  status: 'ACTIVE',
  created_at: '2026-10-16T09:06:00Z',
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
    vi.mocked(loadClass).mockResolvedValue({ class: CLASS, session: null, session_plan: null })
    vi.mocked(loadRoster).mockResolvedValue({ class_id: 'class-1', enrollments: [] })
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
    expect(await screen.findByText(/Nothing runs until you start it/)).toBeTruthy()
  })

  it('records the datetime it was given, read on the teacher’s own clock', async () => {
    const user = userEvent.setup()
    const created: ClassSummary = {
      ...CLASS,
      title: 'Period 4',
      scheduled_for: '2026-10-20T09:30:00.000Z',
    }
    vi.mocked(scheduleClass).mockResolvedValue(created)
    vi.mocked(loadClass).mockResolvedValue({ class: created, session: null, session_plan: null })
    vi.mocked(loadRoster).mockResolvedValue({ class_id: 'class-1', enrollments: [] })
    render(<AdminPage section="classes" />)

    await user.type(await screen.findByLabelText('Title'), 'Period 4')
    fireEvent.change(screen.getByLabelText('Scheduled for (optional)'), {
      target: { value: '2026-10-20T09:30' },
    })
    await user.click(screen.getByRole('button', { name: 'Schedule class' }))

    await waitFor(() =>
      expect(scheduleClass).toHaveBeenCalledWith(INSTITUTION, {
        course_id: 'course-1',
        title: 'Period 4',
        version_id: null,
        // The teacher's own wall clock is what is meant, so the same local value
        // becomes the same instant on any machine.
        scheduled_for: fromDateTimeLocalValue('2026-10-20T09:30'),
      }),
    )
    // And the page repeats when that is, from its own clock.
    expect(await screen.findByText(/Scheduled "Period 4" for/)).toBeTruthy()
  })

  it('starts a class and invites a student onto the roster', async () => {
    const user = userEvent.setup()
    vi.mocked(listClasses).mockResolvedValue([CLASS])
    vi.mocked(loadClass).mockResolvedValue({
      class: CLASS,
      session: null,
      session_plan: null,
    })
    vi.mocked(loadRoster).mockResolvedValue({ class_id: 'class-1', enrollments: [] })
    vi.mocked(startClass).mockResolvedValue(STARTED)
    vi.mocked(enrollStudentByEmail).mockResolvedValue({
      enrollment_id: 'enrollment-1',
      institution_id: INSTITUTION,
      class_id: 'class-1',
      student_id: STUDENT.account_id,
      created_at: '2026-10-16T09:06:00Z',
      created: true,
      student: STUDENT,
      account_created: true,
      development_credential: 'dev-code-7',
    })
    render(<AdminPage section="classes" />)

    await user.click(await screen.findByRole('button', { name: /Period 3/ }))
    await waitFor(() => expect(loadClass).toHaveBeenCalledWith(INSTITUTION, 'class-1'))

    await user.click(screen.getByRole('button', { name: 'Start' }))
    await waitFor(() => expect(startClass).toHaveBeenCalledWith(INSTITUTION, 'class-1'))
    expect(await screen.findByText(/runtime tuple is now pinned/)).toBeTruthy()

    // Inviting by address creates-or-links the account in the tenant and enrols
    // it in one step, because enrolment is what a join is checked against.
    await user.type(screen.getByLabelText('Student email'), 'student7@school.example')
    await user.click(screen.getByRole('button', { name: 'Invite' }))
    await waitFor(() =>
      expect(enrollStudentByEmail).toHaveBeenCalledWith(
        INSTITUTION,
        'class-1',
        'student7@school.example',
      ),
    )
    expect(await screen.findByText(/Invited student7@school.example/)).toBeTruthy()
    // The one-time sign-in code is shown to hand over; it is returned once and
    // never stored in the clear.
    expect(screen.getByTestId('invited-credential').textContent).toContain('dev-code-7')
  })
})

describe('AdminPage — classes started at their own scheduled time', () => {
  // A minute ago, judged against the page's own clock, so the test does not
  // depend on the machine's calendar.
  const DUE: ClassSummary = {
    ...CLASS,
    scheduled_for: new Date(Date.now() - 60_000).toISOString(),
  }

  function primeAttached(list: ClassSummary[]) {
    vi.mocked(listClasses).mockResolvedValue(list)
    vi.mocked(loadClass).mockResolvedValue({ class: list[0], session: null, session_plan: null })
    vi.mocked(loadRoster).mockResolvedValue({ class_id: 'class-1', enrollments: [] })
  }

  it('starts a due class while the page is open, when auto-start is on', async () => {
    primeAttached([DUE])
    vi.mocked(startClass).mockResolvedValue(STARTED)
    localStorage.setItem('mentora.settings', JSON.stringify({ autoStartDueClasses: true }))

    render(<AdminPage section="classes" />)

    // The page starts it through the runtime's own idempotent transition, not a
    // private path: the same call the Start button makes.
    await waitFor(() => expect(startClass).toHaveBeenCalledWith(INSTITUTION, 'class-1'))
    const results = await screen.findByTestId('admin-auto-start-results')
    expect(results.textContent).toContain('Started "Period 3" at its scheduled time.')
  })

  it('leaves a due class alone when auto-start is off, and says when it was due', async () => {
    primeAttached([DUE])
    vi.mocked(startClass).mockResolvedValue(STARTED)

    render(<AdminPage section="classes" />)

    const schedule = await screen.findByTestId('class-schedule-class-1')
    // The schedule is shown, and it is visibly in the past.
    expect(schedule.textContent).toMatch(/ago/)
    expect((screen.getByTestId('class-auto-start') as HTMLInputElement).checked).toBe(false)
    expect(startClass).not.toHaveBeenCalled()
  })

  it('reports a class it could not start instead of swallowing the refusal', async () => {
    primeAttached([DUE])
    vi.mocked(startClass).mockRejectedValue(
      new ApiError('CLASS_NOT_READY', 'the course version was never published'),
    )
    localStorage.setItem('mentora.settings', JSON.stringify({ autoStartDueClasses: true }))

    render(<AdminPage section="classes" />)

    const results = await screen.findByTestId('admin-auto-start-results')
    expect(results.textContent).toContain('the course version was never published')
    // A refused start is reported once, not retried on every tick.
    expect(startClass).toHaveBeenCalledTimes(1)
  })

  it('says the waiting is done by the page, because the server has no scheduler', async () => {
    render(<AdminPage section="classes" />)

    const note = await screen.findByTestId('class-schedule-note')
    expect(note.textContent).toMatch(/this page/)
    expect(note.textContent).toContain('DEC-TECH-003')
    expect(note.textContent).toMatch(/still OPEN/)
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
