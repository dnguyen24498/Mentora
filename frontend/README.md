# Frontend

Material library (`.pptx` upload), the Teacher Studio review page, the Classroom
hub and one running class (the teacher's auto-playing presentation stage, and the
student's view-only follower), the legacy Learning page (slide + teaching canvas +
automatic text-only narration, kept for direct links), an Admin area (accounts,
courses, classes, publications), Settings, and — V0-021/V0-022 — sign-in for the
three account types (administrator, teacher, student) and a class join page, as
real pages of one Vite app. React + TypeScript + Tailwind, built with Vite.

## Pages and routing

| URL | Page | File |
| --- | --- | --- |
| `/` | Material library — courses, upload, extracted Content IR, classes | `src/pages/UploadPage.tsx` |
| `/studio/{artifactId}` | Teacher Studio — full-width slide review of one deck | `src/pages/StudioPage.tsx` |
| `/classroom` | Classroom hub — every class the person may see; a teacher starts one, a student joins a running one (V0-026) | `src/classroom/ClassroomHomePage.tsx` |
| `/classroom/{classId}` | One class — the teacher's auto-playing presentation stage, or the student's view-only follower (V0-025/V0-026) | `src/classroom/ClassroomPage.tsx`, `src/student/StudentClassPage.tsx` |
| `/learn/{artifactId}` | Learning (legacy) — the slide, the teaching canvas and text-only narration, on demand or at a chosen time; kept for direct links, no longer in the nav | `src/presentation/LearnPage.tsx` |
| `/admin/{section}` | Admin — overview, accounts, courses, classes, publications | `src/admin/AdminPage.tsx` |
| `/settings/{section}` | Settings — general, rendering, teaching, accessibility, security | `src/settings/SettingsPage.tsx` |
| `/login` | Sign in — institution, address, **password**; the only public route (V0-023) | `src/auth/LoginPage.tsx` |
| `/join/{classId}` | Join a class — who is asking, then the caller's own join credential | `src/student/JoinClassPage.tsx` |
| `/student` | Alias of the Classroom hub (kept for old links) | `src/classroom/ClassroomHomePage.tsx` |
| `/student/{classId}` | Alias of the student's view of a running class — follows the teacher's slide, with no slide navigation | `src/student/StudentClassPage.tsx` |
| anything else | The app's own not-found view | `src/App.tsx` |

`/admin` and `/settings` are their default sections (overview/general); an unknown
section is a 404 rather than an empty page.

The teacher review flow is a **page of its own**, not a panel on the upload page:
it is the large-screen slide surface, so it is opened directly (a new tab, a
second monitor, a bookmark), survives a deep link and a refresh, and sets its own
document title to the file name.

## Navigation between the pages

`src/components/SiteNav.tsx` is embedded in every page header, so Library,
Teacher Studio, the Classroom hub, Admin and Settings are each reachable from
the others. The Studio link needs a deck: the current page passes the id it
holds, otherwise the last one opened is remembered in `localStorage`
(`src/institution.ts`, like the tenant and the selected course). Before there is
an id, it still links to the Library, where the deck is chosen, rather than being
a disabled label. The Classroom link is the **hub** (`/classroom`): it needs no
class id, because the hub lists the classes the person may see and the teacher
starts one there. The library also remembers the newest deck of the selected
course on a first visit, so Studio is usable without opening one first. Admin and
Settings are plain links, so they are always available.

The legacy Learning page (`/learn/{artifactId}`) is no longer in the nav — the
classroom presents the pinned slides, auto-playing them from the hub — but the
route is kept so a link already shared still opens something.

With identities (V0-021) the nav also answers "who am I": it shows the signed-in
principal and **Sign out**, or a **Sign in** link when no session exists. Since
V0-023 there is no "development mode" chip: the tenant shortcut is off by default and
every page is behind the sign-in, so a session is the only state the nav knows.
V0-022 chooses the entries by **capability** rather
than by role name, so a principal is offered exactly the pages the server would
allow: an **institution administrator** (who authors nothing and attends nothing)
sees Library, Classroom, Admin and Settings; a **teacher** sees all of them; a
**student** sees **Classroom** (the same hub, scoped by the server to their
roster) instead — see "Identities and the student pages" below.

