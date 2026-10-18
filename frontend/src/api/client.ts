import { currentToken, type AuthSession, type CapabilityIdentity, type Principal } from '../auth/session'

export class ApiError extends Error {
  code: string
  /** The precise cause behind a stable code, when the API names one. */
  issueCode: string | null

  constructor(code: string, message: string, issueCode: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.issueCode = issueCode
  }
}

export interface Course {
  course_id: string
  title: string
}

export interface Material {
  artifact_id: string
  version_id: string
  version: number
  filename: string
  media_type: string
  sha256: string
  byte_size: number
  created_at: string
  job_id: string
  job_status: string
  job_updated_at: string
}

export interface UploadResult {
  artifact_id: string
  job_id: string
  version_id: string
  course_id: string
  filename: string
  media_type: string
  sha256: string
  byte_size: number
  job_status: string
  created: boolean
}

export interface TextRun {
  text: string
  font?: string | null
  size_pt?: number | null
  bold?: boolean | null
  italic?: boolean | null
  underline?: boolean | null
  color?: { value: string; alpha: number } | null
}

export interface TextParagraph {
  level: number
  text: string
  runs?: TextRun[]
  align?: string | null
  bullet?: Record<string, unknown> | null
  margin_left_emu?: number | null
  space_before_pt?: number | null
  line_spacing_pt?: number | null
}

export interface ShapeObject {
  source_id: string
  kind: string
  name: string
  placeholder: string | null
  bounds: { x: number | null; y: number | null; width: number | null; height: number | null } | null
  depth: number
  paragraphs: TextParagraph[]
  table?: string[][]
  media_ref?: string | null
  /** Effective style resolved from the theme/layout/master chain (V0-018). */
  geometry?: string | null
  custom_path?: string | null
  fill?: Record<string, unknown> | null
  line?: Record<string, unknown> | null
  rotation?: number | null
  media_type?: string | null
  crop?: Record<string, number> | null
  table_columns?: number[] | null
}

export interface SlideScene {
  scene_id: string
  order: number
  notes: string | null
  objects: ShapeObject[]
  warnings: string[]
  fidelity: string
  background?: Record<string, unknown> | null
}

export interface ContentIR {
  schema_version: string
  slide_count: number
  slides: SlideScene[]
  warnings: string[]
  provenance: Record<string, unknown>
}

const UNREACHABLE_HINT =
  'The backend is not running. Start the whole stack with ./run.sh (frontend :8000, API :8001).'

/** Perform a request and turn every failure mode into a stable `ApiError`. */
async function send(path: string, institutionId: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers)
  // A session is the credential, and the tenant comes from it: when one is
  // present this header is redundant and the API ignores it. It stays because
  // the development tenant shortcut has no session and needs it.
  const token = currentToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (institutionId) headers.set('X-Institution-Id', institutionId)

  let response: Response
  try {
    response = await fetch(path, { ...init, headers })
  } catch (cause) {
    // fetch only rejects on a transport failure: the dev server or API is down.
    throw new ApiError(
      'BACKEND_UNAVAILABLE',
      `${UNREACHABLE_HINT} (${cause instanceof Error ? cause.message : 'network error'})`,
    )
  }

  if (response.ok) return response

  const text = await response.text()
  let body: unknown = null
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = text
    }
  }

  const error =
    body && typeof body === 'object'
      ? (body as { error?: { code?: string; message?: string; issue_code?: string } }).error
      : undefined
  if (error?.code) {
    throw new ApiError(error.code, error.message ?? response.statusText, error.issue_code ?? null)
  }
  if (response.status >= 500 && !text.trim()) {
    // A 5xx with an empty body means the request never reached the API.
    throw new ApiError('BACKEND_UNAVAILABLE', `${UNREACHABLE_HINT} (HTTP ${response.status})`)
  }
  throw new ApiError(String(response.status), response.statusText || `HTTP ${response.status}`)
}

async function request<T>(path: string, institutionId: string, init?: RequestInit): Promise<T> {
  const response = await send(path, institutionId, init)
  const text = await response.text()
  if (!text) return null as T
  try {
    return JSON.parse(text) as T
  } catch {
    return text as unknown as T
  }
}

