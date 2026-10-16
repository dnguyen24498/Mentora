# Backend (modular monolith)

Python backend for the AI Teacher Platform. This slice implements the first V0
vertical: **secure PPTX ingestion + SQLite-backed persistence + deterministic
structural extraction + per-slide fallback rendering with an explicit fidelity
gate**.

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
For normal development the frontend runs on its own server at `:8000` — see
`frontend/README.md`.

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
| `app/compiler/package_builder/` | Baseline Content Package builder (V0-006): IR + renders -> scenes/lesson plan/manifest. |
| `app/compiler/service.py` | `ExtractionService`: artifact -> Content IR -> job status. |
| `app/db/` | SQLite connection + schema/migration application. |
| `app/api/` | FastAPI app factory; serves the built frontend at `/` when present. |
| `app/common/` | Base errors and stable error codes. |

## Endpoints

- `POST /courses` — create a course; `title` query param, optional `course_id`.
- `GET /courses` — list the tenant's courses (used by the frontend picker).
- `GET /courses/{courseId}/materials` — list the course's uploaded presentations, newest first, each with its version number and compiler-job status (used by the frontend file list).
- `POST /courses/{courseId}/materials` — multipart `file`; returns `202` with artifact/job/version ids. Duplicate bytes (or a repeated `Idempotency-Key`) return the existing record with `created: false`.
- `POST /artifacts/{artifactId}/extract` — runs structural extraction and returns the Content IR.
- `POST /artifacts/{artifactId}/compile` — extraction + a fallback render for every slide + the fidelity gate; returns `content_ir`, `render`, `validation`, `job_status`. Idempotent.
- `GET /artifacts/{artifactId}/renders/{order}` — the deterministic fallback visual (SVG) for one slide, re-derived from the stored artifact and tenant-scoped.
- `GET /renderer` — renderer identity, capability, and circuit-breaker health.
- `GET /artifacts/{artifactId}` — artifact metadata.
- `GET /health`.
- `GET /` — the built upload UI (when `frontend/dist/` exists).

## Design notes / deliberate deviations

- **SQLite** is used as the V0 local/dev equivalent of the durable relational
  store required by `DEC-DATA-001` ("PostgreSQL **or equivalent**"). The schema
  is isolated in `app/db/schema.sql` so the repository layer can target
  PostgreSQL later; the PostgreSQL reference is `database/migrations/0001_baseline.sql`.
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
