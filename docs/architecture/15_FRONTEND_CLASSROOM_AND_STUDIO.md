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
general, rendering, teaching, accessibility). A shared navigation
(`frontend/src/components/SiteNav.tsx`) is embedded in every page header, so each
page is reachable from every other. The deck/class-scoped entries use the id the
page holds or the last one opened — remembered in `localStorage` alongside the
tenant — and are disabled with an explanation before an id exists. The library is
the hub: it lists the tenant's classes (`GET /classes`) and links each to its
classroom, and offers both the Studio and the learning page for a selected deck.

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

`/settings/{section}` (`frontend/src/settings/`) holds **client preferences**,
because there is no settings API: the server's own configuration is its environment
(the home region) and the per-request render mode. General reports the tenant
(a real input, sent as `X-Institution-Id`) alongside read-only server facts
(`GET /renderer`, `GET /health`) and the home region; Rendering persists the
compile/preview mode and probes the renderer live in that mode (`GET
/artifacts/{id}/renders/{order}?mode=`), stating that a **packaged** render is
pinned at build time; Teaching sets the narration pace, autoplay and captions;
Accessibility edits the **classroom's own** persisted preferences through the
classroom store, so the two never drift. Preferences live in one module
(`settings/store.ts`, persisted and shared across tabs like the tenant) and are
never authoritative — nothing in Settings changes what the server stores, seals or
publishes.

## Locked Decisions Implemented

- `DEC-RUNTIME-004`
- `DEC-TURN-002`
- `DEC-TURN-009`
