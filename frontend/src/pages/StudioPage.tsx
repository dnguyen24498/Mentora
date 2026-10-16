import { useCallback, useEffect, useState } from 'react'
import TeacherStudio from '../components/TeacherStudio'
import { Link } from '../router'
import { useInstitution } from '../institution'
import {
  ApiError,
  buildReviewPackage,
  loadArtifact,
  loadReviewPackage,
  loadReviewState,
  postReviewDecision,
  saveReviewDraft,
  type ArtifactSummary,
  type ReviewDecisionInput,
  type ReviewPackage,
  type ReviewState,
} from '../api/client'

type Phase = 'loading' | 'building' | 'ready' | 'error'

export interface StudioPageProps {
  /** The artifact whose package is under review (the `/studio/{id}` route). */
  artifactId: string
  /** Injectable so page tests never need a server or a real blob URL. */
  loadRender?: (institutionId: string, path: string) => Promise<string>
}

/** Turn a failed request into a message that keeps the stable error code. */
function describe(cause: unknown): string {
  if (cause instanceof ApiError) {
    return cause.message ? `${cause.code}: ${cause.message}` : cause.code
  }
  return cause instanceof Error ? cause.message : String(cause)
}

/**
 * Teacher Studio page — `/studio/{artifactId}` (V0-007).
 *
 * The review flow is its own page rather than a panel on the upload page: the
 * slide is meant to be seen large, so the page is full-width, can be opened in
 * its own tab or on a second monitor, and survives a deep link and a refresh.
 *
 * It owns only the *loading* of the two review resources:
 *
 * * the **package projection** (`GET .../review-package`) — built on first open
 *   because building renders every slide, then read from storage thereafter;
 * * the **review overlay** (`GET .../review-state`) — the decision and drafts.
 *
 * Everything a review action does is delegated to the server; this page never
 * mutates a package, so the acceptance criterion "edits create draft data" holds
 * regardless of what is clicked here.
 */