The library is the hub for material: selecting a deck offers **Open Teacher
Studio**, and the **Classes** panel (`GET /classes`) links each scheduled class
to the classroom hub (scheduling stays in the runtime API).

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

`src/components/PageHeader.tsx` is the one app bar **every** full page shares — the
shared nav, the page's name, an optional qualifier (a filename, a class) and
identifier, the tenant field, and the page's own action or section tabs. The
library used to centre its own header in a narrower column, so moving to it shifted
the whole nav; the bar now covers the full width on every page and the nav starts
at the same place everywhere (the library's description is page content, below the
bar, not a second header row). The tenant field is a **prop**, not state inside the
header: the page keeps the single `useInstitution()` hook, so a change in the bar
flows to the page instead of into a private copy. On a phone the bar stacks (nav →
title → tenant field); from `lg` up the pieces return to the one-row bar.

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
  has no layout engine. `src/appbar.test.ts` does the same for the **one app bar**
  rule: only `PageHeader` may mount `SiteNav`, and only the public sign-in page may
  grow its own `<header>`, because a page that bypasses the bar shifts the whole
  navigation.
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
`/course-versions`, `/auth`, `/health`, `/docs` and `/openapi.json` to the backend
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

- Takes an **Institution ID** from the shared bar (sent as the `X-Institution-Id`
  tenant header, persisted in `localStorage`).
- Lists the tenant's courses (`GET /courses`) and can create one (`POST /courses`).
- Lists the selected course's already-uploaded presentations
  (`GET /courses/{id}/materials`) with size, version and job status, and lets you
  **select one** to inspect it.
- Uploads or drag-and-drops a `.pptx` (`POST /courses/{id}/materials`). After the
  upload it calls `POST /artifacts/{id}/auto-publish`, so an ordinary deck is
  **published automatically under the signed-in teacher** and is immediately
  usable in a class. The server still applies the review policy: a package marked
  `REVIEW_REQUIRED` comes back `published: false` and the page says to open
  Teacher Studio, and a blocking fidelity failure is reported as an error. No
  Admin → Publications step is needed for the auto-allowed case.
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
or delete *of content*, and that is a property of the domain rather than a gap —
content is immutable, a draft is append-only and a publication is never deleted
(`DEC-CONTENT-005`), so a correction is a **new version**. An **account** is the
exception that proves the rule — a name, a role and an enabled state are genuinely
mutable — so the directory has a real rename, role switch, disable/enable and
removal (V0-022). The section list itself is filtered by **capability**, so the
tabs a principal sees are the ones the server would allow; a section reached by URL
that the role does not hold renders an honest **Not available for this account**
card with links to the ones it does hold, rather than a page whose every request
would `403`.

- **Overview** — what the tenant holds (courses, classes, running classes) and
  links to the section that can act on it. It never mutates anything itself.
- **Accounts** (V0-022, V0-023) — the institution's teacher and student directory:
  create an account, rename it, switch its role, disable/enable it and delete it.
  **The administrator chooses the password** on creation and can **reset** it later;
  the password is sent in the request **body** (never a URL) and is never echoed
  back, and a reset reports the live sessions it revoked. Two refusals are turned
  into the remedy they point at: an address that already belongs to the other role
  says to change *that* account's role rather than split one person in two, and a
  deletion refused with `ACCOUNT_IN_USE` says to **Disable** instead (a removal
  would orphan the roster). It never offers to create an administrator — the API
  refuses that (`ROLE_NOT_MANAGEABLE`), and the page explains that the first
  administrator comes from the sign-in page's bootstrap. The section is visible only
  to a principal holding `account:write`.
- **Courses & materials** — create a course, select one, upload a `.pptx` into it,
  and act on a deck: **Compile** (in the render mode chosen in Settings),
  **Details** (the stored metadata), **Studio** and **Learn**. A deduplicated
  upload (identical bytes) is reported as a reuse rather than a second copy. No
  rename/delete: an artifact is immutable.
