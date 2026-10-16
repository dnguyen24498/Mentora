# V0-007: Teacher review preview

**Week:** W4  
**Status:** DONE  
**Owner:** Solo developer  
**Target:** V0

## Objective

Create a minimal review UI for render, text, notes, warnings, and lesson order.

## Dependencies

- V0-006

## Requirement IDs

- `DEC-CONTENT-006`
- `DEC-CONTENT-008`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/architecture/07_PUBLICATION_AND_REVIEW.md`
- `docs/architecture/15_FRONTEND_CLASSROOM_AND_STUDIO.md`

## In Scope

- Teacher Studio course-version page.
- Side-by-side rendered scene and extracted information.
- Warnings/fidelity and blocking status.
- Approve/reject and simple scene-order/script edits.

## Out of Scope

- Graph editor.
- Multi-review workflow.
- Advanced policy editor.

## Acceptance Criteria

- Teacher cannot approve blocking failures.
- Edits create draft data, not mutate published package.
- Keyboard and basic screen-reader operation.

## Required Tests

- UI component tests.
- Authorization tests.
- Blocking-warning E2E.

## Files/Areas Allowed to Change

- `frontend/apps/teacher-studio/`
- `backend/app/publication/`
- `backend/app/courses/`
- `tests/e2e/`

## Quality Gate

All tests pass; no architecture contradiction; telemetry and traceability are updated; no new production dependency without an accepted ADR.

## Completion Evidence

**Scope delivered: the whole task** — Teacher Studio course-version page,
side-by-side render + extracted information, warnings/fidelity and blocking status,
approve/reject, and simple scene-order/script edits.

- Link to commit/PR: _filled in below after the milestone commit_ (the read-only
  projection slice was `b3580a6`; this commit completes the task).
- Test command and result:
  - `cd backend && env -u PYTHONPATH .venv/bin/python -m pytest -q` -> **234 passed**
    (was 204; **+30** for the review write path in
    `tests/test_publication_review_decisions.py` and `tests/test_publication_review_flow.py`).
  - `cd frontend && npm test` -> **17 passed** (`src/components/TeacherStudio.test.tsx`).
  - `cd frontend && npx tsc --noEmit` clean; `npm run build` succeeds (30 modules).
- **Required tests**
  - **UI component tests** -> `frontend/src/components/TeacherStudio.test.tsx`
    (17 tests): side-by-side render/extracted information, the structural-placeholder
    notice, the blocking path (alert + disabled, `aria-describedby`-linked Approve),
    approve with reviewer attribution, reject-requires-a-reason, stale decision,
    keyboard reorder + draft payload, discard, draft revision initialisation, script
    edit payload, accessible names / `<ol>` structure, arrow-key navigation and the
    text-entry guard.
  - **Authorization tests** -> `test_publication_review_decisions.py::test_decisions_and_drafts_are_tenant_scoped`
    (403 for another institution on decision/review-state/drafts, nothing written),
    `::test_review_actions_require_the_institution_header` (422),
    `::test_review_action_on_an_unknown_artifact_is_404`, plus
    `test_publication_review_flow.py::test_the_whole_flow_is_tenant_isolated`.
  - **Blocking-warning E2E** -> `test_publication_review_flow.py::test_a_blocking_render_failure_never_becomes_approvable`
    (API-level E2E with the real app + SQLite + object store: a failing render is
    never built into a package, `409 PUBLICATION_BLOCKED`, then `404` on
    review-state/decision/drafts, no package bytes and no review rows) and the
    component-level blocking test above. Further: `::test_a_degraded_render_is_reviewable_and_the_decision_is_auditable`
    (degraded ≠ blocked), `::test_review_telemetry_redacts_authored_text`,
    and `test_publication_review_decisions.py::test_approving_a_non_publishable_review_is_blocked`
    (approve is refused even if a non-publishable projection reaches the decision path).
- **Acceptance criteria**
  - **Teacher cannot approve blocking failures** — two independent guarantees: a
    blocked document is never built into a package at all (V0-005 fidelity gate ->
    `409 PUBLICATION_BLOCKED`), and `ReviewWorkflow.decide` refuses `APPROVE` when
    the projection is not publishable (server `409`) while the UI disables Approve
    with a `role="alert"` reason wired through `aria-describedby`.
  - **Edits create draft data, not mutate the published package** — a draft is an
    append-only revision (`UNIQUE (artifact_id, revision)`) stored in
    `review_drafts`, its structural fields are inherited from the package, and
    tests assert the stored package files are byte-identical after an edit
    (`test_save_draft_appends_a_revision_and_leaves_the_package_untouched`, plus the
    live manifest-digest check below). A decision likewise records state *about*
    the content it reviewed and never rewrites it.
  - **Keyboard and basic screen-reader operation** — real `<button>`s (reorder
    controls labelled `Move section N (type) up/down`), `<ol>` lesson order, labelled
    scripts, `aria-pressed` selection, `role="alert"` blocking/validation messages,
    `role="status"` `aria-live` announcements for reorder/save, `role="region"`
    slide panes with headings, `←`/`→` slide navigation that does not hijack a
    focused text field, and visible focus outlines. Verified by the component tests
    (keyboard reorder via `{Enter}`, accessible names, list structure); not audited
    with a real screen reader — that needs a browser harness (see limitations).
- **Demo evidence (live, real 16.7 MB / 28-slide deck**, tenant `university-001`,
  course v3, artifact `1e4c06bc-…`, package `pkg-892f814d4531dec7`**)**
  - `GET …/review-package/review-state` -> **200 in 58 ms**: `version_status DRAFT`,
    `state REVIEW_REQUIRED`, `publishable true`, `decision null`, `draft_count 0`,
    `blocking_scene_orders []`.
  - `GET …/review-package` -> **200 in 15.6 ms**, 28 sections (no re-render).
  - `POST …/review-package/drafts` (move the first section last + rewrite its
    script) -> **200 in 144 ms**: `revision 1`, 28 sections, first = `…#section-1`,
    last = `…#section-0` with the new script.
  - `POST …/review-package/drafts` with a section not in the package -> **400**
    `{"code":"INVALID_REQUEST","issue_code":"UNKNOWN_SECTION"}`.
  - `POST …/review-package/decision` `{"decision":"REJECT"}` (no reason) -> **400**
    `INVALID_REQUEST` ("a rejection must record a reason").
  - `POST …/review-package/decision` `{"decision":"APPROVE"}` -> **200 in 120 ms**:
    `decision APPROVE`, `version_status APPROVED`, `stale false`, `draft_rev 1`.
  - The same approve again -> **200** with the *same* `decision_id` (idempotent).
  - Package `manifest.json` sha256 prefix identical before and after the edit +
    decision (`dcbf71942e1b22a3`) -> **the immutable package was not touched**;
    the review projection still returns the package's own lesson order.
  - Cross-tenant `GET …/review-state` as `university-002` -> **403**.
  - Through the Vite proxy on `:8000` (`Host: dev.nguynx.uk`) the same endpoint
    returns the review state, and Vite serves the new `TeacherStudio.tsx` module.
