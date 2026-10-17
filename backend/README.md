# Backend (modular monolith)

Python backend for the AI Teacher Platform. The V0 vertical implemented so far:
**secure PPTX ingestion + SQLite-backed persistence + deterministic structural
extraction + per-slide rendering that reproduces the deck's own styling, behind
an explicit fidelity gate + a baseline Content Package + teacher review**
(preview, approve/reject, draft lesson-order and script edits).

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
| `app/compiler/models/` | Internal Content IR (`content-ir/1.2.0`): scenes, objects, effective style (fill/line/geometry/text), text runs, media refs, normalized bounds, fidelity, provenance. |
| `app/compiler/extractors/` | Dependency-free PPTX (OOXML) structural extractor (`PptxExtractor`): theme/master/layout resolution (`theme.py`, `style.py`) + `ooxml.py` part/name helpers. |
| `app/compiler/renderers/` | Provider-neutral `DocumentRenderer` adapter + two deterministic local SVG renderers behind a mode factory — themed (default, V0-019) and faithful/structural (V0-005, V0-018) — plus the theme (`mentora_theme.py`) and a required test double. |
| `app/compiler/validators/` | Scene/package invariants and the fidelity publication gate (V0-005) plus CTF package validation (V0-006). |
| `app/compiler/render_service.py` | `RenderingService`: artifact -> Content IR -> per-slide render (mode-selected) -> gate. |
| `app/compiler/package_builder/` | Baseline Content Package builder (V0-006): IR + renders -> scenes/lesson plan/manifest, plus `read_package` for reading one back. |
| `app/compiler/service.py` | `ExtractionService`: artifact -> Content IR -> job status. |
| `app/publication/` | Teacher review of a built package (V0-007): the read-only projection (`review.py`) plus the write path (`workflow.py`, `repository.py`, `draft.py`) — approve/reject and draft lesson-order revisions. Publication state transitions are V0-008. |
| `app/db/` | SQLite connection handling (`Database`: one connection per thread) + schema/migration application. |
| `app/api/` | FastAPI app factory; serves the built frontend at `/` when present, with an SPA fallback for client-side routes (`spa.py`). |
| `app/common/` | Base errors and stable error codes. |

## Endpoints

- `POST /courses` — create a course; `title` query param, optional `course_id`.
- `GET /courses` — list the tenant's courses (used by the frontend picker).
- `GET /courses/{courseId}/materials` — list the course's uploaded presentations, newest first, each with its version number and compiler-job status (used by the frontend file list).
- `POST /courses/{courseId}/materials` — multipart `file`; returns `202` with artifact/job/version ids. Duplicate bytes (or a repeated `Idempotency-Key`) return the existing record with `created: false`.
- `POST /artifacts/{artifactId}/extract` — runs structural extraction and returns the Content IR.
- `POST /artifacts/{artifactId}/compile` — extraction + a fallback render for every slide + the fidelity gate; returns `content_ir`, `render`, `validation`, `job_status`. Idempotent. `?mode=themed|faithful` picks the render mode (V0-019, default `themed`); an unknown mode is `400 INVALID_REQUEST` (`UNKNOWN_RENDER_MODE`).
- `GET /artifacts/{artifactId}/renders/{order}` — the deterministic fallback visual (SVG) for one slide, re-derived from the stored artifact and tenant-scoped. `?mode=` as above.
- `POST /artifacts/{artifactId}/review-package` — **V0-007**: builds the Baseline Content Package (V0-006, idempotent) and returns the teacher review view — per-slide render reference, extracted text, notes, warnings/fidelity and the fallback lesson order with safe markers. `409 PUBLICATION_BLOCKED` when the fidelity gate failed, so a blocking failure is never reviewable.
- `GET /artifacts/{artifactId}/review-package` — the review view of the **stored** package; never re-renders (~20 ms for a 28-slide deck vs ~4 s to build). `404` when nothing is built yet.
- `GET /artifacts/{artifactId}/review-package/renders/{order}` — one slide's packaged fallback render, served from the package (no re-render) after the manifest confirms it lists the asset.
- `POST /artifacts/{artifactId}/review-package/decision` — **approve or reject** the built package. `400 INVALID_REQUEST` for a rejection without a reason, `409 PUBLICATION_BLOCKED` when the document is not publishable (so a blocking failure cannot be approved), `404` when no package exists. Idempotent for a repeated identical action; returns the resulting review state.
- `GET /artifacts/{artifactId}/review-package/review-state` — the current decision, the newest draft revision, the draft count, the course-version status, and whether the decision is `stale` (recorded for a different content version).
- `POST /artifacts/{artifactId}/review-package/drafts` — **append a draft revision** of the lesson order. The body's array order is the proposed order and every entry must name a section that already exists in the package, so a draft can only reorder and re-script; structural fields are inherited from the package. `400` with an `issue_code` (`EMPTY_DRAFT`, `UNKNOWN_SECTION`, `DUPLICATE_SECTION`, `MISSING_SECTION`, `INVALID_SCRIPT`) when it is not a rearrangement, `409 REVISION_CONFLICT` when a concurrent save won the revision.
- `GET /artifacts/{artifactId}/review-package/drafts` — draft revision history, newest first.
- `GET /renderer` — the default render mode, every available mode, the active theme, and the requested mode's identity/capability/circuit-breaker health (`?mode=`, V0-019).
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
- **Connections are thread-scoped (V0-020).** FastAPI serves the sync endpoints
  from a worker threadpool, so requests really do overlap. A `sqlite3.Connection`
  cannot be shared for that: `BEGIN`/`COMMIT` state and cursors are
  connection-scoped, so two requests on one connection interleave (one request's
  `BEGIN` lands inside another's transaction; a cursor is consumed while another
  thread runs a statement on it). `Database` hands each thread its own connection
  while repositories keep calling the same `self._conn.execute(...)` and
  `transaction(self._conn)`. Each connection sets `PRAGMA busy_timeout` (5 s), so a
  queued writer waits for SQLite's write lock instead of failing with
  `database is locked` — bounded failure (`DEC-RELIABILITY-001`), not a hang.
  `tests/test_database_concurrency.py` holds this contract: 240 concurrent
  read+write requests must all succeed and every reported write must be visible.
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
  therefore defines the `DocumentRenderer` interface, a required test double, and
  two dependency-free local implementations behind it (`renderers/factory.py`
  selects by mode) — neither is ever reported as native/compatible:
  - **`themed` (default, V0-019)** — `ThemedSvgRenderer` **re-authors** the
    extracted content in a platform-controlled theme (`renderers/mentora_theme.py`:
    palette, type scale, grid, footer) and reports `THEMED_RENDERED`. The theme
    owns its typefaces, so an unavailable source font can never degrade a scene;
    the source deck's own layout is deliberately *not* reproduced. Because it is a
    re-authoring, the gate is re-scoped from visual fidelity to **content
    completeness**: every text paragraph, picture, and table cell is placed, and
    `CONTENT_DROPPED:`/`TEXT_OVERFLOW:` degrade the scene instead of content being
    silently lost. An object that cannot be re-authored (chart, SmartArt) also
    degrades (`UNSUPPORTED_OBJECT:`), so it asks for review rather than being
    flattened. The theme is versioned and folded into the renderer's config hash,
    so a theme change is a new content-package version.
  - **`faithful` (V0-018)** — `StructuralSvgRenderer` reproduces the source
    slide's own styling and reports `STRUCTURAL_RENDERED`.
  - `?mode=themed|faithful` selects the mode on `POST /artifacts/{id}/compile` and
    `GET /artifacts/{id}/renders/{order}`; `GET /renderer` reports the default, all
    modes, the active theme, and the requested capability (an unknown mode is a
    `400 INVALID_REQUEST`/`UNKNOWN_RENDER_MODE`). The package cache key binds the
    renderer identity (`name@version`), so a themed package can never be mistaken
    for a faithful one. Replace these behind the interface once FND-002 records the
    decision.