- **Classes** — schedule a class onto a course (optionally pinned to a version and
  optionally given a **datetime**), then select it to see its state, its session and
  its **pinned runtime tuple**, **Start** it (the tuple is resolved once and never
  looked up as "latest" again), and manage **enrolments**. V0-022 replaced the
  invite-by-address field with a **student picker** (`GET /accounts?role=student`,
  the one directory read a teacher holds): assigning chooses a student who already
  exists, each roster row has a **Remove** action, and the panel says that creating
  an account is the administrator's job — enrolment never creates one. A replayed
  start is reported as such.
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
- **Security** (V0-023) — change **your own password**: the current one is verified
  exactly as a sign-in is (a wrong one is refused and does not sign you out), and a
  successful change revokes the account's **other** live sessions while keeping this
  one. It says plainly that the credential mechanism is not a decided technology.
  Resetting *someone else's* password is `Admin → Accounts`.

## Identities, the directory and the student pages (V0-021, V0-022)

Sign-in is a page (`/login`) rather than a browser prompt, because the app has to
be honest about what it is: **no credential mechanism is a decided technology** in
the spec (the canonical requirement is institutional federation; every provider
decision is `OPEN`, and the identity ADR `FND-002` is still `TODO`), so the form
says so and the adapter behind it is a labelled development stand-in —
`GET /auth/me` reports `authenticator.kind: "DEVELOPMENT_MOCK"` and the page
renders that word rather than implying federation.

**Three account types sign in through the one form** (V0-021/V0-022) — an institution
administrator, a teacher and a student — because who you are is the account's role,
not a choice on the page. The same page carries the **first-administrator** panel,
since a fresh installation has no accounts and therefore nobody who could sign in to
create one: it posts to `POST /auth/bootstrap-admin` with the password the operator
chooses and **fills the address and password into the sign-in form** so the next step
is one click (no secret is returned to display); a refusal is
named by cause — the institution already has an administrator (`TENANT_ALREADY_PROVISIONED`,
"sign in instead"), or a hardened deployment provisions them through the identity
provider (`BOOTSTRAP_DISABLED`).

**The whole app is behind the sign-in (V0-023).** `App.tsx` treats `/login` as the
only public route: any other route with no session renders a redirect to
`/login?next=<requested path>` (a `replace`, so the guarded path does not linger in
the history), and a successful sign-in returns there. A `401` that means the server
no longer accepts the session (expired, revoked, unknown, disabled) clears it in
`api/client.ts`, so the guard re-applies with a truthful state. There is no
"development mode" affordance: the tenant shortcut is off by default.

- **`src/auth/session.ts`** holds the session — the raw token for the API client,
  the principal (tenant, role, scopes), the capability that issued it and its
  expiry — in `localStorage`, shared across tabs like the tenant (a `storage`
  listener keeps two tabs in step). An **expired session is not a session**: it is
  dropped on read as well as on write, because the server would refuse it anyway
  and a page that looked signed in while every request 401ed would be worse.
  `hasScope()` is **advisory** — it decides what the UI offers, never what is
  allowed (the server re-derives scopes from the account's current role on every
  request, so a stale client can only ever show a button that fails). V0-022 adds
  the third role, the two directory capabilities (`account:read`, `account:write`)
  and `isAdministrator` (read from `account:write`, never from the role name).
  **V0-023: no session is no capabilities** — `hasScope(null, …)` is `false` for every
  scope, because a sign-in is required and the shortcut is off by default.
- **The nav is role-aware, chosen by capability.** A student sees **Classroom**
  (the same `/classroom` hub, which the server scopes to their roster) instead of
  Studio/Admin; an institution administrator sees Library/Classroom/Admin/Settings
  because the authoring surfaces would only answer `403`. This is courtesy, not
  access control: the server refuses a student's teacher verbs with
  `403 INSUFFICIENT_SCOPE` regardless. With no session the nav offers only
  **Sign in**, because there is nothing a caller without a session may do.
- **`src/auth/StudentNotice.tsx`** is where a student lands if they open a
  teacher's page: a real landing — the class they were last in, a field to open a
  class by the id in their join link, and Sign out — rather than a page whose every
  request would answer 403. (A class id is not a secret; *enrolment* is what
  authorizes a join, and the server checks it on every join.)