/** Fetch a binary endpoint (a slide render) and expose it as an object URL. */
export async function fetchObjectUrl(institutionId: string, path: string): Promise<string> {
  const response = await send(path, institutionId)
  return URL.createObjectURL(await response.blob())
}

export const listCourses = (institutionId: string) => request<Course[]>('/courses', institutionId)

export const listMaterials = (institutionId: string, courseId: string) =>
  request<Material[]>(`/courses/${courseId}/materials`, institutionId)

export const createCourse = (institutionId: string, title: string) =>
  request<{ course_id: string; institution_id: string }>(
    `/courses?title=${encodeURIComponent(title)}`,
    institutionId,
    { method: 'POST' },
  )

export const uploadMaterial = (institutionId: string, courseId: string, file: File) => {
  const form = new FormData()
  form.append('file', file)
  return request<UploadResult>(`/courses/${courseId}/materials`, institutionId, {
    method: 'POST',
    body: form,
  })
}

export const extractArtifact = (institutionId: string, artifactId: string) =>
  request<ContentIR>(`/artifacts/${artifactId}/extract`, institutionId, { method: 'POST' })

// -- scheduled classes (V0-009) --------------------------------------------------
//
// The library lists classes so a classroom is reachable from the UI, not only by
// deep link. Scheduling a class is done by the runtime (`POST /classes`); the
// page reads, it does not create.

export interface ClassSummary {
  class_id: string
  institution_id: string
  course_id: string
  title: string
  version_id: string | null
  scheduled_for: string | null
  state: string
  created_at: string
  started_at: string | null
}

export const listClasses = (institutionId: string, limit = 100) =>
  request<ClassSummary[]>(`/classes?limit=${limit}`, institutionId)

/** Stored artifact metadata. The Teacher Studio shows the filename as its title. */
export interface ArtifactSummary {
  artifact_id: string
  course_id: string
  version_id: string
  filename: string
  media_type: string
  sha256: string
  byte_size: number
  object_key: string
  created_at: string
}

export const loadArtifact = (institutionId: string, artifactId: string) =>
  request<ArtifactSummary>(`/artifacts/${artifactId}`, institutionId)

// -- teacher review preview (V0-007) --------------------------------------------
export interface RendererIdentity {
  name: string
  version: string
  engine: string
  config_hash: string
  data_region: string
}

/** One slide exactly as it appears in the package under review (DEC-CONTENT-006). */
export interface ReviewScene {
  order: number
  scene_id: string
  fidelity: string | null
  render_status: 'RENDERED' | 'FAILED'
  fallback_asset: string | null
  render_url: string | null
  requires_review: boolean
  missing_fonts: string[]
  warnings: string[]
  notes: string | null
  text: string[]
  object_count: number
  step_count: number
  renderer: RendererIdentity | null
  source_ref: Record<string, unknown>
}

/** One entry of the fallback lesson order (DEC-CONTENT-007). */
export interface ReviewSection {
  order: number
  section_id: string
  type: string
  scene_id: string | null
  scene_step_id: string | null
  safe_markers: string[]
  script: string | null
  scene_fidelity: string | null
  requires_review: boolean
}

/**
 * Review projection of a built Baseline Content Package.
 *
 * `READY`/`REVIEW_REQUIRED` describe the *content*: whether a human must look at
 * it. The mutable overlay — the decision and the draft revisions — is
 * `ReviewState`. Nothing here is writable: a review action records state about
 * the package, and the publication transition is V0-008.
 */
export interface ReviewPackage {
  artifact_id: string
  package_id: string
  prefix: string
  course_id: string
  course_version: string
  content_package_version: string
  lesson_plan_version: string | null
  knowledge_index_version: string
  teaching_graph_version: string | null
  created_at: string
  state: 'READY' | 'REVIEW_REQUIRED' | 'BLOCKED'
  publishable: boolean
  requires_review: boolean
  scene_count: number
  file_count: number
  renderer: RendererIdentity | null
  placeholder_notice: string
  lesson_order: ReviewSection[]
  scenes: ReviewScene[]
}

/** Build (or rebuild) the package and return its review view. Slow: it renders. */
export const buildReviewPackage = (institutionId: string, artifactId: string) =>
  request<ReviewPackage>(`/artifacts/${artifactId}/review-package`, institutionId, {
    method: 'POST',
  })

