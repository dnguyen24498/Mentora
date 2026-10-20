import { useCallback, useEffect, useRef, useState } from 'react'
import ContentIrView from '../components/ContentIrView'
import SiteNav from '../components/SiteNav'
import { BUTTON_PRIMARY, BUTTON_SMALL, INPUT_CLASS, PANEL_PADDING } from '../components/ui'
import { Link, classroomPath, learnPath, studioPath } from '../router'
import {
  ApiError,
  createCourse,
  extractArtifact,
  listClasses,
  listCourses,
  listMaterials,
  uploadMaterial,
  type ClassSummary,
  type ContentIR,
  type Course,
  type Material,
} from '../api/client'
import {
  readSelectedArtifact,
  readSelectedCourse,
  useInstitution,
  writeSelectedArtifact,
  writeSelectedCourse,
} from '../institution'

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

/**
 * The material library: create a course, upload a `.pptx`, pick an uploaded
 * file and see its extracted Content IR.
 *
 * The teacher **preview/review** flow lives on its own page
 * (`/studio/{artifactId}`, `pages/StudioPage.tsx`) rather than inline here:
 * reviewing slides is a different job from uploading them, and a dedicated page
 * gives the slide the whole viewport instead of one column of a card.
 */
export default function UploadPage() {
  const [institution, setInstitution] = useInstitution()
  const [courses, setCourses] = useState<Course[]>([])
  const [courseId, setCourseId] = useState(readSelectedCourse)
  const [newTitle, setNewTitle] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)
  const [extracting, setExtracting] = useState(false)
  const [loadingMaterials, setLoadingMaterials] = useState(false)
  const [error, setError] = useState<UiError | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [materials, setMaterials] = useState<Material[]>([])
  const [classes, setClasses] = useState<ClassSummary[]>([])
  const [loadingClasses, setLoadingClasses] = useState(false)
  const [classesError, setClassesError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  // The deck the shared nav links to. It is the one the teacher opened, or — on a
  // first visit, before anything has been opened — the newest deck in the course,
  // so Studio and Learn are usable straight away instead of pointing at the
  // library the teacher is already on.
  const [navArtifactId, setNavArtifactId] = useState<string>(() => readSelectedArtifact())
  const [ir, setIr] = useState<ContentIR | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const selected = materials.find((material) => material.artifact_id === selectedId) ?? null

  useEffect(() => {
    writeSelectedCourse(courseId)
  }, [courseId])

  // Remember the deck so the shared nav can reach its Studio and Learn pages
  // from anywhere else.
  useEffect(() => {
    if (!selectedId) return
    writeSelectedArtifact(selectedId)
    setNavArtifactId(selectedId)
  }, [selectedId])

  // A first visit has no remembered deck. The newest uploaded deck stands in, so
  // the nav is not a dead end; opening any deck replaces it.
  useEffect(() => {
    if (navArtifactId || materials.length === 0) return
    const newest = materials[0].artifact_id
    writeSelectedArtifact(newest)
    setNavArtifactId(newest)
  }, [materials, navArtifactId])

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

  // Classes are listed so a classroom is reachable from the UI. Scheduling still
  // belongs to the runtime (`POST /classes`); this page only reads.
  const refreshClasses = useCallback(async (inst: string) => {
    setLoadingClasses(true)
    setClassesError(null)
    try {
      setClasses(await listClasses(inst))
    } catch (cause) {
      setClassesError(
        cause instanceof ApiError ? `${cause.code}: ${cause.message}` : String(cause),
      )
    } finally {
      setLoadingClasses(false)
    }
  }, [])

  useEffect(() => {
    void refreshCourses(institution)
  }, [institution, refreshCourses])

  useEffect(() => {
    void refreshClasses(institution)
  }, [institution, refreshClasses])

  // Changing tenant or course switches which files are on screen, so drop the
  // previous selection and any extracted document with it.
  useEffect(() => {
    setSelectedId(null)
    setIr(null)
    setNotice(null)
    void refreshMaterials(institution, courseId)
  }, [institution, courseId, refreshMaterials])

  function pickFile(candidate: File | null | undefined) {
    if (!candidate) return
    setError(null)
    setIr(null)
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
    setError(null)
    await runExtract(material.artifact_id)
  }

  async function onUpload() {
    if (!file || !courseId) return
    setBusy(true)
    setError(null)
    setIr(null)
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
        <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6 sm:py-5">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <SiteNav current="library" artifactId={selectedId ?? navArtifactId} />
            <span className="ml-auto text-xs font-semibold uppercase tracking-wide text-slate-400">
              Mentora
            </span>
          </div>
          <h1 className="mt-3 text-lg font-semibold sm:text-xl">Mentora — Upload Course Material</h1>
          <p className="mt-1 text-sm text-slate-500">
            Upload a PowerPoint <code className="rounded bg-slate-100 px-1">.pptx</code> file: it is validated,
            stored immutably, recorded in SQLite, and can be structurally extracted.
          </p>
        </div>
      </header>

      <main className="mx-auto grid grid-cols-1 max-w-7xl gap-5 px-4 py-6 sm:gap-6 sm:px-6 sm:py-8 md:grid-cols-[360px_minmax(0,1fr)]">
        <section className={`space-y-5 self-start rounded-xl border border-slate-200 bg-white ${PANEL_PADDING} shadow-sm`}>
          <div>
            <label className="block text-sm font-medium text-slate-700" htmlFor="institution">
              Institution ID
            </label>
            <input
              id="institution"
              value={institution}
              onChange={(event) => setInstitution(event.target.value)}
              className={`mt-1 ${INPUT_CLASS}`}
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
              className={`mt-1 bg-white ${INPUT_CLASS}`}
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
              className={`min-w-0 ${INPUT_CLASS}`}
            />
            <button
              type="button"
              onClick={() => void onCreateCourse()}
              disabled={busy || !newTitle.trim()}
              className="shrink-0 rounded-lg bg-slate-800 px-3 py-2 text-sm font-medium text-white disabled:opacity-40 min-h-11 lg:min-h-0"
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
            className={`${BUTTON_PRIMARY} w-full`}
          >
            {busy ? 'Working…' : 'Upload'}
          </button>

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              <span className="font-mono font-semibold">{error.code}</span>: {error.message}
            </div>
          )}
        </section>

        <section className={`space-y-5 self-start rounded-xl border border-slate-200 bg-white ${PANEL_PADDING} shadow-sm`}>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Uploaded files</h2>
            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600">
              {materials.length}
            </span>
            <button
              type="button"
              onClick={() => void refreshMaterials(institution, courseId)}
              disabled={!courseId || loadingMaterials}
              className={`ml-auto ${BUTTON_SMALL}`}
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
              <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-sm">
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
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <button
                  type="button"
                  onClick={() => void runExtract(selected.artifact_id)}
                  disabled={extracting}
                  className="inline-flex min-h-11 items-center justify-center rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-medium text-slate-700 disabled:opacity-40 lg:min-h-0 lg:py-2"
                >
                  {extracting ? 'Extracting…' : 'Extract structure again'}
                </button>
                {/* A real link: the studio is a page, and opens in its own tab. */}
                <Link
                  to={studioPath(selected.artifact_id)}
                  className="inline-flex min-h-11 items-center justify-center rounded-lg bg-indigo-600 px-4 py-2.5 text-center text-sm font-semibold text-white lg:min-h-0 lg:py-2"
                >
                  Open Teacher Studio
                </Link>
              </div>
              {/* The learning page: the slide plus the teaching canvas. */}
              <Link
                to={learnPath(selected.artifact_id)}
                className="flex min-h-11 items-center justify-center rounded-lg border border-indigo-600 px-4 py-2.5 text-center text-sm font-semibold text-indigo-700 hover:bg-indigo-50 lg:min-h-0 lg:py-2"
              >
                Open learning page
              </Link>
              <p className="text-[11px] text-slate-400">
                <a
                  href={studioPath(selected.artifact_id)}
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium text-indigo-600 underline"
                >
                  Open the Teacher Studio in a new tab ↗
                </a>{' '}
                for a full-screen slide preview.
              </p>
            </div>
          )}

          {ir && (
            <div className="border-t border-slate-100 pt-3">
              <ContentIrView document={ir} />
            </div>
          )}
        </section>

        {/* The third page of the app: a class's classroom. Listed here so it is
            reachable without knowing the id for a deep link. */}
        <section className={`space-y-3 self-start rounded-xl border border-slate-200 bg-white ${PANEL_PADDING} shadow-sm md:col-span-2`}>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Classes</h2>
            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600">
              {classes.length}
            </span>
            <button
              type="button"
              onClick={() => void refreshClasses(institution)}
              disabled={loadingClasses}
              className={`ml-auto ${BUTTON_SMALL}`}
            >
              {loadingClasses ? 'Loading…' : 'Refresh'}
            </button>
          </div>
          <p className="text-xs text-slate-400">
            Classes scheduled for this institution. Each opens its own classroom page.
          </p>
          {classesError && <p className="text-xs text-rose-700">{classesError}</p>}
          {!loadingClasses && !classesError && classes.length === 0 && (
            <p className="text-sm text-slate-400">
              No classes yet — a class is scheduled through the runtime API (
              <code className="rounded bg-slate-100 px-1">POST /classes</code>).
            </p>
          )}
          {classes.length > 0 && (
            <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {classes.map((item) => (
                <li key={item.class_id}>
                  <Link
                    to={classroomPath(item.class_id)}
                    className="flex h-full flex-col gap-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-left transition hover:bg-slate-50"
                  >
                    <span className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium text-slate-800">{item.title}</span>
                      <span className="ml-auto shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600">
                        {item.state}
                      </span>
                    </span>
                    <span className="truncate font-mono text-[10px] text-slate-400">{item.class_id}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </div>
  )
}
