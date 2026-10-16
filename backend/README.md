# Backend (modular monolith)

Python backend for the AI Teacher Platform. The V0 vertical implemented so far:
**secure PPTX ingestion + SQLite-backed persistence + deterministic structural
extraction + per-slide fallback rendering with an explicit fidelity gate + a
baseline Content Package + teacher review** (preview, approve/reject, draft
lesson-order and script edits).

## Commands

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
env -u PYTHONPATH .venv/bin/python -m pytest -q          # all tests
env -u PYTHONPATH .venv/bin/python -m pytest tests/test_pptx_extractor.py -q   # one file
```

`env -u PYTHONPATH` is required in this shell (ROS 2 sets a global `PYTHONPATH`
that breaks the venv's `pytest`).

Run the API on `:8001` (the frontend dev server uses `:8000`; tenant is passed
as `X-Institution-Id` until OIDC is wired):

```bash
cd backend
env -u PYTHONPATH .venv/bin/uvicorn app.api.app:create_app --factory --reload --port 8001
```

The server also serves the built frontend at `/` when `frontend/dist/` exists
(optional single-origin mode; override the location with `MENTORA_FRONTEND_DIST`).
It is mounted through `app/api/spa.py` (`SpaStaticFiles`), which answers the
frontend's client-side routes — `/studio/{artifactId}` included — with the app
shell, so a deep link or a refresh works there too; a real asset is still served
as itself and a **missing** asset still 404s (rewriting it to HTML would only
break the browser). For normal development the frontend runs on its own server at
`:8000` — see `frontend/README.md`.

## Layout

| Path | Responsibility |
| --- | --- |
| `app/security/` | Upload validation: size limit, filename normalization, extension + magic-byte checks (stable error codes). |
| `app/storage/` | `ObjectStore` interface + atomic, content-addressed `LocalObjectStore`. |
| `app/courses/` | Course/version/source-artifact/compiler-job models, tenant-scoped repository, `UploadService`. |
| `app/compiler/models/` | Internal Content IR (`content-ir/1.1.0`): scenes, objects, text runs, normalized bounds, fidelity, provenance. |
| `app/compiler/extractors/` | Dependency-free PPTX (OOXML) structural extractor (`PptxExtractor`). |
| `app/compiler/renderers/` | Provider-neutral `DocumentRenderer` adapter + deterministic local structural SVG renderer + required test double (V0-005). |
| `app/compiler/validators/` | Scene/package invariants and the fidelity publication gate (V0-005) plus CTF package validation (V0-006). |
| `app/compiler/render_service.py` | `RenderingService`: artifact -> Content IR -> per-slide render -> gate. |
| `app/compiler/package_builder/` | Baseline Content Package builder (V0-006): IR + renders -> scenes/lesson plan/manifest, plus `read_package` for reading one back. |
| `app/compiler/service.py` | `ExtractionService`: artifact -> Content IR -> job status. |
| `app/publication/` | Teacher review of a built package (V0-007): the read-only projection (`review.py`) plus the write path (`workflow.py`, `repository.py`, `draft.py`) — approve/reject and draft lesson-order revisions. Publication state transitions are V0-008. |
| `app/db/` | SQLite connection + schema/migration application. |
| `app/api/` | FastAPI app factory; serves the built frontend at `/` when present, with an SPA fallback for client-side routes (`spa.py`). |
| `app/common/` | Base errors and stable error codes. |

## Endpoints

- `POST /courses` — create a course; `title` query param, optional `course_id`.
- `GET /courses` — list the tenant's courses (used by the frontend picker).
- `GET /courses/{courseId}/materials` — list the course's uploaded presentations, newest first, each with its version number and compiler-job status (used by the frontend file list).
- `POST /courses/{courseId}/materials` — multipart `file`; returns `202` with artifact/job/version ids. Duplicate bytes (or a repeated `Idempotency-Key`) return the existing record with `created: false`.
- `POST /artifacts/{artifactId}/extract` — runs structural extraction and returns the Content IR.
- `POST /artifacts/{artifactId}/compile` — extraction + a fallback render for every slide + the fidelity gate; returns `content_ir`, `render`, `validation`, `job_status`. Idempotent.
- `GET /artifacts/{artifactId}/renders/{order}` — the deterministic fallback visual (SVG) for one slide, re-derived from the stored artifact and tenant-scoped.
- `POST /artifacts/{artifactId}/review-package` — **V0-007**: builds the Baseline Content Package (V0-006, idempotent) and returns the teacher review view — per-slide render reference, extracted text, notes, warnings/fidelity and the fallback lesson order with safe markers. `409 PUBLICATION_BLOCKED` when the fidelity gate failed, so a blocking failure is never reviewable.
- `GET /artifacts/{artifactId}/review-package` — the review view of the **stored** package; never re-renders (~20 ms for a 28-slide deck vs ~4 s to build). `404` when nothing is built yet.
- `GET /artifacts/{artifactId}/review-package/renders/{order}` — one slide's packaged fallback render, served from the package (no re-render) after the manifest confirms it lists the asset.
- `POST /artifacts/{artifactId}/review-package/decision` — **approve or reject** the built package. `400 INVALID_REQUEST` for a rejection without a reason, `409 PUBLICATION_BLOCKED` when the document is not publishable (so a blocking failure cannot be approved), `404` when no package exists. Idempotent for a repeated identical action; returns the resulting review state.
- `GET /artifacts/{artifactId}/review-package/review-state` — the current decision, the newest draft revision, the draft count, the course-version status, and whether the decision is `stale` (recorded for a different content version).
- `POST /artifacts/{artifactId}/review-package/drafts` — **append a draft revision** of the lesson order. The body's array order is the proposed order and every entry must name a section that already exists in the package, so a draft can only reorder and re-script; structural fields are inherited from the package. `400` with an `issue_code` (`EMPTY_DRAFT`, `UNKNOWN_SECTION`, `DUPLICATE_SECTION`, `MISSING_SECTION`, `INVALID_SCRIPT`) when it is not a rearrangement, `409 REVISION_CONFLICT` when a concurrent save won the revision.
- `GET /artifacts/{artifactId}/review-package/drafts` — draft revision history, newest first.
- `GET /renderer` — renderer identity, capability, and circuit-breaker health.
- `GET /artifacts/{artifactId}` — artifact metadata (the Teacher Studio uses `filename` for its page title).
- `GET /health`.
- `GET /` — the built frontend (when `frontend/dist/` exists). Any other
  extension-less path returns the same app shell, because the frontend routes
  client-side (`/studio/{artifactId}`); unknown JSON API paths keep their own
  error responses.

## Design notes / deliberate deviations

- **SQLite** is used as the V0 local/dev equivalent of the durable relational
  store required by `DEC-DATA-001` ("PostgreSQL **or equivalent**"). The schema
  is isolated in `app/db/schema.sql` so the repository layer can target
  PostgreSQL later; the PostgreSQL reference is `database/migrations/0001_baseline.sql`
  and `database/migrations/0002_review_decisions_and_drafts.sql`.
- Extraction lives under `app/compiler/` (modular monolith). Task `V0-004`
  nominally targets a top-level `compiler/` package; within `app/compiler/` the
  layout follows the task's areas (`models/`, `extractors/`, `renderers/`,
  `validators/`). Relocate to a top-level package if/when the compiler is split
  out of the monolith.
- **`.pptx` (OOXML) only.** Legacy binary `.ppt` (and `.pptm`/`.ppsx`) is
  rejected with the stable code `UNSUPPORTED_LEGACY_FORMAT` rather than
  misparsed; no macro/script/OLE is ever executed.
- The extractor uses only the stdlib (`zipfile` + `xml.etree`) and bounds archive
  expansion (`ARCHIVE_TOO_LARGE`) to resist zip-bomb/malicious-archive threats.
- **Groups**: a `p:grpSp` holds its shapes as *immediate children* (there is no
  nested `p:spTree` inside a group). The extractor emits a `group` object and
  flattens its contents; nested groups are traversed. Containers it does not
  model (e.g. `p:contentPart`, `mc:AlternateContent`) produce an
  `unsupported element` warning instead of being dropped silently.
- Auth is a stub: the authenticated tenant comes from `X-Institution-Id`. Every
  repository call is tenant-scoped and cross-tenant access is rejected.
- **The renderer is not a decided technology.** `DEC-TECH-005` ("Native
  PowerPoint rendering deployment and licensing") is `OPEN`, so
  `docs/adr/proposed/ADR-P005_RENDERER.md` applies: *"Until accepted,
  provider-neutral interfaces and mocks are used."* `app/compiler/renderers/`
  therefore defines the `DocumentRenderer` interface plus a dependency-free local
  implementation (`StructuralSvgRenderer`, reported as `STRUCTURAL_RENDERED` —
  never as native/compatible) and a required test double. No renderer choice is
  presented as accepted; replace it behind the interface once FND-002 records the
  decision.
- **Fidelity gate**: every slide gets a render or an explicit `FAILED`;
  `FAILED`/`CANCELLED`/missing renders make the document non-publishable
  (`PUBLICATION_BLOCKED`, wired into `POST /course-versions/{id}/publish`'s
  contract for V0-008). Missing fonts and unmodeled objects degrade to
  `DEGRADED_RENDERED` with greppable warnings (`MISSING_FONT:<family>`,
  `UNSUPPORTED_OBJECT:<kind>`) and set `requires_review`.
- Rendering is deterministic and content-addressed: identical bytes + identical
  renderer identity/config produce byte-identical SVG, so recompiles reuse one
  asset. Job claiming, leases, checkpoints, and stage persistence are V0-003 and
  are not implemented here; `RenderingService` is a re-runnable stage function.
- **Baseline Content Package (V0-006).** `PackageBuildService.build()` runs the
  *baseline builder* stage: it renders (V0-005), enforces the fidelity gate, then
  maps the Content IR into the package described by `contracts/ctf/*.schema.json`
  — one scene document per slide, the fallback render copied in as a
  content-addressed asset, a fallback lesson plan (one section per scene, speaker
  notes verbatim, safe markers `<scene_id>#step-<n>`), and a manifest with
  checksums. The manifest is written **last** and is the commit point; all
  references inside the package are package-relative, so no consumer needs the
  compiler's asset store or an OOXML parser. `contracts/ctf/PACKAGE_LAYOUT.md` is
  the layout/reference contract; determinism, integrity, and negative cases are
  covered by `tests/test_package_builder.py`. There is deliberately **no HTTP
  endpoint** yet (the task's writable area is the compiler library); the
  teacher-facing preview is V0-007, publication is V0-008.
- **Teacher review (V0-007).** `app/publication/review.py` projects the *stored*
  package into the review view, so what the teacher sees is exactly what the
  runtime would receive, and browsing costs no rendering. The package id is
  derived from the same cache key as `content_package_version`
  (`pkg-<digest16>`), so identical content always resolves to one package prefix:
  a retried build completes the same package instead of duplicating it, and a
  read-only consumer can address a package without any server state. A document
  that failed the fidelity gate answers `409 PUBLICATION_BLOCKED` instead of being
  offered for review.
- **Review actions and drafts (V0-007).** `app/publication/workflow.py` records
  the two things a teacher can *change*, and neither touches the package:
  a **decision** (approve/reject) and a **draft revision** of the lesson order.
  Approving moves the course version to `APPROVED` and rejecting returns it to
  `REVIEW_REQUIRED` — review states only;
  `APPROVED → SEALING → INDEXING → COMMITTING → PUBLISHED`, the pinned index and
  the outbox are V0-008. A decision binds to the `content_package_version` it
  reviewed, so a rebuild under different content/config reports it as `stale`
  rather than letting it pass as current. Drafts are append-only revisions
  (`UNIQUE (artifact_id, revision)`), their structural fields (`scene_id`,
  `scene_step_id`, `safe_markers`, `type`) are inherited from the package under
  review, and the built package is byte-identical after any edit — which is what
  "edits create draft data, not mutate published package" means in practice.
  Both are durable relational state (`review_decisions`, `review_drafts` in
  `app/db/schema.sql`; PostgreSQL reference
  `database/migrations/0002_review_decisions_and_drafts.sql`), written in one
  transaction each, so a failure changes nothing and retrying is safe.
  `app/publication/telemetry.py` emits `publication.review.decided` /
  `publication.review.draft_saved` with counts and lengths only — a review reason
  and an edited script are never logged. Reviewer identity is client-supplied and
  is **not** an authorization control: roles arrive with the identity work in
  `docs/security/IDENTITY_AUTHORIZATION_AND_TOKENS.md`.