/** Read the review view of the already-stored package. Fast: it never renders. */
export const loadReviewPackage = (institutionId: string, artifactId: string) =>
  request<ReviewPackage>(`/artifacts/${artifactId}/review-package`, institutionId)

// -- review actions (V0-007) -----------------------------------------------------
export type ReviewDecisionKind = 'APPROVE' | 'REJECT'

/** One recorded review outcome for one content version. */
export interface ReviewDecision {
  decision_id: string
  artifact_id: string
  version_id: string
  package_id: string
  content_package_version: string
  decision: ReviewDecisionKind
  reason: string | null
  reviewer: string
  created_at: string
}

/** One resolved entry of a draft revision; structure is inherited from the package. */
export interface ReviewDraftSection {
  order: number
  section_id: string
  type: string
  scene_id: string | null
  scene_step_id: string | null
  safe_markers: string[]
  script: string | null
}

/** One immutable revision of a proposed lesson order (append-only). */
export interface ReviewDraft {
  draft_id: string
  artifact_id: string
  version_id: string
  package_id: string
  content_package_version: string
  lesson_plan_version: string | null
  revision: number
  sections: ReviewDraftSection[]
  edited_by: string
  created_at: string
}

/**
 * The mutable review overlay: the current decision, the newest draft revision
 * and the blocking picture. `stale` means the decision no longer covers the
 * stored content version, so it must not be read as a current approval.
 */
export interface ReviewState {
  artifact_id: string
  version_id: string
  version_status: 'DRAFT' | 'PROCESSING' | 'REVIEW_REQUIRED' | 'APPROVED' | 'PUBLISHED' | 'ARCHIVED'
  package_id: string
  content_package_version: string
  state: 'READY' | 'REVIEW_REQUIRED' | 'BLOCKED'
  publishable: boolean
  requires_review: boolean
  stale: boolean
  blocking_scene_orders: number[]
  decision: ReviewDecision | null
  draft: ReviewDraft | null
  draft_count: number
}

export interface ReviewDecisionInput {
  decision: ReviewDecisionKind
  reason?: string | null
  reviewer?: string | null
}

export interface ReviewDraftInput {
  /** Array position *is* the proposed order. */
  sections: { section_id: string; script?: string | null }[]
  edited_by?: string | null
}

const JSON_POST = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const loadReviewState = (institutionId: string, artifactId: string) =>
  request<ReviewState>(`/artifacts/${artifactId}/review-package/review-state`, institutionId)

/** Approve or reject. A blocked document answers `PUBLICATION_BLOCKED`. */
export const postReviewDecision = (
  institutionId: string,
  artifactId: string,
  input: ReviewDecisionInput,
) =>
  request<ReviewState>(
    `/artifacts/${artifactId}/review-package/decision`,
    institutionId,
    JSON_POST(input),
  )

/** Append a draft revision. Never mutates the package. */
export const saveReviewDraft = (
  institutionId: string,
  artifactId: string,
  input: ReviewDraftInput,
) =>
  request<ReviewDraft>(
    `/artifacts/${artifactId}/review-package/drafts`,
    institutionId,
    JSON_POST(input),
  )

export const listReviewDrafts = (institutionId: string, artifactId: string) =>
  request<{ artifact_id: string; revisions: ReviewDraft[] }>(
    `/artifacts/${artifactId}/review-package/drafts`,
    institutionId,
  )

// -- classroom runtime (V0-011) --------------------------------------------------
//
// The classroom client (src/classroom/) reads the authoritative session snapshot
// and projects its state from it. These are the wire shapes of `GET
// /classes/{id}/snapshot`: the durable `runtime-snapshot@1` document plus its
// envelope (V0-009/V0-010). The document is what a refresh restores; it never
// becomes authoritative on the client.

export interface ClassroomCheckpoint {
  checkpoint_id: string
  scene_id: string | null
  step_id: string | null
  label: string | null
  final: boolean
  created_at: string
}

export interface ClassroomLessonPosition {
  lesson_plan_version?: string
  lesson_id?: string
  section_index: number | null
  section_id?: string | null
  scene_id: string | null
  scene_step_id?: string | null
}

export interface ClassroomTimeline {
  scene_id: string | null
  step_id: string | null
  checkpoint: ClassroomCheckpoint | null
}

