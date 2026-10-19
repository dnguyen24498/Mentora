import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AdminPage from './AdminPage'
import {
  ApiError,
  compileArtifact,
  createAccount,
  createCourse,
  deleteAccount,
  enrollStudentById,
  listAccounts,
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
  unenrollStudent,
  updateAccount,
  uploadMaterial,
  type Account,
  type ClassSummary,
  type ClassView,
  type Material,
  type Publication,
} from '../api/client'
import { clearSession, writeSession, type AuthSession, type Principal, type Scope } from '../auth/session'
import { fromDateTimeLocalValue } from '../time'
import { ARTIFACT, INSTITUTION } from '../test/fixtures'

// The admin pages are orchestration over the existing API, so the client is
// mocked; what the endpoints themselves do is covered by the backend tests.
vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    compileArtifact: vi.fn(),
    createAccount: vi.fn(),
    createCourse: vi.fn(),
    deleteAccount: vi.fn(),
    enrollStudentById: vi.fn(),
    listAccounts: vi.fn(),
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
    unenrollStudent: vi.fn(),
    updateAccount: vi.fn(),
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
  clearSession()
  vi.clearAllMocks()
  vi.mocked(listCourses).mockResolvedValue([COURSE])
  vi.mocked(listClasses).mockResolvedValue([])
  vi.mocked(listMaterials).mockResolvedValue([])
  vi.mocked(listPublications).mockResolvedValue({ course_id: 'course-1', publications: [] })
  vi.mocked(listAccounts).mockResolvedValue({
    institution_id: INSTITUTION,
    role: 'student',
    accounts: [],
  })
})

/** A signed-in principal for a role, so a section's capability filter is exercised. */
function signIn(role: 'institution_admin' | 'teacher', scopes: Scope[]) {
  const principal: Principal = {
    authenticated: true,
    institution_id: INSTITUTION,
    role,
    scopes,
    account_id: 'account-self',
    email: `${role}@uni.test`,
    display_name: null,
    session_id: 'session-1',
  }
  const session: AuthSession = {
    token: 'token-1',
    principal,
    authenticator: {
      id: 'local-credentials@1.0.0',
      name: 'Local development credentials',
      version: '1.0.0',
      kind: 'DEVELOPMENT_MOCK',
    },
    notice: 'Answered by a development mock.',
    expiresAt: new Date(Date.now() + 3_600_000).toISOString(),
  }
  writeSession(session)
}

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

  it('starts a class and assigns an existing student to its roster', async () => {
    const user = userEvent.setup()
    vi.mocked(listClasses).mockResolvedValue([CLASS])
    vi.mocked(loadClass).mockResolvedValue({
      class: CLASS,
      session: null,
      session_plan: null,
    })
    vi.mocked(loadRoster).mockResolvedValue({ class_id: 'class-1', enrollments: [] })
    vi.mocked(startClass).mockResolvedValue(STARTED)
    // A teacher picks from the students who exist: `account:read` lists students.
    vi.mocked(listAccounts).mockResolvedValue({
      institution_id: INSTITUTION,
      role: 'student',
      accounts: [STUDENT],
    })
    vi.mocked(enrollStudentById).mockResolvedValue({
      enrollment_id: 'enrollment-1',
      institution_id: INSTITUTION,
      class_id: 'class-1',
      student_id: STUDENT.account_id,
      created_at: '2026-10-16T09:06:00Z',
      created: true,
      student: STUDENT,
    })
    render(<AdminPage section="classes" />)

    await user.click(await screen.findByRole('button', { name: /Period 3/ }))
    await waitFor(() => expect(loadClass).toHaveBeenCalledWith(INSTITUTION, 'class-1'))

    await user.click(screen.getByRole('button', { name: 'Start' }))
    await waitFor(() => expect(startClass).toHaveBeenCalledWith(INSTITUTION, 'class-1'))
    expect(await screen.findByText(/runtime tuple is now pinned/)).toBeTruthy()

    // Assigning picks an account that already exists — enrolment never creates one
    // (V0-022), so there is an address list rather than an address to type.
    await user.selectOptions(await screen.findByLabelText('Student'), STUDENT.account_id)
    await user.click(screen.getByRole('button', { name: 'Add to class' }))
    await waitFor(() =>
      expect(enrollStudentById).toHaveBeenCalledWith(INSTITUTION, 'class-1', STUDENT.account_id),
    )
    expect(await screen.findByText(/Enrolled student7@school.example/)).toBeTruthy()
    expect(createAccount).not.toHaveBeenCalled()
  })

  it('removes a student from the roster without touching the account', async () => {
    const user = userEvent.setup()
    vi.mocked(listClasses).mockResolvedValue([CLASS])
    vi.mocked(loadClass).mockResolvedValue({ class: CLASS, session: null, session_plan: null })
    vi.mocked(loadRoster).mockResolvedValue({
      class_id: 'class-1',
      enrollments: [
        {
          enrollment_id: 'enrollment-1',
          institution_id: INSTITUTION,
          class_id: 'class-1',
          student_id: STUDENT.account_id,
          created_at: '2026-10-16T09:06:00Z',
          student: STUDENT,
        },
      ],
    })
    vi.mocked(listAccounts).mockResolvedValue({
      institution_id: INSTITUTION,
      role: 'student',
      accounts: [STUDENT],
    })
    vi.mocked(unenrollStudent).mockResolvedValue({
      class_id: 'class-1',
      student_id: STUDENT.account_id,
      removed: true,
    })
    render(<AdminPage section="classes" />)

    await user.click(await screen.findByRole('button', { name: /Period 3/ }))
    await user.click(
      await screen.findByRole('button', {
        name: `Remove ${STUDENT.email} from this class`,
      }),
    )

    await waitFor(() =>
      expect(unenrollStudent).toHaveBeenCalledWith(INSTITUTION, 'class-1', STUDENT.account_id),
    )
    expect(await screen.findByText(/The account itself is unchanged/)).toBeTruthy()
    expect(deleteAccount).not.toHaveBeenCalled()
  })
})

