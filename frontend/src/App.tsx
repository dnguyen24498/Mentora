import { useCallback, useEffect, useRef, useState } from 'react'
import ContentIrView from './components/ContentIrView'
import ReviewPreview from './components/ReviewPreview'
import {
  ApiError,
  buildReviewPackage,
  createCourse,
  extractArtifact,
  listCourses,
  listMaterials,
  loadReviewPackage,
  uploadMaterial,
  type ContentIR,
  type Course,
  type Material,
  type ReviewPackage,
} from './api/client'

const DEFAULT_INSTITUTION = 'university-001'

interface UiError {
  code: string
  message: string
}

const STATUS_STYLE: Record<string, string> = {
  PENDING: 'bg-amber-100 text-amber-700',
  EXTRACTED: 'bg-emerald-100 text-emerald-700',
  FAILED: 'bg-rose-100 text-rose-700',
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`
}

function formatWhen(iso: string): string {
  const parsed = new Date(iso)
  return Number.isNaN(parsed.getTime()) ? iso : parsed.toLocaleString()
}

export default function App() {
  const [institution, setInstitution] = useState(
    () => localStorage.getItem('mentora.institution') ?? DEFAULT_INSTITUTION,
  )
  const [courses, setCourses] = useState<Course[]>([])
  const [courseId, setCourseId] = useState('')
  const [newTitle, setNewTitle] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)
  const [extracting, setExtracting] = useState(false)
  const [loadingMaterials, setLoadingMaterials] = useState(false)
  const [error, setError] = useState<UiError | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [materials, setMaterials] = useState<Material[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [ir, setIr] = useState<ContentIR | null>(null)
  const [review, setReview] = useState<ReviewPackage | null>(null)
  const [reviewNotice, setReviewNotice] = useState<string | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const selected = materials.find((material) => material.artifact_id === selectedId) ?? null

  useEffect(() => {
    localStorage.setItem('mentora.institution', institution)
  }, [institution])

  const fail = useCallback((cause: unknown) => {
    if (cause instanceof ApiError) setError({ code: cause.code, message: cause.message })
    else setError({ code: 'ERROR', message: cause instanceof Error ? cause.message : String(cause) })
  }, [])

  const refreshCourses = useCallback(
    async (inst: string) => {
      try {
        const list = await listCourses(inst)
        setCourses(list)
        setCourseId((prev) =>
          prev && list.some((course) => course.course_id === prev) ? prev : (list[0]?.course_id ?? ''),
        )
      } catch (cause) {
        fail(cause)
      }
    },
    [fail],
  )

  const refreshMaterials = useCallback(
    async (inst: string, course: string) => {
      if (!course) {
        setMaterials([])
        return
      }
      setLoadingMaterials(true)
      try {
        setMaterials(await listMaterials(inst, course))
      } catch (cause) {
        fail(cause)
      } finally {
        setLoadingMaterials(false)
      }
    },
    [fail],
  )

  useEffect(() => {
    void refreshCourses(institution)
  }, [institution, refreshCourses])

  // Changing tenant or course switches which files are on screen, so drop the
  // previous selection and any extracted document with it.
  useEffect(() => {
    setSelectedId(null)
    setIr(null)
    setReview(null)
    setReviewNotice(null)
    setNotice(null)
    void refreshMaterials(institution, courseId)
  }, [institution, courseId, refreshMaterials])

  function pickFile(candidate: File | null | undefined) {
    if (!candidate) return
    setError(null)
    setIr(null)
    setReview(null)
    setReviewNotice(null)
    setNotice(null)
    setFile(candidate)
    if (!candidate.name.toLowerCase().endsWith('.pptx')) {
      setError({
        code: 'UNSUPPORTED_EXTENSION',
        message: 'Only .pptx (OOXML) files are supported; legacy .ppt is rejected by the backend.',
      })
    }
  }

  async function onCreateCourse() {
    const title = newTitle.trim()
    if (!title) return
    setBusy(true)
    setError(null)
    try {
      const created = await createCourse(institution, title)
      setNewTitle('')
      await refreshCourses(institution)
      setCourseId(created.course_id)
    } catch (cause) {
      fail(cause)
    } finally {
      setBusy(false)
    }
  }

  async function runExtract(artifactId: string) {
    setExtracting(true)
    setError(null)
    try {
      setIr(await extractArtifact(institution, artifactId))
      setMaterials((previous) =>
        previous.map((material) =>
          material.artifact_id === artifactId ? { ...material, job_status: 'EXTRACTED' } : material,
        ),
      )
    } catch (cause) {
      fail(cause)
    } finally {
      setExtracting(false)
    }
  }

  /** Selecting a file is the "show me this one" action: load it and extract it. */
  async function onSelectMaterial(material: Material) {
    setSelectedId(material.artifact_id)
    setNotice(null)
    setIr(null)
    setReview(null)
    setReviewNotice(null)
    setError(null)
    await runExtract(material.artifact_id)
  }

  /**
   * Preview slides (V0-007). The stored package is preferred, because building
   * one re-renders every slide (~seconds for a real deck); the first preview of a
   * file therefore builds it and later previews are instant.
   */
  async function onPreview(artifactId: string) {
    setPreviewing(true)
    setError(null)
    setReviewNotice(null)
    try {
      try {
        const stored = await loadReviewPackage(institution, artifactId)
        setReview(stored)
        setReviewNotice('Loaded the package already built for this file (no re-render).')
      } catch (cause) {
        if (!(cause instanceof ApiError) || cause.code !== 'NOT_FOUND') throw cause
        setReview(await buildReviewPackage(institution, artifactId))
        setReviewNotice('Built a new package: every slide was rendered and validated.')
      }
    } catch (cause) {
      fail(cause)
    } finally {
      setPreviewing(false)
    }
  }

  /** Force a rebuild (re-render + revalidate + rewrite the package). */
  async function onRebuildReview(artifactId: string) {
    setPreviewing(true)
    setError(null)
    setReviewNotice(null)
    try {
      setReview(await buildReviewPackage(institution, artifactId))
      setReviewNotice('Rebuilt the package: every slide was rendered and validated again.')
    } catch (cause) {
      fail(cause)
    } finally {
      setPreviewing(false)
    }
  }

  async function onUpload() {
    if (!file || !courseId) return
    setBusy(true)
    setError(null)
    setIr(null)
    setReview(null)
    setReviewNotice(null)
    setNotice(null)
    try {
      const uploaded = await uploadMaterial(institution, courseId, file)
      await refreshMaterials(institution, courseId)
      setSelectedId(uploaded.artifact_id)
      setNotice(
        uploaded.created
          ? `Uploaded ${uploaded.filename} as a new version.`
          : `${uploaded.filename} is already stored (identical bytes) — showing the existing file.`,
      )
      await runExtract(uploaded.artifact_id)
    } catch (cause) {
      fail(cause)
    } finally {
      setBusy(false)
    }
  }

  const canUpload = Boolean(file && courseId) && !busy

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-7xl px-6 py-5">
          <h1 className="text-xl font-semibold">Mentora — Upload Course Material</h1>
          <p className="mt-1 text-sm text-slate-500">
            Upload a PowerPoint <code className="rounded bg-slate-100 px-1">.pptx</code> file: it is validated,
            stored immutably, recorded in SQLite, and can be structurally extracted.
          </p>
        </div>
      </header>

      <main className="mx-auto grid max-w-7xl gap-6 px-6 py-8 md:grid-cols-[360px_minmax(0,1fr)]">
        <section className="space-y-5 self-start rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div>
            <label className="block text-sm font-medium text-slate-700" htmlFor="institution">
              Institution ID
            </label>
            <input
              id="institution"
              value={institution}
              onChange={(event) => setInstitution(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            />
            <p className="mt-1 text-xs text-slate-400">Sent as the X-Institution-Id tenant header.</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700" htmlFor="course">
              Course
            </label>
            <select
              id="course"
              value={courseId}
              onChange={(event) => setCourseId(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            >
              {courses.length === 0 && <option value="">No courses yet — create one below</option>}
              {courses.map((course) => (
                <option key={course.course_id} value={course.course_id}>
                  {course.title}
                </option>
              ))}
            </select>
          </div>

          <div className="flex gap-2">
            <input
              value={newTitle}
              onChange={(event) => setNewTitle(event.target.value)}
              onKeyDown={(event) => event.key === 'Enter' && void onCreateCourse()}
              placeholder="New course title"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            />
            <button
              type="button"
              onClick={() => void onCreateCourse()}
              disabled={busy || !newTitle.trim()}
              className="shrink-0 rounded-lg bg-slate-800 px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
            >
              Create
            </button>
          </div>

          <label
            onDragOver={(event) => {
              event.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault()
              setDragging(false)
              pickFile(event.dataTransfer.files?.[0])
            }}
            className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 py-8 text-center transition ${
              dragging ? 'border-indigo-500 bg-indigo-50' : 'border-slate-300 bg-slate-50 hover:bg-slate-100'
            }`}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".pptx"
              className="hidden"
              onChange={(event) => pickFile(event.target.files?.[0])}
            />
            <span className="text-sm font-medium text-slate-700">
              {file ? file.name : 'Drop a .pptx here or click to browse'}
            </span>
            {file && (
              <span className="mt-1 text-xs text-slate-500">{(file.size / 1024).toFixed(1)} KiB</span>
            )}
          </label>

          <button
            type="button"
            onClick={() => void onUpload()}
            disabled={!canUpload}
            className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-40"
          >
            {busy ? 'Working…' : 'Upload'}
          </button>

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              <span className="font-mono font-semibold">{error.code}</span>: {error.message}
            </div>
          )}
        </section>

        <section className="space-y-5 self-start rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Uploaded files</h2>
            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600">
              {materials.length}
            </span>
            <button
              type="button"
              onClick={() => void refreshMaterials(institution, courseId)}
              disabled={!courseId || loadingMaterials}
              className="ml-auto rounded-md border border-slate-300 px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
            >
              {loadingMaterials ? 'Loading…' : 'Refresh'}
            </button>
          </div>

          <p className="text-xs text-slate-400">
            Select a file to see its stored details and its extracted content.
          </p>

          {!courseId && <p className="text-sm text-slate-400">Select a course to see its uploaded files.</p>}

          {courseId && !loadingMaterials && materials.length === 0 && (
            <p className="text-sm text-slate-400">No presentations uploaded to this course yet.</p>
          )}

          {materials.length > 0 && (
            <ul className="space-y-1.5">
              {materials.map((material) => {
                const active = material.artifact_id === selectedId
                return (
                  <li key={material.artifact_id}>
                    <button
                      type="button"
                      onClick={() => void onSelectMaterial(material)}
                      aria-pressed={active}
                      className={`flex w-full flex-col gap-0.5 rounded-lg border px-3 py-2 text-left transition ${
                        active
                          ? 'border-indigo-500 bg-indigo-50'
                          : 'border-slate-200 bg-white hover:bg-slate-50'
                      }`}
                    >
                      <span className="flex w-full items-center gap-2">
                        <span className="truncate text-sm font-medium text-slate-800">
                          {material.filename}
                        </span>
                        <span
                          className={`ml-auto shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                            STATUS_STYLE[material.job_status] ?? 'bg-slate-100 text-slate-600'
                          }`}
                        >
                          {material.job_status}
                        </span>
                      </span>
                      <span className="text-[11px] text-slate-500">
                        v{material.version} · {formatBytes(material.byte_size)} ·{' '}
                        {formatWhen(material.created_at)}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          )}

          {notice && (
            <p className="rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-xs text-indigo-800">
              {notice}
            </p>
          )}

          {selected && (
            <div className="space-y-3 border-t border-slate-100 pt-3">
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                <dt className="text-slate-500">File</dt>
                <dd className="truncate text-xs">{selected.filename}</dd>
                <dt className="text-slate-500">Artifact</dt>
                <dd className="truncate font-mono text-xs">{selected.artifact_id}</dd>
                <dt className="text-slate-500">Version</dt>
                <dd className="truncate font-mono text-xs">
                  {selected.version_id} (v{selected.version})
                </dd>
                <dt className="text-slate-500">Job</dt>
                <dd className="truncate font-mono text-xs">
                  {selected.job_id} ({selected.job_status})
                </dd>
                <dt className="text-slate-500">SHA-256</dt>
                <dd className="truncate font-mono text-xs">{selected.sha256}</dd>
                <dt className="text-slate-500">Size</dt>
                <dd className="text-xs">
                  {formatBytes(selected.byte_size)} ({selected.byte_size.toLocaleString()} bytes)
                </dd>
                <dt className="text-slate-500">Uploaded</dt>
                <dd className="text-xs">{formatWhen(selected.created_at)}</dd>
              </dl>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => void runExtract(selected.artifact_id)}
                  disabled={extracting}
                  className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-40"
                >
                  {extracting ? 'Extracting…' : 'Extract structure again'}
                </button>
                <button
                  type="button"
                  onClick={() => void onPreview(selected.artifact_id)}
                  disabled={previewing}
                  className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
                >
                  {previewing ? 'Rendering…' : 'Preview slides'}
                </button>
              </div>
            </div>
          )}

          {reviewNotice && (
            <p className="rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-xs text-indigo-800">
              {reviewNotice}
            </p>
          )}

          {review && (
            <div className="border-t border-slate-100 pt-3">
              <div className="mb-2 flex justify-end">
                <button
                  type="button"
                  onClick={() => review && void onRebuildReview(review.artifact_id)}
                  disabled={previewing}
                  className="rounded-md border border-slate-300 px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                >
                  Rebuild package
                </button>
              </div>
              <ReviewPreview institutionId={institution} review={review} />
            </div>
          )}

          {ir && (
            <div className="border-t border-slate-100 pt-3">
              <ContentIrView document={ir} />
            </div>
          )}
        </section>
      </main>
    </div>
  )
}
