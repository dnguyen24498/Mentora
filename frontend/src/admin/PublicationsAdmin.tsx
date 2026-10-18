import { useCallback, useEffect, useState } from 'react'
import {
  describeApiError,
  listCourses,
  listMaterials,
  listPublications,
  loadPublication,
  publishVersion,
  type Course,
  type Material,
  type Publication,
} from '../api/client'
import { readSelectedCourse, writeSelectedCourse } from '../institution'
import {
  Badge,
  Banner,
  BUTTON_PRIMARY,
  EmptyState,
  INPUT_CLASS,
  Panel,
  Row,
  type Tone,
} from '../components/ui'

const PUBLICATION_TONE: Record<string, Tone> = {
  PUBLISHED: 'good',
  SUPERSEDED: 'neutral',
}

const INTEGRITY_TONE: Record<string, Tone> = {
  VERIFIED: 'good',
  MISMATCH: 'bad',
  MISSING: 'warn',
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`
}

/**
 * Publications — the admin view of what has been sealed and is being taught from.
 *
 * Publishing is the one destructive-looking action in the app and it is
 * deliberately not destructive: it seals a built package, indexes it and commits
 * one publication row in one transaction. It is **idempotent** (a replay returns
 * the same publication with `created: false`) and publishing a correction makes a
 * **new** publication that supersedes the old one, which stays readable forever
 * (`DEC-CONTENT-005`). So the only other verb here is "verify", which re-checks the
 * pinned bytes against the digest recorded at seal time and reports
 * `VERIFIED` / `MISMATCH` / `MISSING` rather than mutating anything.
 */
export default function PublicationsAdmin({ institutionId }: { institutionId: string }) {
  const [courses, setCourses] = useState<Course[]>([])
  const [courseId, setCourseId] = useState(readSelectedCourse)
  const [materials, setMaterials] = useState<Material[]>([])
  const [publications, setPublications] = useState<Publication[]>([])
  const [versionId, setVersionId] = useState('')
  const [publishedBy, setPublishedBy] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    writeSelectedCourse(courseId)
  }, [courseId])

  useEffect(() => {
    let cancelled = false
    setError(null)
    void listCourses(institutionId).then(
      (loaded) => {
        if (cancelled) return
        setCourses(loaded)
        setCourseId((previous) =>
          previous && loaded.some((course) => course.course_id === previous)
            ? previous
            : (loaded[0]?.course_id ?? ''),
        )
      },
      (cause: unknown) => {
        if (!cancelled) setError(describeApiError(cause))
      },
    )
    return () => {
      cancelled = true
    }
  }, [institutionId])

  const refresh = useCallback(
    async (course: string) => {
      if (!course) {
        setMaterials([])
        setPublications([])
        return
      }
      try {
        const [loadedMaterials, loadedPublications] = await Promise.all([
          listMaterials(institutionId, course),
          listPublications(institutionId, course),
        ])
        setMaterials(loadedMaterials)
        setPublications(loadedPublications.publications)
      } catch (cause) {
        setError(describeApiError(cause))
      }
    },
    [institutionId],
  )

  useEffect(() => {
    void refresh(courseId)
  }, [courseId, refresh])

  async function publish() {
    if (!versionId.trim()) return
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const publication = await publishVersion(institutionId, versionId.trim(), publishedBy.trim() || undefined)
      await refresh(courseId)
      setVersionId('')
      setNotice(
        publication.created
          ? `Published v${publication.course_version} of the course (${publication.publication_id}).`
          : 'This version was already published — the same publication was returned (idempotent).',
      )
    } catch (cause) {
      setError(describeApiError(cause))
    } finally {
      setBusy(false)
    }
  }

  async function verify(publicationId: string) {
    setError(null)
    setNotice(null)
    try {
      const verified = await loadPublication(institutionId, publicationId, true)
      const integrity = verified.integrity
      setPublications((current) =>
        current.map((item) => (item.publication_id === publicationId ? verified : item)),
      )
      setNotice(
        integrity
          ? `Integrity of ${publicationId}: ${integrity.state} (expected ${integrity.expected_digest.slice(0, 12)}…).`
          : `No integrity report was returned for ${publicationId}.`,
      )
    } catch (cause) {
      setError(describeApiError(cause))
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <Panel title="Course">
        <select
          aria-label="Course"
          value={courseId}
          onChange={(event) => setCourseId(event.target.value)}
          className={INPUT_CLASS}
        >
          {courses.length === 0 && <option value="">No courses yet</option>}
          {courses.map((course) => (
            <option key={course.course_id} value={course.course_id}>
              {course.title}
            </option>
          ))}
        </select>
      </Panel>

      {error && <Banner tone="bad">{error}</Banner>}
      {notice && <Banner tone="good">{notice}</Banner>}

      <Panel title="Publish a version">
        <div className="grid gap-3 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_auto] sm:items-end">
          <div>
            <label htmlFor="publish-version" className="block text-sm font-medium text-slate-700">
              Course version
            </label>
            <input
              id="publish-version"
              list="publish-version-options"
              value={versionId}
              onChange={(event) => setVersionId(event.target.value)}
              placeholder="version id of an approved version"
              className={`${INPUT_CLASS} mt-1 font-mono text-xs`}
            />
            <datalist id="publish-version-options">
              {materials.map((material) => (
                <option key={material.version_id} value={material.version_id}>
                  {material.filename}
                </option>
              ))}
            </datalist>
          </div>
          <div>
            <label htmlFor="publish-by" className="block text-sm font-medium text-slate-700">
              Published by
            </label>
            <input
              id="publish-by"
              value={publishedBy}
              onChange={(event) => setPublishedBy(event.target.value)}
              placeholder="teacher@example.edu"
              className={`${INPUT_CLASS} mt-1`}
            />
          </div>
          <button
            type="button"
            onClick={() => void publish()}
            disabled={busy || !versionId.trim()}
            className={BUTTON_PRIMARY}
          >
            {busy ? 'Publishing…' : 'Publish'}
          </button>
        </div>
        <p className="text-[11px] text-slate-400">
          Only an <strong>approved</strong> version publishes. A refusal writes nothing and reports a
          precise issue code (not approved, stale approval, wrong state, checksum mismatch, index
          failure).
        </p>
      </Panel>

      <Panel title={`Publications (${publications.length})`}>
        {publications.length === 0 && (
          <EmptyState>This course has no publications yet.</EmptyState>
        )}

        <ul className="space-y-2">
          {publications.map((publication) => (
            <li
              key={publication.publication_id}
              className="space-y-2 rounded-lg border border-slate-200 p-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={PUBLICATION_TONE[publication.state] ?? 'neutral'}>
                  {publication.state}
                </Badge>
                <Badge tone="info">v{publication.course_version}</Badge>
                {publication.integrity && (
                  <Badge tone={INTEGRITY_TONE[publication.integrity.state] ?? 'neutral'}>
                    {publication.integrity.state}
                  </Badge>
                )}
                <span className="font-mono text-xs text-slate-500">
                  {publication.publication_id}
                </span>
                <button
                  type="button"
                  onClick={() => void verify(publication.publication_id)}
                  className="ml-auto rounded-md border border-slate-300 px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
                >
                  Verify integrity
                </button>
              </div>

              <dl className="space-y-1 text-sm">
                <Row label="Version">{publication.version_id}</Row>
                <Row label="Content package">{publication.content_package_version}</Row>
                <Row label="Knowledge index">{publication.knowledge_index_version}</Row>
                <Row label="Lesson plan">{publication.lesson_plan_versions.join(', ') || '—'}</Row>
                <Row label="Content digest">{publication.content_digest.slice(0, 24)}…</Row>
                <Row label="Files">
                  {publication.file_count} ({formatBytes(publication.total_bytes)})
                </Row>
                <Row label="Superseded by">{publication.superseded_by ?? '—'}</Row>
                <Row label="Published by">{publication.published_by}</Row>
                <Row label="Created">{publication.created_at}</Row>
              </dl>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  )
}