- **`src/classroom/ClassroomHomePage.tsx`** (`/classroom`) is the one classroom
  hub for everyone (V0-026). It lists whatever `GET /classes` returns: a teacher
  (and an institution administrator) sees the tenant's schedule, a student sees
  only the classes a teacher enrolled them in, because the server scopes the list
  by role. A teacher **Start class** button starts the real V0-009 session and
  opens `/classroom/{id}?autoplay=1`; a running class becomes **Join class** for a
  student and **Open classroom** for a teacher. A scheduled student row says it is
  waiting and the page re-reads the list on a 5 s timer while any class is
  scheduled, so it becomes joinable when the teacher starts without a hidden
  refresh. `/student` is kept as an alias of this hub.
- **`src/student/JoinClassPage.tsx`** (`/join/{classId}`) establishes *who is
  asking* before anything else. Signed out, the route guard has already sent the
  browser to sign in, so the page's signed-out branch is only a defensive fallback.
  Signed in, it shows the class and asks the server for the caller's **own** join
  credential (`POST /classes/{id}/bootstrap-token`, no body), reporting a refusal
  by its precise cause — `NOT_ENROLLED`, `CLASS_NOT_READY`/`NOT_STARTED`,
  `NOT_FOUND` — rather than one generic failure. The join button is **disabled
  until the class is `ACTIVE`** and the page says only the teacher can start it;
  while the class is scheduled it re-reads it on the same 5 s timer, so the button
  enables the moment the teacher starts. The server refusal is still the rule
  (a direct call before the start is `409 NOT_STARTED`), not a UI convention.
- **`src/student/StudentClassPage.tsx`** (`/student/{classId}`) is the
  **fullscreen viewer**, built for the phone a student actually holds: the slide
  fills the viewport with a real **Fullscreen** button as well (a phone browser
  keeps its own chrome), but there is **no slide navigation** — no Previous/Next,
  no picker and no arrow keys. The teacher drives the class; this page reads the
  same authoritative `GET /classes/{id}/snapshot` and moves to the scene its
  lesson position names (V0-025), and the current slide is spoken by the teacher's
  live relayed voice. It waits for the teacher to start and joins by itself. When
  the teacher ends the class it shows a locked **Ended** screen with no slide or
  text — the server refuses a student's snapshot/scene reads with `CLASS_ENDED`
  (V0-027) — and it keeps re-reading the class metadata, so a teacher's **Reopen
  class** joins the new actor epoch by itself. Three limits are stated
  rather than hidden: the update is a **short poll** (about every 1.5 s), not the
  ordered per-class stream (`DEC-DATA-003` is `OPEN`, live path V1-002); the
  **voice is the teacher's live generation relayed over HTTP** (V1-005 bridge,
  `GET /classes/{id}/narration`) rather than a per-student synthesis or a
  transcript — the page shows the provider (the deterministic mock or the opt-in
  OmniVoice prototype) and an **Enable sound** button when the browser blocks
  autoplay. This is explicitly *not* the SFU media plane (`DEC-TECH-004` is
  `OPEN`): the relay answers `204` while there is no current generation, copies
  each WAV chunk the teacher's tab produced, and ends at that generation's verdict.
  The current slide is the unit of replay: a student who joins mid-slide hears it
  from the slide's start (the fast mock would otherwise finish synthesis before the
  next attach and leave them in silence), and the teacher's next slide supersedes
  it. The page sends `after_generation` so waiting for the next slide does not
  replay the one it just heard, and `expected_scene_id` from the snapshot so the
  audio cannot run under a different slide's image.
  The slide's own text stays available only behind the collapsed accessibility
  disclosure; and every scene comes from the package the session
  pinned at start (`GET /classes/{id}/scenes[/{order}]`, `DEC-CONTENT-005`), so a
  correction published mid-lesson cannot change the slide under a student. A
  scene whose file does not match the manifest digest
  (`SCENE_CHECKSUM_MISMATCH`) is refused by the server and reported, never drawn;
  the student's class/snapshot/scene reads are also checked against their roster.

