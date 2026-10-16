export class ApiError extends Error {
  code: string

  constructor(code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.code = code
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

export interface TextParagraph {
  level: number
  text: string
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
}

export interface SlideScene {
  scene_id: string
  order: number
  notes: string | null
  objects: ShapeObject[]
  warnings: string[]
  fidelity: string
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
  headers.set('X-Institution-Id', institutionId)

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
      ? (body as { error?: { code?: string; message?: string } }).error
      : undefined
  if (error?.code) {
    throw new ApiError(error.code, error.message ?? response.statusText)
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
