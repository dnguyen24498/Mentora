import { useCallback, useEffect, useRef, useState } from 'react'
import ContentIrView from '../components/ContentIrView'
import PageHeader from '../components/PageHeader'
import { BUTTON_PRIMARY, BUTTON_SECONDARY, BUTTON_SMALL, INPUT_CLASS } from '../components/ui'
import { Link, classroomPath, studioPath } from '../router'
import {
  ApiError,
  autoPublishArtifact,
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
  // so Studio is usable straight away instead of pointing at the library the
  // teacher is already on.
  const [navArtifactId, setNavArtifactId] = useState<string>(() => readSelectedArtifact())
  const [ir, setIr] = useState<ContentIR | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const selected = materials.find((material) => material.artifact_id === selectedId) ?? null

  useEffect(() => {
    writeSelectedCourse(courseId)
  }, [courseId])

  // Remember the deck so the shared nav can reach its Studio page from anywhere
  // else.
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
      const stored = uploaded.created
        ? `Uploaded ${uploaded.filename} as a new version.`
        : `${uploaded.filename} is already stored (identical bytes) — showing the existing file.`
      setNotice(`${stored} Rendering the slides and publishing under your account…`)
      await runExtract(uploaded.artifact_id)

      // A teacher no longer has to visit Teacher Studio and Admin → Publications
      // just to make an ordinary deck teachable. The server still applies the
      // review policy: only an auto-allowed package becomes visible here.
      try {
        const auto = await autoPublishArtifact(institution, uploaded.artifact_id)
        if (auto.published && auto.publication) {
          setNotice(
            `${stored} Published automatically as version ${auto.publication.course_version}` +
              (auto.created ? '.' : ' (it was already published).') +
              ' It is ready to use in a class.',
          )
        } else if (auto.requires_review) {
          setNotice(
            `${stored} Saved, but it needs a teacher review before publication. ` +
              'Open Teacher Studio to review it, then publish it from Admin → Publications.',
          )
        } else {
          setNotice(`${stored} Saved, but it was not published automatically.`)
        }
      } catch (cause) {
        setNotice(`${stored} Saved, but automatic publication did not complete.`)
        fail(cause)
      }
    } catch (cause) {
      fail(cause)
    } finally {
      setBusy(false)
    }
  }

  const canUpload = Boolean(file && courseId) && !busy

  return (
    <div className="min-h-screen bg-academic-canvas text-slate-900 bg-academic-grid">
      <PageHeader
        nav="library"
        title="Upload Course Material"
        subtitle="Mentora"
        artifactId={selectedId ?? navArtifactId}
        institution={institution}
        onInstitutionChange={setInstitution}
      />

      <div className="mx-auto max-w-7xl px-4 pt-6 pb-2 sm:px-6">
        <div className="rounded-2xl border border-indigo-100/80 bg-gradient-to-r from-slate-900 via-indigo-950 to-blue-950 p-6 text-white shadow-sm sm:p-7">
          <div className="max-w-3xl">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-indigo-200">
              <svg className="h-3.5 w-3.5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
              </svg>
              Courseware & Syllabus Repository
            </span>
            <h2 className="mt-2 text-xl font-bold tracking-tight text-white sm:text-2xl">
              Course Material Ingestion & Slide Engine
            </h2>
            <p className="mt-1 text-xs text-indigo-200/90 leading-relaxed">
              Upload PowerPoint <code className="rounded bg-white/10 px-1 font-mono text-indigo-100">.pptx</code> lecture decks to extract semantic Content IR, render vector visuals, and publish verified teaching packages.
            </p>
          </div>
        </div>
      </div>

      <main className="mx-auto grid grid-cols-1 max-w-7xl gap-5 px-4 py-4 sm:gap-6 sm:px-6 sm:py-6 md:grid-cols-[380px_minmax(0,1fr)]">
        <section className={`space-y-4 self-start rounded-2xl border border-slate-200/85 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.03),0_4px_12px_rgba(0,0,0,0.02)]`}>
          <div className="border-b border-slate-100 pb-2.5">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-600">
              Select or Create Course
            </h2>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700" htmlFor="course">
              Academic Course
            </label>
            <select
              id="course"
              value={courseId}
              onChange={(event) => setCourseId(event.target.value)}
              className={`mt-1 bg-white font-medium ${INPUT_CLASS}`}
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
              placeholder="e.g. CS101: Intro to AI"
              className={`min-w-0 ${INPUT_CLASS}`}
            />
            <button
              type="button"
              onClick={() => void onCreateCourse()}
              disabled={busy || !newTitle.trim()}
              className="shrink-0 rounded-xl bg-slate-800 px-3.5 py-2 text-xs font-semibold text-white shadow-2xs hover:bg-slate-700 active:scale-[0.99] transition disabled:opacity-40 min-h-11 lg:min-h-0"
            >
              Create
            </button>
          </div>

          <div className="border-t border-slate-100 pt-3">
            <label className="block text-xs font-semibold text-slate-700 mb-1.5">
              PowerPoint Deck
            </label>
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
              className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-4 py-8 text-center transition-all ${
                dragging
                  ? 'border-indigo-500 bg-indigo-50/80 scale-[1.01]'
                  : 'border-slate-300/90 bg-slate-50/60 hover:bg-slate-50 hover:border-indigo-400'
              }`}
            >
              <input
                ref={inputRef}
                type="file"
                accept=".pptx"
                className="hidden"
                onChange={(event) => pickFile(event.target.files?.[0])}
              />
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-amber-500 to-orange-600 text-white shadow-sm mb-2.5">
                <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
                </svg>
              </div>
              <span className="text-sm font-semibold text-slate-800">
                {file ? file.name : 'Drop .pptx slide deck here'}
              </span>
              <span className="mt-1 text-xs text-slate-500">
                {file ? `${(file.size / 1024).toFixed(1)} KiB` : 'or click to browse your files'}
              </span>
            </label>
          </div>

          <button
            type="button"
            onClick={() => void onUpload()}
            disabled={!canUpload}
            className={`${BUTTON_PRIMARY} w-full`}
          >
            {busy ? 'Processing Slide Deck…' : 'Upload'}
          </button>

          {error && (
            <div className="rounded-xl border border-rose-200 bg-rose-50/90 px-3.5 py-2.5 text-xs text-rose-800">
              <span className="font-mono font-bold">{error.code}</span>: {error.message}
            </div>
          )}
        </section>

        <section className={`space-y-4 self-start rounded-2xl border border-slate-200/85 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.03),0_4px_12px_rgba(0,0,0,0.02)]`}>
          <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 pb-2.5">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-600">Uploaded files</h2>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-600">
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

          <p className="text-xs text-slate-500">
            Select a file to inspect its stored artifacts, metadata, and extracted Content IR.
          </p>

          {!courseId && <p className="text-sm text-slate-400">Select a course to see its uploaded files.</p>}

          {courseId && !loadingMaterials && materials.length === 0 && (
            <p className="text-sm text-slate-400">No presentations uploaded to this course yet.</p>
          )}

          {materials.length > 0 && (
            <ul className="space-y-2">
              {materials.map((material) => {
                const active = material.artifact_id === selectedId
                return (
                  <li key={material.artifact_id}>
                    <button
                      type="button"
                      onClick={() => void onSelectMaterial(material)}
                      aria-pressed={active}
                      className={`flex w-full flex-col gap-1 rounded-xl border p-3 text-left transition-all ${
                        active
                          ? 'border-indigo-600 bg-indigo-50/70 shadow-xs ring-1 ring-indigo-500/20'
                          : 'border-slate-200/90 bg-white hover:border-slate-300 hover:bg-slate-50/80 shadow-2xs'
                      }`}
                    >
                      <span className="flex w-full items-center gap-2">
                        <span className="truncate text-sm font-semibold text-slate-900">
                          {material.filename}
                        </span>
                        <span
                          className={`ml-auto shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold ${
                            STATUS_STYLE[material.job_status] ?? 'bg-slate-100 text-slate-600'
                          }`}
                        >
                          {material.job_status}
                        </span>
                      </span>
                      <span className="text-[11px] text-slate-500 font-medium">
                        Version {material.version} · {formatBytes(material.byte_size)} ·{' '}
                        {formatWhen(material.created_at)}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          )}

          {notice && (
            <p className="rounded-xl border border-indigo-200 bg-indigo-50/90 px-3.5 py-2.5 text-xs text-indigo-900">
              {notice}
            </p>
          )}

          {selected && (
            <div className="space-y-3 border-t border-slate-100 pt-3">
              <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-xs">
                <dt className="text-slate-500 font-medium">File</dt>
                <dd className="truncate font-medium text-slate-800">{selected.filename}</dd>
                <dt className="text-slate-500 font-medium">Artifact</dt>
                <dd className="truncate font-mono text-slate-600">{selected.artifact_id}</dd>
                <dt className="text-slate-500 font-medium">Version</dt>
                <dd className="truncate font-mono text-slate-600">
                  {selected.version_id} (v{selected.version})
                </dd>
                <dt className="text-slate-500 font-medium">Job</dt>
                <dd className="truncate font-mono text-slate-600">
                  {selected.job_id} ({selected.job_status})
                </dd>
                <dt className="text-slate-500 font-medium">SHA-256</dt>
                <dd className="truncate font-mono text-slate-600">{selected.sha256}</dd>
                <dt className="text-slate-500 font-medium">Size</dt>
                <dd className="text-slate-700">
                  {formatBytes(selected.byte_size)} ({selected.byte_size.toLocaleString()} bytes)
                </dd>
                <dt className="text-slate-500 font-medium">Uploaded</dt>
                <dd className="text-slate-700">{formatWhen(selected.created_at)}</dd>
              </dl>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 pt-1">
                <button
                  type="button"
                  onClick={() => void runExtract(selected.artifact_id)}
                  disabled={extracting}
                  className={BUTTON_SECONDARY}
                >
                  {extracting ? 'Extracting…' : 'Extract structure again'}
                </button>
                {/* A real link: the studio is a page, and opens in its own tab. */}
                <Link
                  to={studioPath(selected.artifact_id)}
                  className={BUTTON_PRIMARY}
                >
                  Open Teacher Studio
                </Link>
              </div>
              <p className="text-[11px] text-slate-500">
                <a
                  href={studioPath(selected.artifact_id)}
                  target="_blank"
                  rel="noreferrer"
                  className="font-semibold text-indigo-600 hover:underline"
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
        <section className={`space-y-4 self-start rounded-2xl border border-slate-200/85 bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,0.03),0_4px_12px_rgba(0,0,0,0.02)] md:col-span-2`}>
          <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 pb-2.5">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-600">Classes</h2>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-600">
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
          <p className="text-xs text-slate-500">
            Classes scheduled for this institution. Each opens its own classroom page.
          </p>
          {classesError && <p className="text-xs text-rose-700">{classesError}</p>}
          {!loadingClasses && !classesError && classes.length === 0 && (
            <p className="text-sm text-slate-400">
              No classes yet — a class is scheduled through the runtime API (
              <code className="rounded bg-slate-100 px-1 font-mono">POST /classes</code>).
            </p>
          )}
          {classes.length > 0 && (
            <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {classes.map((item) => (
                <li key={item.class_id}>
                  <Link
                    to={classroomPath(item.class_id)}
                    className="flex h-full flex-col justify-between gap-2 rounded-xl border border-slate-200/85 bg-slate-50/50 p-4 transition-all hover:bg-white hover:border-indigo-400 hover:shadow-xs"
                  >
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-semibold text-slate-900">{item.title}</span>
                      <span className="ml-auto shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-700">
                        {item.state}
                      </span>
                    </div>
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
