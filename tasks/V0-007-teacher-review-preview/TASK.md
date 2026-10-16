# V0-007: Teacher review preview

**Week:** W4  
**Status:** IN_PROGRESS (read-only preview slice delivered; approve/reject + edits remain)  
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

**Scope delivered: the read-only preview slice only** (agreed with the user:
"preview only" — no approve/reject, no edits). The task stays `IN_PROGRESS`; the
unmet acceptance criteria and required tests are listed under Known limitations.

- Link to commit/PR: _(uncommitted working tree)_
- Test command and result: `cd backend && env -u PYTHONPATH .venv/bin/python -m pytest -q` -> **204 passed** (18 added by this slice in `tests/test_publication_review.py`). Frontend: `npx tsc --noEmit` clean and `npm run build` succeeds (`vite build`, 30 modules).
- Required tests coverage: **authorization tests** -> `test_review_is_tenant_scoped` (POST/GET/render all 403 for another institution), `test_review_requires_the_institution_header` (422), `test_review_of_an_unknown_artifact_is_404`. **Blocking-warning coverage (backend half)** -> `test_blocked_render_is_never_offered_for_review` (409 `PUBLICATION_BLOCKED`, nothing written, GET afterwards 404), `test_publication_blocked_error_reaches_the_service`. **UI component tests: NOT DONE** (no browser harness; see limitations).
- Demo evidence: `POST /artifacts/1e4c06bc-…/review-package` on the real 16.7 MB / 28-slide deck (tenant `university-001`, course v3) -> 200 in **4.04 s**: `state REVIEW_REQUIRED`, `publishable true`, `package pkg-892f814d4531dec7`, 28 scenes / 57 files, `cpv-892f814d4531dec7`, `lp-4f186bb0ec531e0a`, `knowledge_index_version unindexed`, `teaching_graph_version null`, renderer `local-structural-svg@1.0.0 (stdlib-svg)`, lesson order 28 sections (`EXPLANATION`) with `safe_markers ['ppt/slides/slide1.xml#step-0']`. All 28 slides are flagged for review (`DEGRADED_RENDERED`, missing font `Be Vietnam Pro`). Then `GET` the same path -> **200 in 0.022 s (185x faster than the build, no re-render)** and 3 packaged renders (`0/5/27`) in **0.032 s total** (`image/svg+xml`, 2444/8661/1615 bytes).
- Browser flow (to reproduce): `./run.sh` -> <http://dev.nguynx.uk> -> pick the `university-001` course -> select the deck -> **Preview slides**. The UI shows the placeholder-render notice, the per-slide SVG, extracted text, speaker notes, `MISSING_FONT:Be Vietnam Pro` warnings, the fidelity badges and the lesson order with safe markers; `←`/`→` move between slides; **there is no approve button**.
- Metrics observed: none added (the review projection is a read path); the build path keeps emitting `compiler.package.built` from V0-006.
- Traceability rows added: `DEC-CONTENT-006` (`backend/app/publication/review.py`, `frontend/src/components/ReviewPreview.tsx`), `DEC-CONTENT-008` (`backend/app/publication/review.py`, `frontend/src/components/ReviewPreview.tsx`), plus `DEC-CONTENT-004`/`005` for `backend/app/compiler/package_builder/loader.py`.
- Acceptance criteria status:
  - **Teacher cannot approve blocking failures** — satisfied, structurally two ways: the screen has no approve action at all, and a document that failed the fidelity gate is never built into a package (`409 PUBLICATION_BLOCKED`), so there is nothing to review.
  - **Edits create draft data, not mutate the published package** — trivially satisfied for this slice (no edits exist); the delivered projection is read-only and the tests assert the stored package is byte-unchanged after reads (`test_review_does_not_mutate_the_stored_package`).
  - **Keyboard and basic screen-reader operation** — implemented (real `<button>`s with `aria-pressed`, ordered `<ol>`, `alt` text on the render, `←`/`→` navigation, visible focus) but **not verified** against a screen reader; a full audit needs the browser harness.
- Known limitations:
  - **No approve/reject and no edits** — V0-008 owns the publication state machine and draft storage.
  - **No UI component tests / blocking-warning E2E / SR audit** — no browser test harness is installed and adding one is a new dependency (`tests/e2e/` in the nominal scope is still absent, as it is for every V0 task).
  - **The served render is a structural placeholder**, not a native PowerPoint render (`DEC-TECH-005` is `OPEN`); the UI states this explicitly.
  - The read path loads every package file to serve it (`read_package`), which is fine at 577 KiB but would need a ranged/streaming read for large packages.
  - No HTTP cancellation for an in-flight build (V0-003).
  - The preview lives in the single existing Vite app, not `frontend/apps/teacher-studio/`.

## Files/Areas Allowed to Change (as delivered)

- `frontend/apps/teacher-studio/` -> `frontend/src/components/ReviewPreview.tsx`, `frontend/src/api/client.ts`, `frontend/src/App.tsx`, `frontend/README.md`
- `backend/app/publication/` -> `backend/app/publication/{__init__,review,router}.py` (+ wired in `backend/app/api/app.py`)
- `backend/app/courses/` -> untouched
- `tests/e2e/` -> `backend/tests/test_publication_review.py` (the repo's actual test root; same mapping precedent as V0-004/V0-005)

Also touched (required to keep the tree consistent):
`backend/app/compiler/package_builder/{builder,service,loader,__init__}.py`
(deterministic `package_id` + `package_prefix_for` + `read_package`),
`contracts/openapi/openapi.yaml`, `governance/TRACEABILITY_MATRIX.csv`,
`tasks/STATUS_BOARD.csv`, this task folder.