- **Metrics/telemetry**: `app/publication/telemetry.py` emits
  `publication.review.decided` (decision, tenant/artifact/version/package/content
  version, `reason_present`, `reason_chars`, `requires_review`, `replayed`),
  `publication.review.approval_blocked`, and `publication.review.draft_saved`
  (revision, section count, reordered/scripts-edited counts), plus counters
  (`ReviewMetrics`). Authored text is **never** logged — asserted by
  `test_review_telemetry_redacts_authored_text`.
- **Traceability rows added**: `DEC-CONTENT-005` / `006` / `007` / `008` and
  `DEC-DATA-001`, `DEC-RELIABILITY-001`/`002` for `app/publication/{models,repository,draft,workflow,telemetry}.py`,
  the two backend test files, `frontend/src/components/TeacherStudio(.test).tsx`
  and the new migration; the two `ReviewPreview.tsx` rows were retargeted to
  `TeacherStudio.tsx`.
- **Contracts updated before the interface changed**: `contracts/openapi/openapi.yaml`
  gained `/review-package/decision` (POST), `/review-package/review-state` (GET)
  and `/review-package/drafts` (GET/POST) with `ReviewDecisionRequest`,
  `ReviewDecision`, `ReviewDraftRequest`, `ReviewDraftSection`, `ReviewDraft`,
  `ReviewDraftList` and `ReviewState`; `ReviewPackage`'s description now
  distinguishes the immutable projection from the mutable overlay.
