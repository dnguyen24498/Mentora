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
| `app/compiler/renderers/` | Provider-neutral `DocumentRenderer` adapter + two deterministic local SVG renderers behind a mode factory — faithful/structural (default, V0-005/V0-018) and themed (opt-in, V0-019) — plus the theme (`mentora_theme.py`) and a required test double. |
| `app/compiler/validators/` | Scene/package invariants and the fidelity publication gate (V0-005) plus CTF package validation (V0-006). |
| `app/compiler/render_service.py` | `RenderingService`: artifact -> Content IR -> per-slide render (mode-selected) -> gate. |
| `app/compiler/package_builder/` | Baseline Content Package builder (V0-006): IR + renders -> scenes/lesson plan/manifest, plus `read_package` for reading one back. |
| `app/compiler/service.py` | `ExtractionService`: artifact -> Content IR -> job status. |
| `app/publication/` | Teacher review of a built package (V0-007, `review.py`/`workflow.py`/`draft.py`) **and** the atomic publication transition (V0-008, `service.py`/`seal.py`/`index.py`/`outbox.py`): seal (checksums + digests) → index-version pin → one commit transaction → published-version retrieval. |
| `app/db/` | SQLite connection handling (`Database`: one connection per thread) + schema/migration application. |
| `app/api/` | FastAPI app factory; serves the built frontend at `/` when present, with an SPA fallback for client-side routes (`spa.py`). |
| `app/common/` | Base errors and stable error codes. |

## Endpoints

