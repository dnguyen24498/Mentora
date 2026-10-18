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

## Locked Decisions Implemented

- `DEC-RUNTIME-004`
- `DEC-TURN-002`
- `DEC-TURN-009`