export interface ClassroomTurn {
  queue: unknown[]
  floor: unknown | null
  stt_reservation: unknown | null
}

export interface ClassroomRuntimeVersions {
  course_id: string
  course_version: number
  version_id: string
  publication_id: string
  package_id: string
  content_package_version: string
  content_digest: string
  lesson_plan_version: string
  knowledge_index_version: string
  index_version_id: string
  index_source_digest: string
  teaching_graph_version: string | null
  assessment_version: string | null
  model_routing_version: string | null
  policy_version: string
  capability_version: string
  region: string
}

export interface ClassroomSnapshotDocument {
  schema_version: string
  institution_id: string
  course_id: string
  class_id: string
  session_id: string
  state: string
  actor_epoch: number
  state_version: number
  event_sequence: number
  versions: ClassroomRuntimeVersions
  lesson: ClassroomLessonPosition
  turn: ClassroomTurn
  timeline: ClassroomTimeline
  pending_effects: unknown[]
}

export interface SessionSnapshot {
  snapshot_id: string
  class_id: string
  session_id: string
  schema_version: string
  state: string
  state_version: number
  event_sequence: number
  actor_epoch: number
  checksum: string
  created_at: string
  document: ClassroomSnapshotDocument
}

/** Turn a failed request into a message that keeps the stable error code. */
export function describeApiError(cause: unknown): string {
  if (cause instanceof ApiError) {
    // The stable code says a request was refused; the `issue_code` says *why*
    // within that code (NOT_APPROVED vs STALE_APPROVAL, NOT_ENROLLED vs
    // NOT_STARTED). Both are shown: a page that hid the second would make two
    // very different refusals look the same. Neither is ever a raw exception.
    const detail = cause.issueCode ? ` (${cause.issueCode})` : ''
    return cause.message ? `${cause.code}: ${cause.message}${detail}` : `${cause.code}${detail}`
  }
  return cause instanceof Error ? cause.message : String(cause)
}

/** The authoritative session snapshot; a refreshed page restores from it. */
export const loadSnapshot = (institutionId: string, classId: string) =>
  request<SessionSnapshot>(`/classes/${classId}/snapshot`, institutionId)

// -- admin: classes, enrolments, publications, renderer (V0-008/V0-009) ----------
//
// Everything here maps onto an endpoint that already exists. The API has no
// generic update or delete: content is immutable and a publication is never
// deleted (`DEC-CONTENT-005`), so the "write" verbs are the domain's own
// append-only transitions — schedule, start, enrol, publish — plus create.

export interface ClassroomSessionSummary {
  session_id: string
  class_id: string
  course_id: string
  session_plan_id: string
  state: string
  actor_epoch: number
  state_version: number
  event_sequence: number
  snapshot_id: string | null
  created_at: string
  started_at: string
}

/** The resolved, pinned runtime tuple a started session runs on. */
export interface SessionPlanSummary {
  session_plan_id: string
  class_id: string
  versions: Record<string, unknown>
  capabilities: Record<string, unknown>
  created_at: string
}

export interface ClassView {
  class: ClassSummary
  session: ClassroomSessionSummary | null
  session_plan: SessionPlanSummary | null
}

export interface Enrollment {
  enrollment_id: string
  institution_id: string
  class_id: string
  student_id: string
  created_at: string
}

export interface ScheduleClassInput {
  course_id: string
  title?: string | null
  version_id?: string | null
  scheduled_for?: string | null
}

/** Schedule a class. A class is not run until it is started (V0-009). */
export const scheduleClass = (institutionId: string, input: ScheduleClassInput) => {
  const query = new URLSearchParams({ course_id: input.course_id })
  if (input.title) query.set('title', input.title)
  if (input.version_id) query.set('version_id', input.version_id)
  if (input.scheduled_for) query.set('scheduled_for', input.scheduled_for)
  return request<ClassSummary>(`/classes?${query.toString()}`, institutionId, { method: 'POST' })
}

export const loadClass = (institutionId: string, classId: string) =>
  request<ClassView>(`/classes/${classId}`, institutionId)

/** Start a class: pin the exact runtime tuple once and go `ACTIVE`. */
export const startClass = (institutionId: string, classId: string) =>
  request<ClassView & { created: boolean }>(`/classes/${classId}/start`, institutionId, {
    method: 'POST',
  })