- `POST /courses` — create a course; `title` query param, optional `course_id`.
- `GET /courses` — list the tenant's courses (used by the frontend picker).
- `GET /courses/{courseId}/materials` — list the course's uploaded presentations, newest first, each with its version number and compiler-job status (used by the frontend file list).
- `POST /courses/{courseId}/materials` — multipart `file`; returns `202` with artifact/job/version ids. Duplicate bytes (or a repeated `Idempotency-Key`) return the existing record with `created: false`.
- `POST /artifacts/{artifactId}/extract` — runs structural extraction and returns the Content IR.
- `POST /artifacts/{artifactId}/compile` — extraction + a fallback render for every slide + the fidelity gate; returns `content_ir`, `render`, `validation`, `job_status`. Idempotent. `?mode=faithful|themed` picks the render mode (V0-019 v5, default `faithful`); an unknown mode is `400 INVALID_REQUEST` (`UNKNOWN_RENDER_MODE`).
- `GET /artifacts/{artifactId}/renders/{order}` — the deterministic fallback visual (SVG) for one slide, re-derived from the stored artifact and tenant-scoped. `?mode=` as above.
- `POST /artifacts/{artifactId}/review-package` — **V0-007**: builds the Baseline Content Package (V0-006, idempotent) and returns the teacher review view — per-slide render reference, extracted text, notes, warnings/fidelity and the fallback lesson order with safe markers. `409 PUBLICATION_BLOCKED` when the fidelity gate failed, so a blocking failure is never reviewable.
- `GET /artifacts/{artifactId}/review-package` — the review view of the **stored** package; never re-renders (~20 ms for a 28-slide deck vs ~4 s to build). `404` when nothing is built yet.
- `GET /artifacts/{artifactId}/review-package/renders/{order}` — one slide's packaged fallback render, served from the package (no re-render) after the manifest confirms it lists the asset.
- `POST /artifacts/{artifactId}/review-package/decision` — **approve or reject** the built package. `400 INVALID_REQUEST` for a rejection without a reason, `409 PUBLICATION_BLOCKED` when the document is not publishable (so a blocking failure cannot be approved), `404` when no package exists. Idempotent for a repeated identical action; returns the resulting review state.
- `GET /artifacts/{artifactId}/review-package/review-state` — the current decision, the newest draft revision, the draft count, the course-version status, and whether the decision is `stale` (recorded for a different content version).
- `POST /artifacts/{artifactId}/review-package/drafts` — **append a draft revision** of the lesson order. The body's array order is the proposed order and every entry must name a section that already exists in the package, so a draft can only reorder and re-script; structural fields are inherited from the package. `400` with an `issue_code` (`EMPTY_DRAFT`, `UNKNOWN_SECTION`, `DUPLICATE_SECTION`, `MISSING_SECTION`, `INVALID_SCRIPT`) when it is not a rearrangement, `409 REVISION_CONFLICT` when a concurrent save won the revision.
- `GET /artifacts/{artifactId}/review-package/drafts` — draft revision history, newest first.
- `POST /course-versions/{versionId}/publish` — **V0-008**: seal the built package (verify checksums/references, record the manifest and content digests), establish the compatible knowledge-index version, and commit the publication + index pin + outbox event in **one transaction**; returns the publication with `created`. Idempotent on `(versionId, content_package_version)`: a replay returns the same publication with `created: false`. `409 PUBLICATION_BLOCKED` with an `issue_code` (`NOT_APPROVED`, `STALE_APPROVAL`, `WRONG_STATE`, the validator's code, `INDEX_FAILED`) when the version must not be published; nothing is written. `404` when no package is built.
- `GET /course-versions/{versionId}/publication` — the version's newest publication (`404` when unpublished). `?verify=true` re-reads the pinned package and re-checks it against the digest sealed at publish time, adding an `integrity` report (`VERIFIED`/`MISMATCH`/`MISSING`).
- `GET /publications/{publicationId}` — one publication by identity, **including a superseded one** (a session pinned to it keeps reading it). Another institution's is `404`, not `403` (the lookup is tenant-scoped and does not leak existence). `?verify=true` as above.
- `GET /courses/{courseId}/publications` — the course's publication history, newest first, superseded ones included (`?limit=`, default 50).
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
  - **`faithful` (default, V0-019 v5)** — `StructuralSvgRenderer` reproduces the
    **source slide's own layout and styling** (V0-018) and reports
    `STRUCTURAL_RENDERED`: the effective theme colours and font scheme, backgrounds
    (including a layout's **picture** background — resolved against the layout's own
    relationships), the art the slide **inherits** from its layout/master (V0-019 v7),
    preset + `custGeom` shapes, fills/strokes/dashes, rotation/flip, real font sizes
    with wrap/alignment/bullets, embedded pictures with crop, tables and connectors.
    A component it cannot reproduce is **drawn in the platform look, in place**
    (`renderers/mentora_theme.py`), never dropped and never a review blocker:
    an unavailable source font is *substituted* with the platform's type stack
    (deterministically — the client's fonts cannot change the asset) and recorded
    as `FONT_SUBSTITUTED:<family>`, and a frame whose font was substituted is shrunk
    to stay inside the author's frame instead of spilling over its neighbour; a
    chart/SmartArt/WordArt/equation/graphic frame becomes a flat platform panel
    labelled with the object (`UNSUPPORTED_OBJECT:<kind>`); a picture that cannot be
    inlined (EMF/WMF/TIFF, over budget, bytes withheld) becomes a flat platform
    panel labelled with the part. Keeping the author's layout also means keeping the
    author's overlaps: where a source deck's own frames overlap, the overlap is
    reproduced, exactly as PowerPoint shows it.
  - **`themed` (opt-in, V0-019 v4)** — `ThemedSvgRenderer` **keeps the author's
    grouping and re-authors the look**: the grouping and content are the author's,
    the arrangement within each group and the appearance are the platform's
    (`renderers/flow.py` + `renderers/textmetrics.py` + `renderers/mentora_theme.py`),
    reporting `THEMED_RENDERED`. A binary widest-gap XY-cut over the source boxes
    recovers the slide's rows and columns (an icon stays beside its label; a column
    is only cut when both sides are a substantial share of the region), and each
    recovered cell is folded into flow blocks (a merged list of paragraphs, a
    table, a row of pictures) placed by a single measuring pass over a cursor:
    position and measurement are the same computation, so blocks cannot overlap by
    construction (`tests/test_flow_layout.py` asserts the invariant pairwise over
    the emitted geometry). A row cell that draws more than one block becomes a
    card: the content is inset and a flat surface panel (no border) is painted
    behind it. A heading is hoisted (kicker/title/subtitle over one
    hairline rule) and the page number lives in a reserved bottom strip the flow
    may not enter. The look is entirely the platform's: its type stack, its type
    scale, its palette; no source typeface, colour, fill or geometry is
    reproduced. The gate is therefore **content completeness**, and no code path
    can lose content: nothing is re-selected, re-ordered, or dropped, and content
    that cannot be fitted even at the smallest readable type scale is still drawn
    (flagged `TEXT_OVERFLOW:<scene>`, degraded for review, page number omitted so
    nothing is covered). An object that cannot be redrawn (chart, SmartArt) becomes
    a labelled panel and degrades (`UNSUPPORTED_OBJECT:`). The theme is versioned
    and folded into the renderer's config hash, so a theme change is a new
    content-package version.
  - `?mode=faithful|themed` selects the mode on `POST /artifacts/{id}/compile` and
    `GET /artifacts/{id}/renders/{order}`; `GET /renderer` reports the default, all
    modes, the active theme, and the requested capability (an unknown mode is a
    `400 INVALID_REQUEST`/`UNKNOWN_RENDER_MODE`). The package cache key binds the
    renderer identity (`name@version`), so a themed package can never be mistaken
    for a faithful one. Replace these behind the interface once FND-002 records the
    decision.
- **Fidelity gate**: every slide gets a render or an explicit `FAILED`;
  `FAILED`/`CANCELLED`/missing renders make the document non-publishable
  (`PUBLICATION_BLOCKED`, wired into `POST /course-versions/{id}/publish`'s
  contract for V0-008). `DEGRADED_RENDERED` scenes require review. A component the
  default renderer draws in the platform look, and a source font it had to
  substitute, are **warnings** on a structural scene — greppable
  (`FONT_SUBSTITUTED:<family>`, `UNSUPPORTED_OBJECT:<kind>`, `UNSUPPORTED_MEDIA:`,
  `MEDIA_BUDGET_EXCEEDED:`, `MEDIA_UNAVAILABLE:`) and disclosed in the review's
  `missing_fonts`/`warnings`, but they do **not** set `requires_review`, because
  nothing is missing from the output.
- **Faithful slide rendering (V0-018, the default mode since V0-019 v5).**
  `DEC-TECH-005` is still `OPEN`, so this is explicitly *not* a native PowerPoint
  engine: the renderer draws the presentation **from the Content IR**. Fidelity
  comes from extraction, not from a new dependency — the IR resolves the deck's
  effective look (theme colours and fonts through `p:clrMap`, slide→layout→master
  placeholder geometry and `p:txStyles` defaults, backgrounds,
  fills/lines/gradients/geometry/rotation, run+paragraph formatting, `srcRect`
  crops, table metrics) and the renderer reproduces it in SVG. Consequences worth
  knowing:
  - **Backgrounds cascade across parts, and their images belong to the part that
    declares them.** A deck's art-directed (usually dark) backgrounds live on the
    title/section **layouts**, so each level resolves against its own
    relationships; an unresolvable picture fails through to the next background up
    with a warning instead of blanking the slide. Missing that turns a dark closing
    slide into white-on-white.
  - **A slide also draws what its layout and master contribute** (V0-019 v7).
    Decks keep their shared chrome — the crest, the faculty badge, a rule, a static
    label — on the **layout**, not on every slide, and PowerPoint paints it *under*
    the slide's own objects. Extraction collects the **non-placeholder** art of the
    master and the layout (`inherited_objects`, each part resolved against its own
    relationships, `showMasterSp` honoured on the slide and on the layout) and the
    renderer paints it master-first, layout-second, the slide's own objects last. A
    layout/master placeholder is not art — it is a definition the slide's own
    placeholder replaces — and inherited objects are not slide content: they never
    join `objects`, the slide's text, its reading order or its `object_count`.
    Without this the reference deck's 26 slides lose the top-right logo pair they
    carry only in the layout. Because the parts are the author's, a high-resolution
    logo is inlined at its source resolution on every slide that inherits it
    (reference deck: ~500 KB per slide) — the per-scene budget is what bounds it,
    and the opt-in `themed` mode does not carry the chrome at all.
  - The IR must stay self-sufficient: a renderer that opened the `.pptx` would
    break `DEC-CONTENT-001`, so image bytes travel separately in
    `RenderRequest.media`, keyed by the IR's `media_ref`.
  - Pictures are inlined as `data:` URIs (the studio shows the SVG through a
    `blob:` `<img>`, where external references cannot resolve). A per-scene raw
    budget (`RenderConfig.max_inline_media_bytes`, 16 MiB) and an output cap
    (`max_asset_bytes`, 28 MiB) keep one slide from bloating the package. A
    picture that cannot be inlined (over budget, EMF/WMF/TIFF, or bytes not
    supplied) is drawn as a **flat platform panel** labelled with the part
    (`renderers/mentora_theme.py`) and warned about
    (`MEDIA_BUDGET_EXCEEDED:`/`UNSUPPORTED_MEDIA:`/`MEDIA_UNAVAILABLE:`) — in place,
    without changing fidelity.
  - **A component the source cannot be reproduced for is drawn in the platform
    look, in place** (the product rule is *"same layout as the author's deck;
    where a component cannot be reproduced, draw it in the platform's default
    look"*): an unavailable source font is substituted with the platform's type
    stack — deterministically, so the client's own fonts can never change the asset
    — and recorded as `FONT_SUBSTITUTED:<family>`; a chart/SmartArt/WordArt/
    equation/graphic frame is a flat platform panel labelled with the object
    (`UNSUPPORTED_OBJECT:<kind>`); an unknown preset geometry is its bounding
    rectangle. None of these lowers the fidelity or sets `requires_review`: the
    content is complete and the layout is the author's.
  - Text uses estimated glyph advances for word-wrap and auto-shrink (an
    auto-fitting box is never overrun; an `a:noAutofit` box that does not hold its
    text spills, as PowerPoint spills it), and a frame whose font was *substituted*
    is shrunk to stay inside the author's frame rather than spilling over a
    neighbouring block — our metrics are not the author's. There is no font metric
    library in the stdlib, so a substituted typeface can wrap a line a word earlier
    than PowerPoint would.
  - Because the author's geometry is kept, the author's *overlaps* are kept too:
    where a source deck's own frames overlap, the render reproduces the overlap,
    exactly as PowerPoint shows it.
  - The renderer identity is bumped to `3.0.0` and the IR schema to
    `content-ir/1.2.0`; both are part of the cache key, so stale renders are not
    reused after this change. (V0-019 v7 draws inherited layout/master art, so the
    identity moves on to `local-structural-svg@3.1.0` and the extractor to `1.4.0`,
    which retires packages built before it.)
- **Themed slide rendering (V0-019 v4, opt-in since v5).** `ThemedSvgRenderer`
  re-authors the *look* of each slide while keeping the *grouping* and every word,
  cell and picture the author put on it. It shares only the
  `_Canvas`/`_attr`/`_num` helpers with the structural renderer; its geometry is
  `flow.py`'s, not the source's:
  - **The grouping is the author's**: the IR objects keep their source boxes, and
    a binary widest-gap XY-cut (`flow.structure`) recovers the slide's rows and
    columns. A cell holds the objects the author grouped together, so an icon
    stays beside its label and a card keeps its parts. A column is only cut when
    both sides are a substantial share of the region width
    (`theme.min_column_share`), so a narrow icon column never splits from its
    label; a full-width object spans the region and forbids a column cut through
    it. Same-key neighbours (one bullet per text box) are re-joined into one run.
  - **Content is the author's**: each recovered cell is folded into flow blocks — a
    list of paragraphs (level indent, bullet markers when the source resolved one,
    bold/italic runs), a table (empty rows/columns dropped, source column
    proportions kept), a row of pictures (≤4 per row, aspect from the file
    header), a panel for a chart/SmartArt. A text-less decorative shape is dropped
    (it is not content).
  - **The look is the platform's**: the theme's type stack, its type scale, its
    palette (`mentora_theme.py`). Source sizes only choose a *row* (`lead`/`body`/
    `caption`, relative to the slide's most common size), so an art-directed
    statistic still reads as one. No source colour, fill, stroke or box is drawn.
    A cell that draws more than one block becomes a **card**: the content is inset
    and a flat `theme.surface` rounded panel (no border) is painted behind it.
  - **Placement is the platform's**: within a cell, blocks are measured and placed
    in the same pass, so a block always advances the cursor and can never overlap
    the next. A hoisted heading (kicker/title/subtitle + one hairline rule) sits
    above the body and the page number below it, in a strip the flow cannot enter.
  - **The gate is content completeness**: nothing is re-selected, re-ordered or
    dropped. Content that does not fit even at the smallest readable scale is
    still drawn in full and flagged `TEXT_OVERFLOW:<scene>` (degraded for review,
    page number omitted). A chart/SmartArt is a labelled panel plus
    `UNSUPPORTED_OBJECT:` and review — in this mode only; the default mode draws
    it in the platform look in place and merely warns. No LLM rewrites slide text,
    because that would change meaning.
  - **Metrics are estimated** (`textmetrics.py`: a font-free Helvetica/Arial advance
    table biased slightly wide), so a line may break a word early — it can never
    push a block into its neighbour. There is no bundled font to license or embed.
  - The theme is versioned and folded into the renderer's config hash; the
    renderer identity is `mentora-themed-svg@4.0.0`, so themed and faithful
    packages can never be confused.
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
  `REVIEW_REQUIRED` — review states only. The publication transition
  (`APPROVED → SEALING → INDEXING → COMMITTING → PUBLISHED`), the pinned index and
  the outbox are V0-008 (below). A decision binds to the `content_package_version` it
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
- **Atomic publication (V0-008).** `app/publication/service.py` runs the three
  stages and then one commit. The stages are **in-process and never persisted**, so
  there is no staging row a crash could leave behind: "partial publication is
  invisible" holds by construction, not by compensation. **SEALING** (`seal.py`)
  re-validates the stored package and computes two digests — `manifest_sha256`
  (the envelope, kept for provenance) and `content_digest` (path + SHA-256 of every
  manifest-listed file, sorted), which is the *verify* basis, so a legitimate
  rewrite of the manifest (a new `created_at`) is not a false alarm. **INDEXING**
  goes through the replaceable `IndexBuilder` interface (`index.py`):
  `BaselineIndexBuilder` establishes the index-version identity a publication must
  pin (`DEC-DATA-005`) and builds no index content — a Baseline Content Package is
  usable without enrichment (`DEC-CONTENT-002`) and the search/vector technology is
  `OPEN` (`DEC-TECH-008`), so it pins `unindexed` and records the published
  `content_digest` as the content it is compatible with. V0-014 replaces the
  builder; the record, the pin and the transaction do not move. **COMMITTING**
  (`repository.py::PublicationRepository.commit`) is one transaction that writes
  the index-version row, the publication row and the transactional-outbox row,
  performs the guarded `APPROVED → PUBLISHED` status change (the row count is the
  guard) and marks superseded publications — so a visible publication always has
  its pin and its event.
  - **Identity is content**, `(version_id, content_package_version)`, unique per
    tenant: a replay returns the *same* publication with `created: false`, and two
    concurrent publishes of one version produce exactly one (the loser re-reads the
    winner; an unrecoverable race is a classified `COMMIT_CONFLICT`). The existence
    check runs *before* the approval check, because a replay arrives when the
    version is already `PUBLISHED`, which is not the `APPROVED` precondition.
  - **A correction is a new course version** — new package, new publication.
    Publishing it marks the course's strictly older publications, and any other
    publication of the same version, `SUPERSEDED` with a `superseded_by` link.
    Nothing is deleted: `DEC-CONTENT-005` pins all compatible versions, and
    `GET /publications/{id}` serves a superseded one to the session reading it.
  - **Refusals are classified and write nothing** (`errors.py`): `409
    PUBLICATION_BLOCKED` with `NOT_APPROVED`, `STALE_APPROVAL`, `WRONG_STATE`, the
    validator's own code (e.g. `CHECKSUM_MISMATCH`) or `INDEX_FAILED`. Every one is
    raised before the transaction, so the version stays retryable
    (`DEC-RELIABILITY-002`).
  - **The seal is the read half of immutability**: `?verify=true` on either read
    endpoint re-reads the *pinned* prefix (not the one the current renderer
    implies) and reports `VERIFIED`/`MISMATCH`/`MISSING` against the recorded
    digest rather than erroring.
  - Durable state: `publications`, `knowledge_index_versions` and
    `publication_outbox` in `app/db/schema.sql` (PostgreSQL reference
    `database/migrations/0003_atomic_publication.sql`). The outbox row is written
    but **not dispatched** — delivery technology is `OPEN` (`DEC-TECH-001`), so
    `dispatched_at` stays null until a later task adds a sender.
    `app/publication/telemetry.py` emits `publication.stage`,
    `publication.published`, `publication.blocked` and
    `publication.integrity_checked` with the version tuple and counts only — never
    slide text, notes or a review reason. Covered by
    `tests/test_publication_publish.py` (19): the happy path, the index pin and its
    provenance, the outbox event (and its JSON-Schema contract), duplicate and
    concurrent publish, a crash at each stage (nothing published, retry succeeds),
    checksum and index failure, a stale/absent approval, publishing writing no
    bytes, a correction leaving the old package readable, tamper detection, tenant
    isolation, and telemetry.