- **Schema/migrations**: `review_decisions` + `review_drafts` added to
  `backend/app/db/schema.sql` (`CREATE TABLE IF NOT EXISTS`, applied by `init_db`
  on start, so the existing dev DB picked them up) with the PostgreSQL reference
  `database/migrations/0002_review_decisions_and_drafts.sql`.
- Known limitations:
  - **Reviewer identity is not implemented** — `reviewer`/`edited_by` are
    client-supplied attribution (default: the tenant id) and are **not** an
    authorization control; role enforcement needs
    `docs/security/IDENTITY_AUTHORIZATION_AND_TOKENS.md`.
  - **Approving does not publish** — `APPROVED → SEALING → INDEXING → COMMITTING → PUBLISHED`,
    the pinned knowledge-index record and the outbox are V0-008.
  - Version status is `DRAFT` until a first review action; nothing in V0-005/V0-006
    moves a version to `REVIEW_REQUIRED` on build (that belongs to the compiler-job
    state machine, V0-003).
  - **The served render is a structural placeholder**, not a native PowerPoint
    render (`DEC-TECH-005` is `OPEN`); the UI states this explicitly.
  - The read path loads every package file to serve it (`read_package`) — fine at
    577 KiB, but would need a ranged/streaming read for large packages.
  - No HTTP cancellation for an in-flight build (V0-003).
  - No CI/lint config (FND-001 is still `TODO`); tests and `tsc` are run manually.
  - The Teacher Studio lives in the single existing Vite app, not
    `frontend/apps/teacher-studio/` (see the mapping note below).

## Files/Areas Allowed to Change (as delivered)

- `frontend/apps/teacher-studio/` -> `frontend/src/components/TeacherStudio.tsx`,
  `frontend/src/components/TeacherStudio.test.tsx`, `frontend/src/test/setup.ts`,
  `frontend/vitest.config.ts`, `frontend/package.json`, `frontend/src/api/client.ts`,
  `frontend/src/App.tsx`, `frontend/README.md` (single Vite app; the nominal
  `frontend/apps/teacher-studio/` app does not exist — same mapping precedent as
  V0-004…V0-006)
- `backend/app/publication/` -> `backend/app/publication/{__init__,review,router,models,repository,draft,workflow,telemetry}.py`
- `backend/app/courses/` -> `models.py` (+`APPROVED`), `repository.py` (+`set_version_status`)
- `tests/e2e/` -> `backend/tests/test_publication_review_decisions.py`,
  `backend/tests/test_publication_review_flow.py` (the repo's actual test root;
  the E2E is an HTTP-level end-to-end flow, not browser automation)

Also touched (required to keep the tree consistent):
`backend/app/db/schema.sql` + `database/migrations/0002_review_decisions_and_drafts.sql`
(the definition of done requires schemas and migrations to move together),
`backend/app/api/app.py` (router wiring + `issue_code` in the error envelope),
`contracts/openapi/openapi.yaml`, `governance/TRACEABILITY_MATRIX.csv`,
`tasks/STATUS_BOARD.csv`, this task folder, `AGENTS.md`, `backend/README.md`.