export interface PublicationIntegrity {
  state: 'VERIFIED' | 'MISMATCH' | 'MISSING'
  package_id: string
  expected_digest: string
  [key: string]: unknown
}

export interface Publication {
  publication_id: string
  institution_id: string
  course_id: string
  version_id: string
  course_version: number
  artifact_id: string
  package_id: string
  content_package_version: string
  lesson_plan_versions: string[]
  knowledge_index_version: string
  teaching_graph_version: string | null
  index_version_id: string
  package_prefix: string
  manifest_sha256: string
  content_digest: string
  file_count: number
  total_bytes: number
  state: string
  superseded_by: string | null
  published_by: string
  created_at: string
  /** Present only when the read asked for verification (`?verify=true`). */
  integrity?: PublicationIntegrity
}

export const listPublications = (institutionId: string, courseId: string, limit = 50) =>
  request<{ course_id: string; publications: Publication[] }>(
    `/courses/${courseId}/publications?limit=${limit}`,
    institutionId,
  )

/** One publication by identity, superseded ones included. */
export const loadPublication = (institutionId: string, publicationId: string, verify = false) =>
  request<Publication>(
    `/publications/${publicationId}${verify ? '?verify=true' : ''}`,
    institutionId,
  )

export const loadVersionPublication = (institutionId: string, versionId: string, verify = false) =>
  request<Publication>(
    `/course-versions/${versionId}/publication${verify ? '?verify=true' : ''}`,
    institutionId,
  )

/** Seal, index and commit an approved version. Idempotent on the content. */
export const publishVersion = (institutionId: string, versionId: string, publishedBy?: string) =>
  request<Publication & { created: boolean }>(
    `/course-versions/${versionId}/publish`,
    institutionId,
    JSON_POST({ published_by: publishedBy ?? null }),
  )

/** Extract, render every slide and run the fidelity gate, for one mode. */
export const compileArtifact = (institutionId: string, artifactId: string, mode?: string) =>
  request<Record<string, unknown>>(
    `/artifacts/${artifactId}/compile${mode ? `?mode=${encodeURIComponent(mode)}` : ''}`,
    institutionId,
    { method: 'POST' },
  )

export interface RendererModeInfo {
  mode: string
  label: string
}

export interface RendererStatus {
  default_mode: string
  mode: string
  modes: RendererModeInfo[]
  identity: RendererIdentity
  support: Record<string, unknown>
  health: Record<string, unknown>
  theme: Record<string, unknown> | null
}

/** Renderer capability and circuit-breaker state (V0-005). */
export const loadRendererStatus = (institutionId: string, mode?: string) =>
  request<RendererStatus>(
    `/renderer${mode ? `?mode=${encodeURIComponent(mode)}` : ''}`,
    institutionId,
  )

/** Liveness. Needs no tenant: it reports the process, not a tenant's data. */
export const loadHealth = () => request<{ status: string }>('/health', '')

// -- identity (V0-021) ------------------------------------------------------------
//
// The session *is* the credential and it carries the tenant, so these calls pass
// no institution id. Signing in names the institution the account lives in
// (that is what the credential proves); every later request derives it from the
// session.

export interface LoginInput {
  institutionId: string
  email: string
  credential: string
}

export interface SessionIssuance {
  authenticated: boolean
  token: string
  token_type: string
  expires_at: string
  principal: Principal
  authenticator: CapabilityIdentity
  notice: string
}

/**
 * Sign in. A refusal is a stable code: `AUTHENTICATION_FAILED` with
 * `issue_code INVALID_CREDENTIALS` for a wrong credential *or* an unknown
 * account (deliberately indistinguishable), `AUTHENTICATION_UNAVAILABLE` when
 * the capability could not be reached — an availability failure is not a
 * denial, so the two are never conflated.
 */
export const login = (input: LoginInput) =>
  request<SessionIssuance>('/auth/login', '', JSON_POST({
    institution_id: input.institutionId,
    email: input.email,
    credential: input.credential,
  }))

/** Revoke the presented session. Idempotent, and never fails on an expired one. */
export const logout = () => request<{ revoked: boolean }>('/auth/logout', '', { method: 'POST' })

export interface PrincipalEnvelope {
  principal: Principal
  authenticator: CapabilityIdentity
  notice: string
  development_shortcut: boolean
}

