import { useCallback, useEffect, useState } from 'react'
import { Link, learnPath, studioPath } from '../router'
import {
  compileArtifact,
  createCourse,
  describeApiError,
  listCourses,
  listMaterials,
  loadArtifact,
  uploadMaterial,
  type ArtifactSummary,
  type Course,
  type Material,
} from '../api/client'
import { readSelectedCourse, writeSelectedArtifact, writeSelectedCourse } from '../institution'
import { useSettings } from '../settings/store'
import {
  Badge,
  Banner,
  BUTTON_PRIMARY,
  BUTTON_SECONDARY,
  BUTTON_SMALL,
  EmptyState,
  INPUT_CLASS,
  Panel,
  Row,
  type Tone,
} from '../components/ui'

const JOB_TONE: Record<string, Tone> = {
  PENDING: 'warn',
  EXTRACTED: 'good',
  FAILED: 'bad',
}

interface CompileSummary {
  publishable: boolean
  requires_review: boolean
  scene_count: number
}

function summariseCompile(result: Record<string, unknown>): CompileSummary | null {
  const validation = result.validation as Record<string, unknown> | undefined
  if (!validation) return null
  return {
    publishable: Boolean(validation.publishable),
    requires_review: Boolean(validation.requires_review),
    scene_count: Number(validation.scene_count ?? 0),
  }
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`
}

/**
 * Courses and their materials — the admin view.
 *
 * Create a course, upload a deck into it, and act on a deck: compile it (in the
 * render mode chosen in Settings), inspect its stored metadata, or hand it to the
 * Teacher Studio / learning page. Nothing here edits a stored artifact — an
 * artifact is immutable and a new upload is a new version (that is why the
 * actions are "compile" and "open", never "rename" or "delete").
 */
export default function CoursesAdmin({ institutionId }: { institutionId: string }) {
  const [settings] = useSettings()
  const [courses, setCourses] = useState<Course[]>([])
  const [courseId, setCourseId] = useState(readSelectedCourse)
  const [materials, setMaterials] = useState<Material[]>([])
  const [newTitle, setNewTitle] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [detail, setDetail] = useState<ArtifactSummary | null>(null)

  useEffect(() => {
    writeSelectedCourse(courseId)
  }, [courseId])

  const refreshCourses = useCallback(async () => {
    try {
      const loaded = await listCourses(institutionId)
      setCourses(loaded)
      setCourseId((previous) =>
        previous && loaded.some((course) => course.course_id === previous)
          ? previous
          : (loaded[0]?.course_id ?? ''),
      )
      return loaded
    } catch (cause) {
      setError(describeApiError(cause))
      return []
    }
  }, [institutionId])

  const refreshMaterials = useCallback(
    async (course: string) => {
      if (!course) {
        setMaterials([])
        return
      }
      try {
        setMaterials(await listMaterials(institutionId, course))
      } catch (cause) {
        setError(describeApiError(cause))
      }
    },
    [institutionId],
  )

  useEffect(() => {
    setError(null)
    setNotice(null)
    setDetail(null)
    void refreshCourses()
  }, [institutionId, refreshCourses])

  useEffect(() => {
    setDetail(null)
    void refreshMaterials(courseId)
  }, [courseId, refreshMaterials])

  async function create() {
    if (!newTitle.trim()) return
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const created = await createCourse(institutionId, newTitle.trim())
      setNewTitle('')
      await refreshCourses()
      setCourseId(created.course_id)
      setNotice('Course created.')
    } catch (cause) {
      setError(describeApiError(cause))
    } finally {
      setBusy(false)
    }
  }

  async function upload() {
    if (!file || !courseId) return
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const uploaded = await uploadMaterial(institutionId, courseId, file)
      setFile(null)
      await refreshMaterials(courseId)
      writeSelectedArtifact(uploaded.artifact_id)
      setNotice(
        uploaded.created
          ? `Uploaded ${uploaded.filename} as a new version (${uploaded.artifact_id}).`
          : `${uploaded.filename} is already stored (identical bytes) — reusing the existing version.`,
      )
    } catch (cause) {
      setError(describeApiError(cause))
    } finally {
      setBusy(false)
    }
  }

  async function compile(artifact: Material) {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const result = await compileArtifact(institutionId, artifact.artifact_id, settings.renderMode)
      const summary = summariseCompile(result)
      setNotice(
        summary
          ? `Compiled ${artifact.filename} in ${settings.renderMode} mode: ${summary.scene_count} scene(s), ` +
            `${summary.publishable ? 'publishable' : 'blocked'}` +
            `${summary.requires_review ? ', review required' : ''}.`
          : `Compiled ${artifact.filename} in ${settings.renderMode} mode.`,
      )
    } catch (cause) {
      setError(describeApiError(cause))
    } finally {
      setBusy(false)
    }
  }

  async function openDetail(artifactId: string) {
    setError(null)
    writeSelectedArtifact(artifactId)
    try {
      setDetail(await loadArtifact(institutionId, artifactId))
    } catch (cause) {
      setError(describeApiError(cause))
    }
  }

  return (
    <div className="mx-auto grid max-w-7xl gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
      <Panel title="Courses">
        <div className="flex gap-2">
          <input
            aria-label="New course title"
            value={newTitle}
            onChange={(event) => setNewTitle(event.target.value)}
            onKeyDown={(event) => event.key === 'Enter' && void create()}
            placeholder="New course title"
            className={INPUT_CLASS}
          />
          <button
            type="button"
            onClick={() => void create()}
            disabled={busy || !newTitle.trim()}
            className={`${BUTTON_PRIMARY} shrink-0`}
          >
            Create
          </button>
        </div>

        <ul className="space-y-1.5">
          {courses.map((course) => {
            const active = course.course_id === courseId
            return (
              <li key={course.course_id}>
                <button
                  type="button"
                  onClick={() => setCourseId(course.course_id)}
                  aria-pressed={active}
                  className={`flex w-full flex-col gap-0.5 rounded-lg border px-3 py-2 text-left ${
                    active ? 'border-indigo-500 bg-indigo-50' : 'border-slate-200 hover:bg-slate-50'
                  }`}
                >
                  <span className="text-sm font-medium text-slate-800">{course.title}</span>
                  <span className="truncate font-mono text-[10px] text-slate-400">
                    {course.course_id}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
        {courses.length === 0 && <EmptyState>No courses yet.</EmptyState>}
      </Panel>

      <div className="space-y-6">
        <Panel
          title="Materials"
          actions={
            <button
              type="button"
              onClick={() => void refreshMaterials(courseId)}
              disabled={!courseId}
              className={BUTTON_SMALL}
            >
              Refresh
            </button>
          }
        >
          <div className="flex flex-wrap items-end gap-2">
            <div className="min-w-0 flex-1 sm:min-w-[220px]">
              <label htmlFor="material" className="block text-sm font-medium text-slate-700">
                Upload a .pptx
              </label>
              <input
                id="material"
                type="file"
                accept=".pptx"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                className="mt-1 w-full text-base lg:text-xs"
              />
            </div>
            <button
              type="button"
              onClick={() => void upload()}
              disabled={busy || !file || !courseId}
              className={BUTTON_PRIMARY}
            >
              {busy ? 'Working…' : 'Upload'}
            </button>
          </div>
          <p className="text-[11px] text-slate-400">
            Bytes are content-addressed: uploading the same file again reuses the stored version
            rather than storing a second copy.
          </p>

          {error && <Banner tone="bad">{error}</Banner>}
          {notice && <Banner tone="good">{notice}</Banner>}

          {!courseId && <EmptyState>Select a course to see its materials.</EmptyState>}
          {courseId && materials.length === 0 && <EmptyState>No material in this course yet.</EmptyState>}

          {materials.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-left text-xs">
                <thead className="text-[10px] uppercase tracking-wide text-slate-400">
                  <tr>
                    <th className="py-1 pr-3">File</th>
                    <th className="py-1 pr-3">Version</th>
                    <th className="py-1 pr-3">Size</th>
                    <th className="py-1 pr-3">Job</th>
                    <th className="py-1">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {materials.map((material) => (
                    <tr key={material.artifact_id} className="border-t border-slate-100">
                      <td className="py-2 pr-3">
                        <span className="font-medium text-slate-800">{material.filename}</span>
                        <span className="block truncate font-mono text-[10px] text-slate-400">
                          {material.artifact_id}
                        </span>
                      </td>
                      <td className="py-2 pr-3 font-mono">v{material.version}</td>
                      <td className="py-2 pr-3">{formatBytes(material.byte_size)}</td>
                      <td className="py-2 pr-3">
                        <Badge tone={JOB_TONE[material.job_status] ?? 'neutral'}>
                          {material.job_status}
                        </Badge>
                      </td>
                      <td className="py-2">
                        <div className="flex flex-wrap gap-1">
                          <Link
                            to={studioPath(material.artifact_id)}
                            className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50 lg:px-1.5 lg:py-0.5"
                          >
                            Studio
                          </Link>
                          <Link
                            to={learnPath(material.artifact_id)}
                            className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50 lg:px-1.5 lg:py-0.5"
                          >
                            Learn
                          </Link>
                          <button
                            type="button"
                            onClick={() => void openDetail(material.artifact_id)}
                            className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50 lg:px-1.5 lg:py-0.5"
                          >
                            Details
                          </button>
                          <button
                            type="button"
                            onClick={() => void compile(material)}
                            disabled={busy}
                            className="rounded border border-slate-300 px-2 py-1 font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40 lg:px-1.5 lg:py-0.5"
                          >
                            Compile
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        {detail && (
          <Panel
            title="Artifact"
            actions={
              <button type="button" onClick={() => setDetail(null)} className={BUTTON_SECONDARY}>
                Close
              </button>
            }
          >
            <dl className="space-y-1 text-sm">
              <Row label="Artifact">{detail.artifact_id}</Row>
              <Row label="Version">{detail.version_id}</Row>
              <Row label="Filename">{detail.filename}</Row>
              <Row label="Media type">{detail.media_type}</Row>
              <Row label="SHA-256">{detail.sha256}</Row>
              <Row label="Size">{formatBytes(detail.byte_size)}</Row>
              <Row label="Object key">{detail.object_key}</Row>
              <Row label="Created">{detail.created_at}</Row>
            </dl>
          </Panel>
        )}
      </div>
    </div>
  )
}
