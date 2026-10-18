# V0-011: Classroom frontend snapshot and event reducer

**Week:** W5  
**Status:** DONE  
**Owner:** Solo developer  
**Target:** V0

## Objective

Render the authoritative classroom state and recover from refresh.

## Dependencies

- V0-010

## Requirement IDs

- `DEC-RUNTIME-004`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/architecture/15_FRONTEND_CLASSROOM_AND_STUDIO.md`
- `contracts/websocket/PROTOCOL.md`

## In Scope

- Classroom shell.
- Separate snapshot/event/media/UI stores.
- Scene display and controls.
- Duplicate/stale/gap behavior.
- Reconnect/resync UI.

## Out of Scope

- Microphone.
- Raise Hand.
- WebRTC.

## Acceptance Criteria

- Refresh restores scene and state.
- Duplicate/stale event ignored.
- Sequence gap requests resync and disables unsafe control.

## Required Tests

- Reducer unit tests, refresh E2E, sequence gap E2E, accessibility smoke.

## Files/Areas Allowed to Change

- `frontend/apps/classroom/`
- `frontend/packages/`
- `tests/e2e/`

## Quality Gate

All tests pass; no architecture contradiction; telemetry and traceability are updated; no new production dependency without an accepted ADR.

## Completion Evidence

- Link to commit/PR: `581bf4c`
- Test command and result: `cd frontend && npx tsc --noEmit && npm test` — **61 passed** (was 38; +23)
- Demo recording/screenshot:
- Metrics observed: `ClassroomTelemetry` counters (connects, resyncs, eventsApplied, eventsIgnored, gaps, staleEpochs, commandsSent, loadFailures) plus structured events (`classroom.connect/snapshot/event/resync/command/load_failed`) — identities and counts only, never scene text/transcript/audio.
- Traceability rows added: `DEC-RUNTIME-004` (client), `DEC-RUNTIME-003`/`DEC-RUNTIME-007` (client mirrors), `DEC-DATA-004`, `DEC-RELIABILITY-001`.
- Known limitations:

## Files/Areas Allowed to Change (as delivered)

- `frontend/apps/classroom/` -> `frontend/src/classroom/` (the nominal
  `frontend/apps/classroom/` app does not exist; the repo is a single Vite app —
  the same mapping precedent as V0-004…V0-007). Added `ClassroomPage.tsx`,
  `ClassroomShell.tsx`, `useClassroomSession.ts` and
  `ClassroomPage.test.tsx`.
- `frontend/packages/` -> `frontend/src/classroom/state/` (shared, React-free
  state): `types.ts`, `reducer.ts`, `store.ts`, `session.ts`, `transport.ts`,
  `telemetry.ts`, `testing.ts` + `reducer.test.ts`, `session.test.ts`.
- `tests/e2e/` -> `frontend/src/classroom/state/*.test.ts` and
  `frontend/src/classroom/ClassroomPage.test.tsx` (the repo's actual test root;
  the E2E is a component-level end-to-end flow driven through an injected
  transport, not browser automation — same precedent as V0-007).

Also touched (required to keep the tree consistent):
`frontend/src/api/client.ts` (the snapshot types + `loadSnapshot`),
`frontend/src/router.tsx` + `frontend/src/router.test.tsx` (the
`/classroom/{classId}` route), `frontend/src/App.tsx` + `frontend/src/App.test.tsx`,
`frontend/vite.config.ts` (proxy `/classes`), `frontend/README.md`, `AGENTS.md`,
`docs/architecture/15_FRONTEND_CLASSROOM_AND_STUDIO.md` + regenerated
`docs/architecture/ARCHITECTURE_FULL.md`, `governance/TRACEABILITY_MATRIX.csv`,
`tasks/STATUS_BOARD.csv`, this task folder.

## What was delivered

The classroom client is a **projection** of the actor, never a source of truth
(DEC-RUNTIME-004). One page, `/classroom/{classId}`:

- **Separate stores** (`frontend/src/classroom/state/store.ts`): the raw
  **snapshot**, the **event reducer** slice, **media** and **ephemeral UI /
  accessibility preferences** — the last two never touch the actor.
- **Pure reducer** (`reducer.ts`): applies an event only when contiguous for the
  current epoch; **ignores duplicates and stale events** (`DEC-RUNTIME-003`);
  **discards a superseded epoch** (`DEC-RUNTIME-007`); reports a **gap** instead
  of applying out of order.
- **Session** (`session.ts`): a gap, a stale epoch or a manual action re-reads the
  authoritative snapshot with bounded retry (`DEC-RELIABILITY-001`) and resets the
  event cursor; a failed load leaves the client `disconnected` and frozen.
- **Shell** (`ClassroomShell.tsx`): scene + authoritative state display, previous
  / next scene and resync controls (disabled whenever the client is not `live`),
  a recovery banner, and accessibility preference toggles (reduced motion, high
  contrast) persisted to `localStorage`.
- **Transport seam** (`transport.ts`): the ordered per-class event/command
  mechanism is `DEC-DATA-003` with technology `OPEN`, so V0 ships a transport that
  reads the snapshot only and advertises `liveEvents:false`/`commands:false`; the
  shell says so instead of faking a stream. The live stream/command path is
  V1-002.
- **Telemetry** (`telemetry.ts`): structured events + counters, identities only.

## Known limitations

- **No live event stream yet.** The ordered per-class mechanism is
  `DEC-DATA-003`/V1-002 and its technology is `OPEN` (`DEC-TECH-001/002`), so the
  shipped transport reads the authoritative snapshot and nothing else; the live
  controls are disabled and the page says why. Tests and a local demo drive events
  through the injected `ClassroomTransport`.
- **The scene is shown as state, not pixels.** The pinned package's visual scene
  has no client-facing render endpoint in V0; the shell shows the authoritative
  scene/step identity and notes that the visual presentation is V0-013.
- **Client command intents only.** `ClassroomSession.send` builds a
  `ClassroomCommand` and hands it to the transport; the V0 transport cannot carry
  it, and resolving a target belongs to the timeline/V1 command path. The client
  never mutates authoritative state locally.
- **Media is inert by design.** `studentMicActive` is always `false` and
  captions/transcript stay empty (mic/raise-hand/WebRTC are out of scope;
  `DEC-TURN-001`). The media slice exists so the separation is real and V0-013/V1
  can populate it.
- **No CI/lint config yet** (FND-001 is still `TODO`); `tsc` and `npm test` are run
  manually.
