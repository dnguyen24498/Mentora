# Frontend

Material library (`.pptx` upload), the Teacher Studio review page, the Classroom
runtime page, the Learning page (slide + teaching canvas + automatic text-only
narration, which can also be set to start at a chosen time), an Admin area
(courses, classes, publications) and Settings, as real
pages of one Vite app. React + TypeScript + Tailwind, built with Vite.

## Pages and routing

| URL | Page | File |
| --- | --- | --- |
| `/` | Material library — courses, upload, extracted Content IR, classes | `src/pages/UploadPage.tsx` |
| `/studio/{artifactId}` | Teacher Studio — full-width slide review of one deck | `src/pages/StudioPage.tsx` |
| `/classroom/{classId}` | Classroom — authoritative runtime state of a session (V0-011) | `src/classroom/ClassroomPage.tsx` |
| `/learn/{artifactId}` | Learning — the slide, the teaching canvas and text-only narration, on demand or at a chosen time | `src/presentation/LearnPage.tsx` |
| `/admin/{section}` | Admin — overview, courses, classes, publications | `src/admin/AdminPage.tsx` |
| `/settings/{section}` | Settings — general, rendering, teaching, accessibility | `src/settings/SettingsPage.tsx` |
| anything else | The app's own not-found view | `src/App.tsx` |

`/admin` and `/settings` are their default sections (overview/general); an unknown
section is a 404 rather than an empty page.

The teacher review flow is a **page of its own**, not a panel on the upload page:
it is the large-screen slide surface, so it is opened directly (a new tab, a
second monitor, a bookmark), survives a deep link and a refresh, and sets its own
document title to the file name.

## Navigation between the pages

`src/components/SiteNav.tsx` is embedded in every page header, so Library,
Teacher Studio, Classroom, Learning, Admin and Settings are each reachable from
the others. The Studio and Learn links need a deck and the Classroom link needs a
class: the current page passes the id it holds, otherwise the last one opened is
remembered in `localStorage` (`src/institution.ts`, like the tenant and the
selected course). Before there is an id, the entry is a disabled label that says
why — never a link that goes nowhere. Admin and Settings are plain links, so they
are always available.

The library is the hub: selecting a deck offers **Open Teacher Studio** and
**Open learning page**, and the **Classes** panel (`GET /classes`) links each
scheduled class to its classroom (scheduling stays in the runtime API).

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

## Phones and large screens

The app is designed for a large screen (a classroom display, the Teacher Studio on
a second monitor) and is **usable on a phone** without becoming a second design:
every page is one mobile-first layout, so the large screen still gets the dense
layout it had.

`src/components/PageHeader.tsx` is the app bar the five full pages share — the
shared nav, the page's name, an optional qualifier (a filename, a class) and
identifier, the tenant field, and the page's own action or section tabs. The tenant
field is a **prop**, not state inside the header: the page keeps the single
`useInstitution()` hook, so a change in the bar flows to the page instead of into a
private copy. On a phone the bar stacks (nav → title → tenant field); from `lg` up
the pieces return to the one-row bar.

The rules live in `src/components/ui.tsx` as plain class-string tokens
(`TOUCH_TARGET`, `PAGE_PADDING`, `PANEL_PADDING`, `INPUT_CLASS`,
`INPUT_CHROME_CLASS`, `BUTTON_PRIMARY`/`BUTTON_SECONDARY`/`BUTTON_SMALL`,
`TAB_CLASS`), so "how this app looks on a phone" is decided in one place:

- Below `lg` (≥1024px) the UI assumes a finger: every control is at least **44px**
  tall, and above `lg` the original compact height returns. `lg` is the app's own
  big-screen breakpoint (every two-column page already switches there), and
  `SiteNav` **wraps** its six chips rather than hiding some behind a menu.
- A form control is **16px** below `lg`. This one is a bug rather than a taste:
  iOS Safari zooms the whole page when a focused control's text is smaller, and a
  phone in landscape and a tablet are both below `lg`.
