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

async function request<T>(path: string, institutionId: string, init?: RequestInit): Promise<T> {
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

  const text = await response.text()
  let body: unknown = null
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = text
    }
  }

  if (!response.ok) {
    const error =
      body && typeof body === 'object' ? (body as { error?: { code?: string; message?: string } }).error : undefined
    if (error?.code) {
      throw new ApiError(error.code, error.message ?? response.statusText)
    }
    if (response.status >= 500 && !text.trim()) {
      // A 5xx with an empty body means the request never reached the API.
      throw new ApiError('BACKEND_UNAVAILABLE', `${UNREACHABLE_HINT} (HTTP ${response.status})`)
    }
    throw new ApiError(String(response.status), response.statusText || `HTTP ${response.status}`)
  }
  return body as T
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
