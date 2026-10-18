# Frontend

Material library (`.pptx` upload), the Teacher Studio review page, and the
Classroom runtime page, as real pages of one Vite app. React + TypeScript +
Tailwind, built with Vite.

## Pages and routing

| URL | Page | File |
| --- | --- | --- |
| `/` | Material library — courses, upload, extracted Content IR | `src/pages/UploadPage.tsx` |
| `/studio/{artifactId}` | Teacher Studio — full-width slide review of one deck | `src/pages/StudioPage.tsx` |
| `/classroom/{classId}` | Classroom — authoritative runtime state of a session (V0-011) | `src/classroom/ClassroomPage.tsx` |
| anything else | The app's own not-found view | `src/App.tsx` |

The teacher review flow is a **page of its own**, not a panel on the upload page:
it is the large-screen slide surface, so it is opened directly (a new tab, a
second monitor, a bookmark), survives a deep link and a refresh, and sets its own
document title to the file name.

Routing is `src/router.tsx` — a ~70-line dependency-free `useRoute` / `navigate` /
`Link` module (no router dependency: a handful of static pages do not justify one,
and the project adds no production dependency without an accepted decision).
`Link` renders a real `<a href>`, so middle-click, ctrl/cmd-click and "open in new
tab" behave natively; only a plain left click is routed client-side.

Because the paths are real, the **server** must answer them: the Vite dev server
already serves the app shell, and in single-origin mode the backend does it with
`backend/app/api/spa.py` (`SpaStaticFiles`), which returns `index.html` for any
extension-less 404 while still serving real assets and still 404ing a *missing*
asset. The tenant is stored in `localStorage` (`src/institution.ts`) so a studio
tab opened separately shares it with the library tab.

## Ports

| Service | Port |
| --- | --- |
| Frontend (Vite dev server) | **8000** |
| Backend API | **8001** |

Vite proxies `/courses`, `/artifacts`, `/classes`, and `/health` to the backend
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
origin (point the browser at the backend port, e.g. `:8001`). Client-side routes
are part of that contract: `backend/app/api/spa.py` answers `/studio/{artifactId}`
(and any other extension-less path) with the app shell, so a deep link or a
refresh works in single-origin mode too.

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
- **Open Teacher Studio** opens `/studio/{artifactId}` (V0-007,
  `src/pages/StudioPage.tsx`), the course-version review page. It reads the
  package already built for the file (`GET /artifacts/{id}/review-package`, no
  re-render); the first open of a file builds it (`POST` the same path) and later
  opens are instant. From the library it can also be opened **in a new tab**.
  The page loads the artifact metadata for its title
  (`GET /artifacts/{id}` → filename), so a studio tab is identifiable on its own.
  - **Large screen**: the page is full width (no content column), **Focus slide**
    collapses the lesson-order editor so the slide takes the whole width, and
    **Full screen** puts the slide region itself into browser fullscreen (offered
    only where the browser implements it).
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
    Focus mode hides the editor from the accessibility tree rather than deleting
    it, so unsaved edits survive a toggle.

  Notes:
  - The slide SVG is fetched by the client and displayed from an object URL,
    because `<img src>` cannot send the `X-Institution-Id` header.
  - The render is a **structural placeholder**, not a native PowerPoint render;
    the UI says so (`DEC-TECH-005` is still `OPEN`).
  - Reviewer identity is not implemented yet (the tenant header is the only
    principal), so the reviewer field is attribution only and defaults to the
    tenant id.

## Classroom (V0-011)

`/classroom/{classId}` is the runtime view of a session. It is a **projection** —
the Classroom Actor owns the truth — rebuilt from the authoritative snapshot
(`GET /classes/{id}/snapshot`) plus contiguous ordered events, so a **refresh
restores scene and state**.

- **State** lives in `src/classroom/state/`, split into separate slices
  (`ClassroomStore`): the raw **snapshot**, the **event reducer**, **media** and
  **ephemeral UI / accessibility preferences**. Only the reducer slice is derived
  from the actor; media and UI are client-only.
- **`reducer.ts`** is pure: it applies an event only when it is contiguous for the
  current epoch (`sequence === lastSequence + 1`), **ignores duplicates and stale
  events** (`sequence <= lastSequence`), **discards an effect from a superseded
  epoch**, and reports a **sequence gap** rather than applying out of order.
- **`session.ts`** wires a store to a transport: a gap, a stale epoch, or the
  **Resynchronise** button re-reads the authoritative snapshot (bounded retry) and
  resets the event cursor. A failed load leaves the client `disconnected` and
  frozen.
- **`ClassroomShell.tsx`** shows the scene identity and the authoritative state
  (epoch, sequence, state version, checkpoint), previous/next scene and resync
  controls — the command controls are disabled whenever the client is not `live`
  — a recovery banner (`role="status"` / `role="alert"`), and accessibility
  preference toggles (reduced motion, high contrast) persisted to `localStorage`.
- **Transport** (`transport.ts`) is an interface. The ordered per-class
  command/event mechanism is `DEC-DATA-003` and its technology is `OPEN`, so the
  shipped transport reads the snapshot only and advertises
  `liveEvents:false`/`commands:false`; the page says so instead of faking a
  stream. The live stream and command path are V1-002. Tests and a local demo
  drive events through the injected `ClassroomTransport`.
- **Telemetry** (`telemetry.ts`) emits structured events and counters — identities
  and outcomes only, never scene text, transcript or audio.

Out of scope here (and kept inactive by design): microphone, Raise Hand and
WebRTC. `studentMicActive` is always `false` (`DEC-TURN-001`).

## Tests

```bash
cd frontend && npm test          # vitest run (component tests)
cd frontend && npx tsc --noEmit  # part of npm run build
```

`src/components/TeacherStudio.test.tsx` covers the V0-007 UI requirements with
vitest + Testing Library on jsdom: the side-by-side render/extracted information,
the blocking-warning path (alert + disabled, described Approve), approve/reject,
the reject-requires-a-reason rule, stale decisions, keyboard-operable reordering
and the draft payload, focus mode, and basic screen-reader structure.
`src/pages/StudioPage.test.tsx` covers the page's orchestration (load vs build,
the visible rendering phase, unloadable packages, the server's refusal, draft
saves) with a mocked API client; `src/App.test.tsx` covers the routing between
the pages including a deep link; `src/router.test.tsx` covers route parsing
and the `Link`/`navigate` behaviour. Test deps are **dev-only**; the production
build and its dependencies are unchanged.

`src/classroom/state/reducer.test.ts` is the pure-reducer acceptance suite
(contiguous apply, duplicate/stale ignored, gap reported and not applied,
superseded epoch discarded, unknown event advances the cursor); 
`src/classroom/state/session.test.ts` covers connect, gap → resync → recover,
bounded-retry disconnect and the telemetry contract; 
`src/classroom/ClassroomPage.test.tsx` is the component-level end-to-end
(refresh restores scene/state, duplicate ignored, gap freezes controls and
recovers, accessibility smoke), with the event stream driven by an injected
transport so no server is needed.

Only `.pptx` (OOXML) is accepted; legacy `.ppt` is rejected by the backend with
`UNSUPPORTED_LEGACY_FORMAT`.