- Definition-list rows (`Row`) stack label over value on a phone, a wide data
  table scrolls sideways inside its container, and a two-button action grid
  (`Extract` / `Open Teacher Studio`) stacks.
- **Every grid declares its own columns** (`grid-cols-*`) at the base breakpoint.
  This is the one that actually bit: a bare `grid` gets a single *implicit* track,
  and an implicit track is `auto` — floored at the content's min-content width. So
  one long unbreakable filename set the minimum width of the page, and the library
  measured 666px inside a 390px viewport. Tailwind's `grid-cols-1` is
  `minmax(0, 1fr)`, whose floor is 0, so the value ellipsises instead. A column
  declaration that only exists behind a variant (`md:grid-cols-2`) does *not*
  count. `src/responsive.test.ts` is a source scan for exactly this, because jsdom
  has no layout engine.
- The teaching canvas draws at the screen's **device pixel ratio**, so a stroke on
  a phone is sharp instead of an upscaled CSS-pixel bitmap. Strokes are stored in
  CSS pixels either way, so the scale only affects the paint.

Keyboard affordances (← / → hints) are hidden below `lg`, where there is no
keyboard; nothing is removed from the DOM, and no page gains or loses a control.

### Checking it

jsdom cannot measure layout, and the repo has no layout test runner, so the check
is a browser at a phone width. With the app running, load each route and assert
that no element extends past the viewport:

```js
document.documentElement.scrollWidth <= document.documentElement.clientWidth
```

Measured that way at 320/360/390/414/768/1280px, every route holds — including the
library with a deck selected, its stored details, the IR viewer expanded and the
raw JSON shown (the widest content the app has).

## Ports

| Service | Port |
| --- | --- |
| Frontend (Vite dev server) | **8000** |
| Backend API | **8001** |

Vite proxies `/courses`, `/artifacts`, `/classes`, `/renderer`, `/publications`,
`/course-versions`, `/health`, `/docs` and `/openapi.json` to the backend
(`MENTORA_BACKEND_ORIGIN`, default `http://127.0.0.1:8001`), so the browser only
ever talks to `:8000` — no CORS. A path that is *not* proxied but is not an asset
gets the SPA shell instead of an API response, which is why every API prefix the
client uses is listed here.

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

## Learning page (`/learn/{artifactId}`)

The learner-facing view of one deck, in `src/presentation/` — the module the spec
reserves for presentation work:

- **The slide**, loaded the way the Studio loads it (an object URL, because
  `<img src>` cannot send the `X-Institution-Id` header) and read from the
  package already built for the deck, so opening Learning never re-renders it.
- **The teaching canvas** (`TeachingCanvas.tsx`): a transparent annotation layer
  over the slide, with pen, highlighter and eraser, a colour and width, undo and
  clear. Strokes are kept per slide while the page is open. They are
  **client-local**: the ordered per-class event stream that would carry them to
  students is `DEC-DATA-003` (`OPEN`; the live path is V1-002), so nothing
  pretends to broadcast. A browser with no 2D canvas still shows the slide and
  says annotation is unavailable, instead of failing.
- **Slide navigation**: previous/next, a jump-to selector, and the ← / → arrow
  keys (ignored while focus is in a control).
- **The teaching script**: the slide's extracted text, its speaker notes, the
  pinned package's lesson-order script and, when the teacher has one, the newest
  draft revision for that section (`GET .../review-package/review-state`).
