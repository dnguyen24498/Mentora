# Frontend

Upload UI for course materials (`.pptx`) plus the Teacher Studio review page.
React + TypeScript + Tailwind, built with Vite.

## Ports

| Service | Port |
| --- | --- |
| Frontend (Vite dev server) | **8000** |
| Backend API | **8001** |

Vite proxies `/courses`, `/artifacts`, and `/health` to the backend
(`MENTORA_BACKEND_ORIGIN`, default `http://127.0.0.1:8001`), so the browser only
ever talks to `:8000` — no CORS.

## Run (two terminals)

```bash
# terminal 1: backend API on :8001
cd backend && env -u PYTHONPATH .venv/bin/uvicorn app.api.app:create_app --factory --port 8001

# terminal 2: frontend on :8000 (hot reload)
cd frontend && npm install && npm run dev
```

Open <http://localhost:8000>.

### Accessing through a hostname / tunnel

Vite blocks unknown `Host` headers. If you reach the dev server via a domain
(e.g. `dev.nguynx.uk`), add it to `server.allowedHosts` in `vite.config.ts` — or
set the comma-separated `MENTORA_ALLOWED_HOSTS` env var:

```bash
MENTORA_ALLOWED_HOSTS=dev.nguynx.uk,other.example ./run.sh
```

The default allows `dev.nguynx.uk`. API proxying is unaffected (it happens
server-side), so the API still works from any allowed host.

## Production-style build (optional)

`npm run build` emits `frontend/dist/`. If you don't want a separate frontend
server, the backend serves that build at `/` when it exists, giving a single
origin (point the browser at the backend port, e.g. `:8001`).

## What it does

- Takes an **Institution ID** (sent as the `X-Institution-Id` tenant header,
  persisted in `localStorage`).
- Lists the tenant's courses (`GET /courses`) and can create one (`POST /courses`).
- Lists the selected course's already-uploaded presentations
  (`GET /courses/{id}/materials`) with size, version and job status, and lets you
  **select one** to inspect it.
- Uploads or drag-and-drops a `.pptx` (`POST /courses/{id}/materials`).
- Selecting a file (or finishing an upload) shows its stored artifact metadata and
  runs structural extraction (`POST /artifacts/{id}/extract`), rendering the full
  content in the IR viewer (`src/components/ContentIrView.tsx`): every object per
  slide, all paragraphs, tables as tables, images with their media reference,
  group nesting, and slide notes.
- **Open Teacher Studio** (V0-007, `src/components/TeacherStudio.tsx`) is the
  course-version review page. It reads the package already built for the file
  (`GET /artifacts/{id}/review-package`, no re-render); the first open of a file
  builds it (`POST` the same path) and later opens are instant.
  - **Side by side**: the rendered fallback for the selected slide next to the
    extracted text, the speaker notes and the fidelity/warnings (including
    missing fonts).
  - **Warnings & blocking status**: a document that failed the fidelity gate is
    never offered for review at all (`PUBLICATION_BLOCKED`); if a non-publishable
    projection is shown, the blocking failure is announced in a `role="alert"`
    region and **Approve is disabled** and wired to that region with
    `aria-describedby`, so a blocking failure cannot be approved from the UI (the
    server refuses it too).
  - **Approve / reject**: approve moves the course version to `APPROVED`, reject
    (which requires a reason) returns it to `REVIEW_REQUIRED`. Both are shown with
    the content version they cover; a decision recorded for other content is
    labelled **stale**. Sealing, indexing and publication are V0-008 — approving
    here does not publish.
  - **Lesson order & script edits**: reorder sections or rewrite a script and
    **Save draft**. Saving appends a draft *revision*
    (`POST /artifacts/{id}/review-package/drafts`) and the page says so: the
    built package is never modified, and the draft is data for a future version.
    A refused edit reports the server's stable `issue_code`.
  - **Keyboard and screen reader**: every action is a real `<button>` (reorder
    buttons are labelled "Move section N (type) up/down" and announce the result
    in a live region), the lesson order is an `<ol>`, each script has a label, the
    slide panes expose headings, ← / → move between slides (unless focus is in a
    text field), and status/error messages are `role="status"` / `role="alert"`.

  Notes:
  - The slide SVG is fetched by the client and displayed from an object URL,
    because `<img src>` cannot send the `X-Institution-Id` header.
  - The render is a **structural placeholder**, not a native PowerPoint render;
    the UI says so (`DEC-TECH-005` is still `OPEN`).
  - Reviewer identity is not implemented yet (the tenant header is the only
    principal), so the reviewer field is attribution only and defaults to the
    tenant id.

## Tests

```bash
cd frontend && npm test          # vitest run (component tests)
cd frontend && npx tsc --noEmit  # part of npm run build
```

`src/components/TeacherStudio.test.tsx` covers the V0-007 UI requirements with
vitest + Testing Library on jsdom: the side-by-side render/extracted information,
the blocking-warning path (alert + disabled, described Approve), approve/reject,
the reject-requires-a-reason rule, stale decisions, keyboard-operable reordering
and the draft payload, and basic screen-reader structure. Test deps are
**dev-only**; the production build and its dependencies are unchanged.

Only `.pptx` (OOXML) is accepted; legacy `.ppt` is rejected by the backend with
`UNSUPPORTED_LEGACY_FORMAT`.
