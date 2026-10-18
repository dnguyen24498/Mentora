# Frontend Classroom and Teacher Studio

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define authoritative client state, UX, reconnect, and review interfaces.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Separate snapshot/event reducer, media state, ephemeral UI, device permissions, and accessibility preferences. Apply contiguous events for current epoch; duplicates/stale ignored; gaps require resync.

Classroom displays content, captions, transcript, teacher state, queue, floor countdown, mic indicator, Finish, quiz, and recovery. Teacher Studio reviews fidelity, notes, reveals, semantics, citations, lessons, policy, voice, and publication diff.

## Implemented classroom client

The classroom client is implemented in `frontend/src/classroom/`. It is a **projection**, never a source of truth: the Classroom Actor owns authoritative state, and the client holds a derived view rebuilt from the authoritative snapshot (`GET /classes/{id}/snapshot`, the durable `runtime-snapshot@1` document) plus contiguous ordered events. The state is split into separate slices (`frontend/src/classroom/state/`): the **event reducer** (`reducer.ts` — the only slice derived from the actor's stream), the raw **snapshot**, **media** state and **ephemeral UI / accessibility preferences** in `store.ts`. The reducer is pure: it applies an event only when it is **contiguous for the current epoch** (`sequence === lastSequence + 1`), **ignores duplicates and stale events** (`sequence <= lastSequence` — `DEC-RUNTIME-003`), **discards an effect from a superseded epoch** (`DEC-RUNTIME-007`), and reports a **sequence gap** rather than applying out of order. A gap, a stale epoch or a failed load freezes the client (`status !== 'live'`), disables the command controls and requests a resync; the session (`session.ts`) answers a resync by re-reading the authoritative snapshot with bounded retry (`DEC-RELIABILITY-001`) and resetting the event cursor — it never guesses at the missing events. A refresh is a fresh mount, so it restores scene and state from the snapshot (`DEC-RUNTIME-004`, `DEC-DATA-004`). The transport is an interface with one V0 implementation (`transport.ts`) that reads the snapshot only: the ordered per-class event mechanism is `DEC-DATA-003` and its technology is `OPEN`, so the shell reports `liveEvents:false`/`commands:false` and says so instead of faking a stream (that live path is V1-002). Group student audio stays inactive (`DEC-TURN-001`). The client emits structured telemetry — identities, counts and outcomes only, never scene text, transcript or audio (`telemetry.ts`).

## Implemented pages and navigation

The app has four routed pages (`frontend/src/router.tsx`, dependency-free): the
material library (`/`), the Teacher Studio (`/studio/{artifactId}`), the
classroom (`/classroom/{classId}`) and the learning page (`/learn/{artifactId}`),
plus two **sectioned areas**: the Admin area (`/admin/{section}` —
overview, courses, classes, publications) and Settings (`/settings/{section}` —
general, rendering, teaching, accessibility). V0-021 adds three: **sign in**
(`/login`), a class's **student join page** (`/join/{classId}`) and the student's
**own fullscreen view** of a class (`/student/{classId}`). A shared navigation
(`frontend/src/components/SiteNav.tsx`) is embedded in every page header, so each
page is reachable from every other. The deck/class-scoped entries use the id the
page holds or the last one opened — remembered in `localStorage` alongside the
tenant — and are disabled with an explanation before an id exists. The library is
the hub: it lists the tenant's classes (`GET /classes`) and links each to its
classroom, and offers both the Studio and the learning page for a selected deck.

## Implemented identities and the student surface (V0-021)

`frontend/src/auth/` holds the identity half. `session.ts` is the signed-in
session (`localStorage`, shared across tabs like the tenant): the raw token for
the API client, the principal, the capability that issued it, and a memoised read
for `useSyncExternalStore`. Two things are deliberate:

- an **expired session is not a session** — the same rule on write as on read,
  because the server would refuse it anyway and a page that looked signed in while
  every request 401ed would be worse than one that asks again;
- `hasScope()` is **advisory**: it decides what the UI offers, never what is
  allowed. The server re-derives scopes from the account's current role on every
  request, so a stale client can only ever show a button that fails.

`mode.ts` answers "which mode is this browser in?". It cannot be read from local
state, because the **development tenant shortcut has no session at all**, so it
asks `GET /auth/me` — the endpoint reports `authenticated: false` for the
shortcut and `401 SESSION_REQUIRED` when the deployment has switched it off. The
answer is cached for the page and shown as "Development mode"; the app never
presents the shortcut as a sign-in, nor as signed out while it is in fact acting
as a teacher. `LoginPage.tsx` is the credential exchange — institution, address,
opaque **sign-in code** — and says in the page that no credential mechanism is a
decided technology and that the adapter behind the form is a labelled development
mock. `fetchObjectUrl` and every other request carry the session token through
`api/client.ts::send`.

A student who opens a teacher's page is *not* shown a page whose every request
would answer `403`: `StudentNotice.tsx` is a real landing, offering the remembered
class, the class id from their join link, and Sign out. That is a courtesy, not
the control — the server enforces the role on every request.

`frontend/src/student/` is the student's surface, built for the device a student
actually holds. `JoinClassPage.tsx` (`/join/{classId}`) establishes *who is
asking* before anything else: signed out it asks for a sign-in and says the
development shortcut cannot join (it is a teacher, and joining is the student's
own capability); signed in it shows the class and asks the
server for the caller's own join credential, reporting a refusal by its precise
cause (`NOT_ENROLLED`, `CLASS_NOT_READY`/`NOT_STARTED`, `NOT_FOUND`).
`StudentClassPage.tsx` (`/student/{classId}`) is the **fullscreen** view: the
slide fills the viewport (a real Fullscreen button as well as the layout, because
a phone browser still shows its own chrome), one tap or one arrow key moves a
slide, the controls keep their ≥44px tap area, and the current slide's own text
and notes are shown as the narration. Two properties it does not overstate: the
slide shown is the one *this student* is on, because the ordered per-class event
stream that would carry "the teacher moved to slide 4" is `DEC-DATA-003` (`OPEN`,
live path V1-002); and the narration is **text only**, the deck's own words — no
model wrote it and it is not audio (`DEC-TECH-007` is `OPEN`). What *is*
authoritative is the content: every scene comes from the package the session
pinned at start (`DEC-CONTENT-005`) through `GET /classes/{id}/scenes[/{order}]`,
so a correction published mid-lesson cannot change the slide under the student,
and a tampered file is refused (`SCENE_CHECKSUM_MISMATCH`) rather than shown.

Teacher-side, `admin/ClassesAdmin.tsx` uses the real roster: **invite by email**
creates-or-links the account in the tenant and enrols it in one step, then shows
the one-time sign-in code to hand over (returned once, never stored in the clear),
and the class detail offers the student join link to share.

## Implemented responsive layout (phone and large screen)

The app was built for the large screen — a classroom display, a projector, a
laptop in the Teacher Studio — and the UI **MUST** remain usable on a phone
without losing that layout. Every page is therefore one layout expressed
mobile-first, not two designs: `frontend/src/components/ui.tsx` holds the tokens
(tap target, page/card padding, form control, buttons, section tab) and
`frontend/src/components/PageHeader.tsx` is the app bar the five full pages share
(the shared nav, the page's `h1`, an optional qualifier and identifier, the tenant
field and the page's own action).

`lg` (≥1024px) is the switch between the two, and it is not arbitrary: it is
already the app's big-screen breakpoint (every two-column page and the one-row
header use it). Below `lg` the UI assumes a finger, at and above it a mouse:

- A control **MUST** be at least 44px tall below `lg` and may return to the
  original compact height above it. The shared nav is a **wrapping row of chips**
  — six destinations, shown rather than hidden behind a menu — and the section
  tabs (Admin, Settings; four each) wrap onto a second row rather than clipping a
  destination off the right edge, since a four-item strip that hides one item is
  worse than a two-line one.
- A form control **MUST** be 16px below `lg`: iOS Safari zooms the whole page when
  a focused control's text is smaller, and a phone in landscape and a tablet are
  both below `lg`. Above it the original dense size returns.
- A grid container **MUST** declare its own columns at the base breakpoint
  (`grid-cols-*`), and a definition list's value track is
  `minmax(0, 1fr)` rather than `1fr`. A bare `grid` — or an `auto`/`1fr` track
  whose minimum is `auto` — gets a floor of the content's **min-content** width,
  so one long unbreakable value (a deck filename such as
  `updated_B_o_c_o_T_ng_k_t_C_ng_t_c_…`, a SHA-256, a class id) sets the minimum
  width of the container and the page grows wider than the phone instead of the
  value ellipsising. That is not hypothetical: the library page measured 666px
  inside a 390px viewport because `<main>` declared its columns only from `md` up.
  Tailwind's `grid-cols-N` is `repeat(N, minmax(0, 1fr))`, whose floor is 0, so
  declaring the columns **at the base breakpoint** is the fix — a declaration
  behind a variant (`md:grid-cols-2`) is the bug, not the fix.
  `frontend/src/responsive.test.ts` is the source scan for the invariant, because
  jsdom has no layout engine and cannot measure the symptom.
- Definition-list rows (`ui.tsx::Row`) stack label over value on a phone, where a
  long identifier would otherwise be crushed beside its label, and a wide data
  table scrolls horizontally inside its own container rather than squeezing its
  columns.
- The teaching canvas sizes its bitmap to the **device pixel ratio** of the
  surface (`devicePixelRatio`; a phone reports 2–3), so a stroke is drawn at the
  screen's own resolution instead of an upscaled CSS-pixel bitmap. A stroke's
  points and width stay in the surface's **CSS** pixels — the paint transform
  applies the scale — so a stroke keeps its meaning across a re-measure.
  Re-measuring happens on a resize, a rotation and a `ResizeObserver` change.

Nothing about this is a behavioural change: no page gains or loses a control, no
request changes, and the phone layout is the same information the large screen
shows.

The invariant is verified by **measuring the running app in a browser** at 320,
360, 390, 414, 768 and 1280 px: `documentElement.scrollWidth` equals the viewport
on every route, including the densest state (the library with a deck selected, its
stored details, the IR viewer expanded and the raw JSON shown). There is no CI and
no layout test runner in this repository (`FND-001` is `TODO`), so that measurement
is a manual step; `frontend/src/responsive.test.ts` guards the one invariant that
caused a real defect.

## Implemented learning page

`/learn/{artifactId}` (`frontend/src/presentation/`) presents one deck: the
rendered slide, the **teaching canvas** over it, and the slide's teaching script.
The slide is read from the package already built for the deck (never re-rendered
on open) and fetched as an object URL, because `<img src>` cannot send the tenant
header. The teaching canvas (`TeachingCanvas.tsx`) is the client-local core of
the web classroom's dynamic surface: pen, highlighter and eraser, colour, width,
undo and clear, kept per slide for the life of the page. It is **not** shared:
the ordered per-class event stream that would carry an overlay to students is
`DEC-DATA-003` (technology `OPEN`) and its live path is V1-002, so the page says
the annotations stay in the browser rather than faking a broadcast. A browser
with no 2D canvas still shows the slide and reports annotation as unavailable.
The teaching script panel shows the slide's extracted text, its speaker notes,
its lesson-order script from the pinned package and the teacher's newest draft
revision for that section (`GET .../review-package/review-state`).

## Implemented automatic teaching (text only)

The learning page **teaches** as well as shows. `presentation/narration.ts` builds
one narration segment per scene from the deck's *authored* text in a fixed
precedence — the teacher's newest draft revision for the section, else the pinned
package's lesson script, else the slide's speaker notes, else the slide's own text
— and labels which one was used. Nothing is generated and nothing is re-ordered:
there is **no language model** in this path (no LLM provider exists in the
codebase and the decision ledger does not name one), so the feature teaches the
words the author wrote, reproducibly.

Press **Play** and the page narrates: the passage appears as a caption
(`presentation/LearnPage.tsx`, toggleable in Settings) and is appended to a
running transcript, and `presentation/useNarrationTimer.ts` moves to the next slide
once the passage's dwell has elapsed — `dwellMs` scales with the word count and the
teacher's chosen pace (Settings → Teaching) and is clamped to a readable band
(2.5–30 s), so a long passage gets longer and a blank slide still gets a beat.
Pause holds the position, Stop rewinds and clears the transcript, and the last
slide ends the narration rather than wrapping. The timer keys on the segment
identity as well as its length, so two equally long slides do not merge into one
tick, and a re-render cannot restart a countdown.

This is **text only**: no audio is produced. The voice capability is the
provider-neutral speech domain (`backend/app/speech/`, V0-012) and its provider
decision (`DEC-TECH-007`) is `OPEN`, so the text fallback path is the only one that
runs. It is also **client-local**: the narration is not an authoritative event, the
ordered per-class timeline with checkpoints, resume and bridge phrases is
`DEC-RUNTIME-005`/`DEC-DATA-003` and V0-013's work, and the stream that would carry
it to students is V1-002. Nothing about a narration is written to the server.

It can also **start itself at a time the teacher names**: a `datetime-local` value
on the panel, held as an instant by the page's own clock (`time.ts`, `useNow`), and
when that instant arrives the narration begins — Pause, Stop, the caption and the
transcript then behave exactly as if Play had been pressed. The trigger is
client-local for the same reason the narration is: it is a page waiting, not a
server clock, so the tab has to stay open, and the panel says so. Moving it
server-side is exactly the durable workflow/timeline work that is `DEC-TECH-003`
(`OPEN`) and V0-013.

## Implemented admin and settings areas

`/admin/{section}` (`frontend/src/admin/`) manages the V0 entities **through the
existing API only** — overview (what the tenant holds), courses & materials
(create a course, upload a deck into it, compile it, open its Studio/learning
page), classes (schedule, start, enrol) and publications (publish, verify). The
write verbs are the domain's own transitions; there is no generic update or delete,
and that is a property of the domain rather than a gap: content is immutable, a
draft is append-only and a publication is never deleted (`DEC-CONTENT-005`), so a
correction is a new version. The publications view is the place the seal is made
visible: `Publish` is idempotent on the content and reports a replay as such, and
`Verify integrity` re-checks the pinned package against the digest recorded at seal
time and reports `VERIFIED`/`MISMATCH`/`MISSING` without mutating anything.

A class can be given a **datetime**, and the classes view shows it and how far off it
is, ticking on the page's own clock (`time.ts`). With **auto-start** on, a class whose
time has come is started while the page is open, through the same idempotent
`POST /classes/{id}/start` the Start button uses, and each outcome is reported per
class — including a refusal, so a class whose course was never published says
`CLASS_NOT_READY`/`VERSION_NOT_PUBLISHED` instead of appearing to have started. This
is deliberately **not** a server scheduler: the backend records `scheduled_for` and
never acts on it (an automatic start would be a durable workflow, and `DEC-TECH-003`
is `OPEN`), so nothing runs with the page closed, the view states that, and Start
stays available either way.

`/settings/{section}` (`frontend/src/settings/`) holds **client preferences**,
because there is no settings API: the server's own configuration is its environment
(the home region) and the per-request render mode. General reports the tenant
(a real input, sent as `X-Institution-Id`) alongside read-only server facts
(`GET /renderer`, `GET /health`) and the home region; Rendering persists the
compile/preview mode and probes the renderer live in that mode (`GET
/artifacts/{id}/renders/{order}?mode=`), stating that a **packaged** render is
pinned at build time; Teaching sets the narration pace, autoplay and captions and
whether a scheduled class is started when its time arrives; Accessibility edits the
**classroom's own** persisted preferences through the classroom store, so the two
never drift. Preferences live in one module
(`settings/store.ts`, persisted and shared across tabs like the tenant) and are
never authoritative — nothing in Settings changes what the server stores, seals or
publishes.

## Locked Decisions Implemented

- `DEC-RUNTIME-004`
- `DEC-TURN-002`
- `DEC-TURN-009`