export default function StudioPage({ artifactId, loadRender }: StudioPageProps) {
  const [institution, setInstitution] = useInstitution()
  const [phase, setPhase] = useState<Phase>('loading')
  const [review, setReview] = useState<ReviewPackage | null>(null)
  const [reviewState, setReviewState] = useState<ReviewState | null>(null)
  const [artifact, setArtifact] = useState<ArtifactSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [reviewNotice, setReviewNotice] = useState<string | null>(null)
  const [reviewError, setReviewError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(
    async ({ rebuild = false }: { rebuild?: boolean } = {}) => {
      setError(null)
      setReviewError(null)
      setReviewNotice(null)
      setPhase('loading')
      try {
        let loaded: ReviewPackage
        if (rebuild) {
          setPhase('building')
          loaded = await buildReviewPackage(institution, artifactId)
        } else {
          try {
            loaded = await loadReviewPackage(institution, artifactId)
          } catch (cause) {
            if (!(cause instanceof ApiError) || cause.code !== 'NOT_FOUND') throw cause
            // Nothing is built for this file yet. Building renders every slide,
            // so it is a visible, slow phase rather than a silent one.
            setPhase('building')
            loaded = await buildReviewPackage(institution, artifactId)
          }
        }
        setReview(loaded)
        setNotice(
          rebuild
            ? 'Rebuilt the package: every slide was rendered and validated again.'
            : 'Loaded the package already built for this file (no re-render).',
        )
        const [overlay, meta] = await Promise.all([
          loadReviewState(institution, artifactId),
          loadArtifact(institution, artifactId).catch(() => null),
        ])
        setReviewState(overlay)
        setArtifact(meta)
        setPhase('ready')
      } catch (cause) {
        setError(describe(cause))
        setPhase('error')
      }
    },
    [artifactId, institution],
  )

  useEffect(() => {
    void load()
  }, [load])

  // Distinct tabs are the point of a page of its own, so name this one.
  useEffect(() => {
    document.title = artifact
      ? `${artifact.filename} — Teacher Studio`
      : 'Teacher Studio — Mentora'
  }, [artifact])

  /**
   * Approve or reject. The server refuses to approve a non-publishable document
   * (`PUBLICATION_BLOCKED`); this records state *about* the package.
   */
  const decide = useCallback(
    async (input: ReviewDecisionInput) => {
      setBusy(true)
      setReviewError(null)
      setReviewNotice(null)
      try {
        setReviewState(await postReviewDecision(institution, artifactId, input))
        setReviewNotice(
          input.decision === 'APPROVE'
            ? 'Approved. The course version is now APPROVED; sealing, indexing and publication are the next task (V0-008).'
            : 'Rejected. The course version is back in REVIEW_REQUIRED, with the reason recorded.',
        )
      } catch (cause) {
        setReviewError(describe(cause))
      } finally {
        setBusy(false)
      }
    },
    [artifactId, institution],
  )

  /**
   * Save a draft revision of the lesson order. Drafts are appended to the
   * relational store; the immutable package under review is left untouched.
   */
  const saveDraft = useCallback(
    async (sections: { section_id: string; script: string }[]) => {
      setBusy(true)
      setReviewError(null)
      setReviewNotice(null)
      try {
        const draft = await saveReviewDraft(institution, artifactId, { sections })
        setReviewState(await loadReviewState(institution, artifactId))
        setReviewNotice(
          `Saved draft revision ${draft.revision}. The built package is unchanged — the draft is data for a future version.`,
        )
      } catch (cause) {
        setReviewError(describe(cause))
      } finally {
        setBusy(false)
      }
    },
    [artifactId, institution],
  )

  const loading = phase === 'loading' || phase === 'building'

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3">
          <Link
            to="/"
            className="rounded-md border border-slate-300 px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
          >
            ← Library
          </Link>
          <h1 className="text-base font-semibold">Teacher Studio</h1>
          <span className="truncate text-sm text-slate-500">{artifact?.filename ?? 'loading…'}</span>
          <span className="hidden truncate font-mono text-[11px] text-slate-400 sm:inline">{artifactId}</span>

          <div className="ml-auto flex items-center gap-2">
            <label htmlFor="institution" className="text-[11px] font-medium text-slate-500">
              Institution
            </label>
            <input
              id="institution"
              value={institution}
              onChange={(event) => setInstitution(event.target.value)}
              className="w-40 rounded-md border border-slate-300 px-2 py-1 text-xs focus:border-indigo-500 focus:outline-none"
            />
            <button
              type="button"
              onClick={() => void load({ rebuild: true })}
              disabled={loading}
              className="rounded-md border border-slate-300 px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
            >
              Rebuild package
            </button>
          </div>
        </div>
      </header>

      <main className="px-4 py-4">
        {phase === 'loading' && (
          <p role="status" className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-500">
            Loading the reviewed package…
          </p>
        )}

        {phase === 'building' && (
          <p role="status" className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-500">
            Rendering every slide and validating the package — this takes a few seconds for a real deck.
          </p>
        )}

        {phase === 'error' && (
          <div
            data-testid="studio-error"
            role="alert"
            className="rounded-xl border border-rose-200 bg-rose-50 p-5 text-rose-800"
          >
            <p className="text-sm font-semibold">The package for this file could not be loaded.</p>
            <p className="mt-1 font-mono text-xs">{error}</p>
            <p className="mt-2 text-xs">
              Check the institution (the file belongs to one tenant) and that the link names an uploaded
              artifact.
            </p>
          </div>
        )}

        {phase === 'ready' && review && (
          <div className="space-y-3">
            {notice && (
              <p data-testid="studio-notice" className="text-[11px] text-slate-500">
                {notice}
              </p>
            )}
            <TeacherStudio
              institutionId={institution}
              review={review}
              reviewState={reviewState}
              busy={busy}
              notice={reviewNotice}
              error={reviewError}
              onDecide={decide}
              onSaveDraft={saveDraft}
              loadRender={loadRender}
            />
          </div>
        )}
      </main>
    </div>
  )
}