Teacher-side, the Admin area's **classes** section (`src/admin/ClassesAdmin.tsx`)
uses the real roster: V0-022 changed how a student gets onto it — the **picker
chooses from the students who exist** (`GET /accounts?role=student`, the only
directory read a teacher holds), each roster row has a **Remove** action
(`DELETE /classes/{id}/enrollments/{studentId}`, which takes them off the class and
leaves the account and its sign-in untouched), and the panel says that creating an
account is the institution administrator's job in **Admin → Accounts**. Enrolment
never creates an account, so there is no address to type and no implicit signup
behind one; the class detail still offers the **student join link** to share, and
V0-024 selects a class as soon as one exists (falling back to the newest when a
remembered id is not this tenant's), so the Start / assign / join-link panel is on
screen instead of an empty "Select a class". Starting is the teacher's verb and
the only path to a joinable class; the classroom page links a teacher to this
panel for the class they are viewing.

## Classroom hub and automatic play (V0-026)

`/classroom` is the single classroom page. It lists the classes the signed-in
person may see (the server scopes `GET /classes` by role) and is the only place a
class is started: a teacher presses **Start class**, which calls the real
`POST /classes/{id}/start` and opens `/classroom/{id}?autoplay=1`. There is no
separate "learning page" destination any more; `/learn/{artifactId}` is kept for
direct links only and is not in the nav.

A class whose session is `COMPLETED` reads **Ended** (the domain state is kept;
only the label changes). Its lesson is locked for students: the row still shows
the class and the reason, but offers no Join or lesson link, and the student
viewer draws no slide or text. A teacher sees **Reopen class**, which calls
`POST /classes/{id}/reopen` and opens the same class at `?autoplay=1`; the same
roster and the same pinned package are kept, the lesson returns to its first
slide, and a **new actor epoch** is started, so every pre-end join credential is
stale (V0-027, `DEC-CONTENT-005`, `DEC-RUNTIME-007`). Ending is an explicit
teacher action — auto-play reaching the last slide stops, it does not end the
class — because a durable scheduler is `DEC-TECH-003` (`OPEN`).

On that URL the teacher's stage (`src/classroom/TeacherStage.tsx`) advances the
**pinned** slides by itself. The dwell for each slide is
`src/classroom/playbackTiming.ts::dwellForScene` — the slide's text and notes
counted as words at the pace set in Settings (`teachingWpm`, 80–260 wpm), with a
5 s floor and a 30 s ceiling — and it stops when the last slide is reached rather
than looping. A **Pause / Play** button is offered, and the slide picker still
works so the teacher can jump. This is **client-local**: the teacher's tab is the
clock, closing it stops the slides, and no scheduler or worker is implied
(`DEC-TECH-003` is `OPEN`). Students follow the same class at
`/classroom/{id}` — the app serves them `StudentClassPage` — and move only when
the authoritative snapshot's current lesson scene changes (the ~1.5 s poll;
`DEC-DATA-003` is `OPEN`, V1-002). A student has no slide controls.

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
  For a teacher the runtime scene buttons are hidden, because the presentation
  stage above owns slide movement (V0-025).
- **`TeacherStage.tsx`** (V0-025) is the teacher's presentation surface: it loads
  the pinned scene list, shows the slide the session is on, and moves the class
  with **Previous slide**, **Next slide** and a slide picker. Each move is
  `POST /classes/{id}/navigate` with the `state_version` the page is showing; the
  response's durable snapshot is applied to the store, so the stage and the shell
  agree immediately. A stale refusal (`STALE_STATE_VERSION`) or an ended class is
  shown and triggers a resynchronise rather than silently presenting the wrong
  slide. This is an HTTP command over the existing aggregate, not the V1-002
  ordered stream.
- **Transport** (`transport.ts`) is an interface. The ordered per-class
  command/event mechanism is `DEC-DATA-003` and its technology is `OPEN`, so the
  shipped transport reads the snapshot only and advertises
  `liveEvents:false`/`commands:false`; the page says so instead of faking a
  stream. The teacher's slide command and the student's short snapshot poll are
  the V0 stopgap; the live stream and runtime command path are V1-002. Tests and a
  local demo drive events through the injected `ClassroomTransport`.
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
shared navigation (every page from every page, the chooser an entry falls back to
before an id is known, `aria-current`). `src/classroom/ClassroomHomePage.test.tsx`
covers the hub (a teacher starting a class lands on `?autoplay=1`, a student only
sees the running class as joinable, an empty roster is explained, a start refusal
is reported on the row); `src/classroom/TeacherStage.test.tsx` covers the
auto-play clock (advance after the dwell, pause, stop at the last slide, and no
movement without the flag) and `src/classroom/playbackTiming.test.ts` the pacing
rule (words at the teacher's speed, the 5 s floor, the 30 s cap, notes counted).
`src/presentation/LearnPage.test.tsx` covers the
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
defaults, persisting the mode, the pacing and the auto-start, editing the
classroom's own accessibility preferences, and the **Security** change-password
form: success with the revoked-session count, a local mismatch refusal, and a wrong
current password that leaves the session standing). Test deps
are **dev-only**; the production build and its dependencies are unchanged.