- **Automatic teaching (text only)**: **Play** narrates the deck. Each slide's
  narration is the deck's *authored* text — the teacher's newest draft revision,
  else the package's lesson script, else the speaker notes, else the slide text —
  and the panel names which one it used. The passage appears as a caption
  (toggleable), is appended to a running transcript, and after its dwell the page
  moves to the next slide by itself; **Pause** holds, **Stop** rewinds and clears
  the transcript, and the last slide ends the narration. The pace is the
  words-per-minute setting (Settings → Teaching): dwell scales with the word count
  and is clamped to 2.5–30 s, so a long passage gets longer and a blank slide
  still gets a beat.
  - **No audio and no model.** The voice capability's provider decision
    (`DEC-TECH-007`) is `OPEN`, so this runs the speech domain's text fallback
    path only; and no LLM provider exists in the codebase (the ledger does not
    name one), so the teaching text is the author's, not generated.
  - **Client-local.** The narration is not an authoritative event: the ordered
    per-class timeline with checkpoints, resume and bridge phrases
    (`DEC-RUNTIME-005`, `DEC-DATA-003`) is V0-013/V1-002. Nothing is written to
    the server.
  - **Teaching at a time.** Give the panel a datetime and the narration begins by
    itself when the page's own clock reaches it (Pause, Stop, caption and transcript
    then behave exactly as if Play had been pressed). It is client-local for the same
    reason: the tab has to stay open, because a server that waited would be the
    durable scheduler `DEC-TECH-003` (`OPEN`) — and the panel says so. The pure
    arithmetic (reading an instant, whether it is due, a countdown, the
    `datetime-local` round trip) lives in `src/time.ts` and is unit-tested.

## Admin area (`/admin/{section}`)

`src/admin/` manages the V0 entities **through the existing API only**. That
constraint is deliberate and is stated on the pages: the API has no generic update
or delete, and that is a property of the domain rather than a gap — content is
immutable, a draft is append-only and a publication is never deleted
(`DEC-CONTENT-005`), so a correction is a **new version**.

- **Overview** — what the tenant holds (courses, classes, running classes) and
  links to the section that can act on it. It never mutates anything itself.
- **Courses & materials** — create a course, select one, upload a `.pptx` into it,
  and act on a deck: **Compile** (in the render mode chosen in Settings),
  **Details** (the stored metadata), **Studio** and **Learn**. A deduplicated
  upload (identical bytes) is reported as a reuse rather than a second copy. No
  rename/delete: an artifact is immutable.
- **Classes** — schedule a class onto a course (optionally pinned to a version and
  optionally given a **datetime**), then select it to see its state, its session and
  its **pinned runtime tuple**, **Start** it (the tuple is resolved once and never
  looked up as "latest" again), and manage **enrolments** (enrol is idempotent). A
  replayed start is reported as such.
  - The datetime is read on the teacher's own clock (`src/time.ts`, the
    `datetime-local` value ↔ instant conversion) and shown with a live countdown, so
    a class that is due says so.
  - **Auto-start when due** (off by default) starts a due class **while this page is
    open**, through the same idempotent `POST /classes/{id}/start` the Start button
    uses; each outcome is reported per class, a refusal included, so a class whose
    course was never published says `CLASS_NOT_READY`/`VERSION_NOT_PUBLISHED` instead
    of appearing to have started.
  - This is deliberately **not** a server scheduler: the API records `scheduled_for`
    and never enforces it, because an automatic start would be a durable workflow and
    `DEC-TECH-003` is `OPEN`. Nothing runs with the page closed, and the view says so.
- **Publications** — publish an approved version and read what has been sealed.
  `Publish` is idempotent on the content (`created: false` on a replay) and reports
  every refusal by its stable `issue_code`; `Verify integrity` re-checks the pinned
  package against the digest recorded at seal time and reports
  `VERIFIED`/`MISMATCH`/`MISSING` without changing anything. Superseded
  publications stay listed — they are linked, never deleted.

## Settings (`/settings/{section}`)

`src/settings/` holds **client preferences**, because there is no settings API: the
server's own configuration is its environment (the home region,
`MENTORA_HOME_REGION`) and the per-request render mode. Preferences live in one
module (`src/settings/store.ts`, persisted as `mentora.settings` and kept in step
across tabs through the `storage` event, exactly like the tenant). They are
conveniences: nothing in Settings changes what the server stores, seals or
publishes.