- **Fidelity gate**: every slide gets a render or an explicit `FAILED`;
  `FAILED`/`CANCELLED`/missing renders make the document non-publishable
  (`PUBLICATION_BLOCKED`, wired into `POST /course-versions/{id}/publish`'s
  contract for V0-008). Missing fonts and unmodeled objects degrade to
  `DEGRADED_RENDERED` with greppable warnings (`MISSING_FONT:<family>`,
  `UNSUPPORTED_OBJECT:<kind>`) and set `requires_review`.
- **Faithful slide rendering (V0-018).** `DEC-TECH-005` is still `OPEN`, so this
  is explicitly *not* a native PowerPoint engine: the renderer draws the
  presentation **from the Content IR**. Fidelity comes from extraction, not from
  a new dependency — the IR resolves the deck's effective look (theme colours and
  fonts through `p:clrMap`, slide→layout→master placeholder geometry and
  `p:txStyles` defaults, backgrounds, fills/lines/gradients/geometry/rotation,
  run+paragraph formatting, `srcRect` crops, table metrics) and the renderer
  reproduces it in SVG. Consequences worth knowing:
  - The IR must stay self-sufficient: a renderer that opened the `.pptx` would
    break `DEC-CONTENT-001`, so image bytes travel separately in
    `RenderRequest.media`, keyed by the IR's `media_ref`.
  - Pictures are inlined as `data:` URIs (the studio shows the SVG through a
    `blob:` `<img>`, where external references cannot resolve). A per-scene raw
    budget (`RenderConfig.max_inline_media_bytes`, 16 MiB) and an output cap
    (`max_asset_bytes`, 28 MiB) keep one slide from bloating the package.
    Over-budget or non-inlinable (EMF/WMF/TIFF) pictures render as a labelled
    placeholder with a `MEDIA_BUDGET_EXCEEDED:`/`UNSUPPORTED_*` warning but do
    **not** change fidelity — escaping the budget is a rendering limitation, not
    a meaning change, so the gate's taxonomy (`MISSING_FONT`,
    `UNSUPPORTED_OBJECT`) is unchanged.
  - Text uses estimated glyph advances for word-wrap and auto-shrink
    (PowerPoint never overflows a text box); there is no font metric library in
    the stdlib. Charts, SmartArt, animation and exotic effects remain placeholders.
  - The renderer identity is bumped to `2.0.0` and the IR schema to
    `content-ir/1.2.0`; both are part of the cache key, so stale renders are not
    reused after this change.
- **Themed slide rendering (V0-019, the default mode).** `ThemedSvgRenderer`
  classifies each slide into an archetype (`title`/`bullets`/`content`/`table`/
  `media`/`mixed`/`empty` — `classify_scene` is a pure, tested function of the IR)
  and re-flows its content: a heading block (a title slide is a *hero*: larger and
  vertically centred), a body flow of paragraphs with theme bullets and preserved
  emphasis/alignment, pictures framed to their **own aspect ratio** (read from the
  image header by `compiler/imaging.py`, no image library) and capped so a picture
  can never overflow on its own, and tables with a themed header row. It
  **re-flows, never re-selects**: decorative geometry is re-themed away on purpose
  while every text paragraph, picture, and table cell is placed — no LLM rewrites
  slide text, because that would change meaning. If content still does not fit, the
  flow shrinks to a readable floor and then reports `TEXT_OVERFLOW:` and degrades;
  content is never silently dropped, and `CONTENT_DROPPED:` is the completeness
  gate's alarm if it ever were.
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