`src/classroom/state/reducer.test.ts` is the pure-reducer acceptance suite
(contiguous apply, duplicate/stale ignored, gap reported and not applied,
superseded epoch discarded, unknown event advances the cursor); 
`src/classroom/state/session.test.ts` covers connect, gap → resync → recover,
bounded-retry disconnect and the telemetry contract; 
`src/classroom/ClassroomPage.test.tsx` is the component-level end-to-end
(refresh restores scene/state, duplicate ignored, gap freezes controls and
recovers, accessibility smoke), with the event stream driven by an injected
transport so no server is needed. For V0-025, `src/classroom/TeacherStage.test.tsx`
covers the teacher's slide stage (the pinned slide, next/picker commands fenced by
`state_version`, a stale refusal triggering resync, no slides before start, the
last slide after the end), with V0-027 adding **End class** (confirmed, applies
the completed snapshot) and **Reopen class** (applies the new first-slide
snapshot). `src/classroom/ClassroomPage.teacher.test.tsx` proves the page exposes
it only to a teacher and applies the returned snapshot, and
`src/classroom/scenePosition.test.ts` covers the snapshot scene-id/section-index
mapping. `src/classroom/ClassroomHomePage.test.tsx` covers the hub's ended row
(teacher Reopen, student locked with no lesson link). `src/student/StudentClassPage.test.tsx`
covers the student viewer (opens on the teacher's slide, no buttons/picker/arrow
keys, follows a snapshot change on the poll, waits for the start and joins by
itself, locks an ended class instead of drawing its last slide, joins the same
class after a reopen, and refuses to read an unassigned class).

For V0-021, `src/auth/session.test.tsx` covers the session store (write/read,
expiry dropped on read, cross-tab updates, scope helpers, the development
shortcut never counted as signed in), `src/auth/LoginPage.test.tsx` covers the
sign-in page (success stores the session and reports the issuer, a refusal is
shown without navigating, the mock is named), and
`src/student/JoinClassPage.test.tsx` covers the join page's refusals and its
signed-out prompt. `src/components/SiteNav.test.tsx` and `src/App.test.tsx` add the
identity cases: the role-aware nav, the student landing, and the student
route guard. V0-023 adds the guard to `App.test.tsx` (an unauthenticated browser is
sent to `/login` with the requested page remembered, `/login` is public, and nothing
opens without a session), and no suite expects a "Development mode" state any more.

For V0-022, those suites grew a third role: `LoginPage.test.tsx` covers the
first-administrator bootstrap (creating it with a password fills it into the sign-in
form, "already provisioned" reads as "sign in instead", a hardened deployment says the
provider owns the account, and the panel disappears once a session exists);
`AdminPage.test.tsx` covers the **Accounts** directory (creating a teacher with the
password the administrator chooses, resetting one and reporting the revoked sessions,
a refused removal explained with the
`ACCOUNT_IN_USE` remedy, disabling with the revoked-session count, and no
administrator-creation option) **and the capability filter** (an administrator sees
Accounts and not the authoring sections, a teacher the reverse, and a section the
role does not hold renders **Not available for this account**), plus the classes
**picker/unassign** path; and `SiteNav.test.tsx` checks that an administrator is
offered the library and the directory and not the authoring surfaces. Note the
test environment has **no jest-dom**, so assertions use
the DOM directly (`button.disabled`, `getAttribute('disabled')`).

Only `.pptx` (OOXML) is accepted; legacy `.ppt` is rejected by the backend with
`UNSUPPORTED_LEGACY_FORMAT`.