- **General** — the institution (a real input, sent as `X-Institution-Id` on every
  request), plus read-only server facts read live from `GET /health` and
  `GET /renderer` (renderer identity, default mode, data region) and the home
  region, which is server configuration and is offered as a fact, not as a field.
  **Restore defaults** resets the stored preferences.
- **Rendering** — the render mode (`faithful`/`themed`) used for new renders: the
  Admin **Compile** action and the live preview on the page itself
  (`GET /artifacts/{id}/renders/{order}?mode=`, using the last deck opened). It
  cannot change a **packaged** render — those are pinned at build time — and the
  page says so. It also reports the renderer's declared support and circuit-breaker
  state for the selected mode, and notes that no renderer technology is accepted
  (`DEC-TECH-005` is `OPEN`).
- **Teaching** — the narration pace (words per minute), whether a deck starts
  narrating when it is opened, whether the caption line is shown, and whether a due
  **scheduled class** is started when its time arrives (which, like the narration,
  only happens while the page that waits is open — the server has no scheduler),
  with an explicit statement of what runs: authored text, no model, no audio,
  nothing written to the server.
- **Accessibility** — reduced motion and high contrast. These are the **classroom's
  own** persisted preferences, edited through the classroom store
  (`readClassroomPreferences`/`updateClassroomPreferences`) rather than kept a
  second time, so the two can never drift.

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
and the `Link`/`navigate` behaviour. `src/components/SiteNav.test.tsx` covers the
shared navigation (every page from every page, the disabled entries before an id
is known, `aria-current`). `src/presentation/LearnPage.test.tsx` covers the
learning page: stored vs built package, slide navigation by button, selector and
arrow keys, the teaching script, the canvas toolbar including its no-2D-canvas
degradation, and the automatic teaching (play/pause/stop, the transcript, the
caption, auto-advance and the end of the deck under fake timers, autoplay,
captions off, the pace setting, and the draft-revision precedence with a
graceful fallback when the overlay cannot be read, plus teaching at a chosen time:
a time already reached starts at once, a time in the future waits with a countdown
and can be cleared, and the clock reaching it begins the narration — with the
client-local boundary stated on the page).
`src/presentation/narration.test.ts` is the pure narration suite (word counting,
dwell clamping and scaling, the source precedence, and the draft-revision rule).
`src/time.test.ts` is the pure scheduled-instant suite (parsing an instant and
refusing a non-instant, whether a time is due including the absent case, countdowns
in both directions, the `datetime-local` round trip in the reader's own timezone,
and the one-line schedule description).
`src/settings/store.test.ts` covers the preference store (defaults, round-trip,
unreadable storage, clamping an out-of-range pace, ignoring an unknown mode).
`src/components/PageHeader.test.tsx` covers the shared app bar's contract (one
`h1` per page, the current nav entry, the tenant field reporting to the page rather
than holding its own copy, and the page's own action/second row), and
`src/presentation/TeachingCanvas.test.tsx` covers the canvas's device-scale
contract (the bitmap is the surface times the device pixel ratio, so a phone gets
a sharp line; it stays 1:1 where the scale is 1) and its no-2D-context
degradation.
`src/admin/AdminPage.test.tsx` covers each admin section against a mocked API
(course creation, material listing/upload/compile in the Settings mode, the
absence of any delete/rename, scheduling with and without a datetime, starting,
enrolling, publishing and verifying, and the scheduled start: a due class started
while the page is open, a due class left alone with auto-start off, and a refusal
reported per class rather than retried), and `src/settings/SettingsPage.test.tsx`
covers each settings section (the server facts it can only report, restoring
defaults, persisting the mode, the pacing and the auto-start, and editing the
classroom's own accessibility preferences). Test deps
are **dev-only**; the production build and its dependencies are unchanged.

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