describe('AdminPage — the directory, by capability', () => {
  const ADMIN_SCOPES: Scope[] = ['account:read', 'account:write', 'content:read', 'class:read']

  it('offers Accounts to an administrator and withholds the authoring sections', async () => {
    signIn('institution_admin', ADMIN_SCOPES)
    render(<AdminPage section="overview" />)

    expect(await screen.findByRole('link', { name: 'Accounts' })).toBeTruthy()
    // An administrator authors nothing, so the authoring sections would only 403.
    expect(screen.queryByRole('link', { name: 'Courses & materials' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'Classes' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'Publications' })).toBeNull()
  })

  it('withholds Accounts from a teacher', async () => {
    signIn('teacher', [
      'account:read',
      'class:read',
      'class:write',
      'content:read',
      'content:write',
      'enrollment:write',
      'publication:write',
      'review:write',
      'scene:read',
    ])
    render(<AdminPage section="overview" />)

    expect(await screen.findByRole('link', { name: 'Courses & materials' })).toBeTruthy()
    expect(screen.queryByRole('link', { name: 'Accounts' })).toBeNull()
  })

  it('says a section is unavailable rather than showing a page that would 403', async () => {
    signIn('teacher', ['account:read', 'content:read'])

    // A URL the nav does not offer for this role reaches an honest dead end.
    render(<AdminPage section="accounts" />)

    expect(await screen.findByText('Not available for this account')).toBeTruthy()
    expect(screen.queryByLabelText('Email address')).toBeNull()
  })

  it('creates a teacher and hands over the one-time code exactly once', async () => {
    const user = userEvent.setup()
    signIn('institution_admin', ADMIN_SCOPES)
    vi.mocked(createAccount).mockResolvedValue({
      created: true,
      account: { ...STUDENT, role: 'teacher', status: 'ACTIVE' },
      development_credential: 'dev-code-9',
      sessions_revoked: 0,
    })
    render(<AdminPage section="accounts" />)

    await user.type(await screen.findByLabelText('Email address'), 'new@school.example')
    await user.selectOptions(screen.getByLabelText('Role'), 'teacher')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    await waitFor(() =>
      expect(createAccount).toHaveBeenCalledWith(
        INSTITUTION,
        'new@school.example',
        'teacher',
        '',
      ),
    )
    expect(screen.getByTestId('issued-credential').textContent).toContain('dev-code-9')
    // The code is a labelled development mock, and the page says so.
    expect(screen.getByTestId('issued-credential').textContent).toMatch(/development mock/)
  })

  it('explains a refused removal with the remedy the guard points at', async () => {
    const user = userEvent.setup()
    signIn('institution_admin', ADMIN_SCOPES)
    vi.mocked(listAccounts).mockResolvedValue({
      institution_id: INSTITUTION,
      role: 'student',
      accounts: [STUDENT],
    })
    vi.mocked(deleteAccount).mockRejectedValue(
      new ApiError('CONFLICT', 'the account is on a class roster', 'ACCOUNT_IN_USE'),
    )
    render(<AdminPage section="accounts" />)

    await user.click(await screen.findByRole('button', { name: 'Delete' }))

    const banner = await screen.findByRole('alert')
    expect(banner.textContent).toMatch(/ACCOUNT_IN_USE|on a class roster/)
    expect(banner.textContent).toMatch(/Disable instead/)
  })

  it('disables an account and reports the sessions it revoked', async () => {
    const user = userEvent.setup()
    signIn('institution_admin', ADMIN_SCOPES)
    vi.mocked(listAccounts).mockResolvedValue({
      institution_id: INSTITUTION,
      role: 'student',
      accounts: [STUDENT],
    })
    vi.mocked(updateAccount).mockResolvedValue({
      created: false,
      account: { ...STUDENT, status: 'DISABLED' },
      development_credential: null,
      sessions_revoked: 2,
    })
    render(<AdminPage section="accounts" />)

    await user.click(await screen.findByRole('button', { name: 'Disable' }))

    await waitFor(() =>
      expect(updateAccount).toHaveBeenCalledWith(INSTITUTION, STUDENT.account_id, {
        status: 'DISABLED',
      }),
    )
    expect(await screen.findByText(/revoked 2 live session/)).toBeTruthy()
  })

  it('does not offer administrator creation through the directory', async () => {
    signIn('institution_admin', ADMIN_SCOPES)
    render(<AdminPage section="accounts" />)

    // Administrator accounts come from the deployment bootstrap, and the page says
    // so instead of offering a role the API refuses.
    expect(await screen.findByText(/Administrators are not created here/)).toBeTruthy()
    expect(screen.queryByRole('option', { name: /administrator/i })).toBeNull()
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