/**
 * The principal the presented credential authorizes.
 *
 * The tenant header is sent when one is given, because that is how the
 * development shortcut resolves: with no session, `/auth/me` is the one call that
 * can tell a client *which mode it is in*. With a session it wins and the header
 * is ignored, so a signed-in read is unaffected.
 */
export const loadPrincipal = (institutionId = '') =>
  request<PrincipalEnvelope>('/auth/me', institutionId)

/** Turn an issuance into the session the client stores. */
export function sessionFrom(issuance: SessionIssuance): AuthSession {
  return {
    token: issuance.token,
    principal: issuance.principal,
    authenticator: issuance.authenticator,
    notice: issuance.notice,
    expiresAt: issuance.expires_at,
  }
}

// -- the teacher's roster (V0-021) ------------------------------------------------

/** A platform account, scoped to one institution. */
export interface Account {
  account_id: string
  institution_id: string
  email: string
  display_name: string
  role: string
  scopes: string[]
  status: string
  created_at: string
}

/** An enrolment with the account behind it, as the teacher's roster shows it. */
export interface RosterEntry extends Enrollment {
  student: Account | null
}

/**
 * Add a student to the class roster.
 *
 * With an `email` this is the teacher's **invitation**: the account is created in
 * this institution if it has none for that address, or linked if it has, and the
 * response carries a one-time sign-in code when the credential capability
 * provisions one (the development mock does; institutional federation would not).
 * Enrollment is the class-scoped authorization a join is checked against, and it
 * is idempotent: inviting the same student twice is one identity and one
 * enrolment.
 */
export const enrollStudentByEmail = (institutionId: string, classId: string, email: string) =>
  request<
    Enrollment & {
      student: Account
      account_created: boolean
      development_credential: string | null
      created: boolean
    }
  >(
    `/classes/${classId}/enrollments?email=${encodeURIComponent(email)}`,
    institutionId,
    { method: 'POST' },
  )

/** Enrol an account that already exists, by its id. */
export const enrollStudentById = (institutionId: string, classId: string, accountId: string) =>
  request<Enrollment & { student: Account; created: boolean }>(
    `/classes/${classId}/enrollments?student_id=${encodeURIComponent(accountId)}`,
    institutionId,
    { method: 'POST' },
  )

/** The roster, with the account each enrolment authorizes. A teacher capability. */
export const loadRoster = (institutionId: string, classId: string) =>
  request<{ class_id: string; enrollments: RosterEntry[] }>(
    `/classes/${classId}/enrollments`,
    institutionId,
  )

// -- the student's view of a running class (V0-021) -------------------------------

export interface BootstrapToken {
  token: string
  class_id: string
  session_id: string
  student_id: string
  actor_epoch: number
  nonce: string
  scopes: string[]
  issued_at: string
  expires_at: string
}

/**
 * Request the caller's **own** join credential.
 *
 * There is no student id in the request: the credential is bound to the session's
 * account, so it cannot be someone else's join. Joining is a *participant* action,
 * so a teacher — including the development shortcut, which is a teacher principal —
 * is refused `403 INSUFFICIENT_SCOPE`; for a student the refusals are precise —
 * `403 NOT_ENROLLED` when the account is not in this class, `409 CLASS_NOT_READY`
 * with `issue_code NOT_STARTED` when the class has not started.
 */
export const issueBootstrapToken = (classId: string) =>
  request<BootstrapToken>(`/classes/${classId}/bootstrap-token`, '', { method: 'POST' })

/** One slide of the package a session pinned, as the student page needs it. */
export interface ClassScene {
  order: number
  scene_id: string
  fidelity: string | null
  notes: string | null
  text: string[]
  warnings: string[]
  object_count: number
  step_count: number
}

export interface ClassSceneList {
  class_id: string
  package_id: string
  content_digest: string
  scene_count: number
  scenes: ClassScene[]
}

/** The slides of the pinned package, with their text. Never a `latest` lookup. */
export const loadClassScenes = (classId: string) =>
  request<ClassSceneList>(`/classes/${classId}/scenes`, '')

/** One slide's render, from the pinned package. */
export const classSceneUrl = (classId: string, order: number) =>
  fetchObjectUrl('', `/classes/${classId}/scenes/${order}`)
