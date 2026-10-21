# Timeline State Machine

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define authoritative transitions and failure handling.

## Dependencies

- `docs/architecture/02_ARCHITECTURAL_INVARIANTS.md`
- `docs/architecture/09_CLASSROOM_ACTOR_AND_RECOVERY.md`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

## States and flow

```text
READY -> RUNNING -> PAUSING -> PAUSED -> RESUMING -> RUNNING/COMPLETED. Late events follow execute/skip/coalesce/block. Checkpoint occurs before floor invitation.
```

## Universal transition contract

Command ID deduplication, authorization, expected epoch/state, preconditions, transition, emitted event, effects with idempotency IDs, deadline/timeout, compensation/recovery, and post-transition invariant check are mandatory. Timeouts are explicit ordered inputs.

## Requirement Trace

- `DEC-RUNTIME-003`
- `DEC-RUNTIME-007`
- `DEC-DATA-004`

## Implemented (V0-013)

`backend/app/classroom/timeline/` implements the `TimelineController` for V0:
`IDLE → PREPARING → SYNTHESIZING → PLAYING → COMPLETED`, with `CANCELLED`,
`FAILED` and `FALLBACK` terminal. One generation per narration request; a
different generation is stale, a repeated marker/chunk is a duplicate, a marker
behind the last one or after a terminal verdict is late, and an audio gap raises
rather than splicing. A checkpoint records scene/segment/chunk/offset (semantic,
not bytes); resume starts a new generation at that segment. The script is read from
the pinned package and cut into word-safe chunks (≤160 characters, closed at a
sentence end once ≥40), each synthesized separately so the first audio arrives
after one chunk. It streams over `GET /classes/{classId}/narration/{order}` to the
teacher's tab only; shared student audio is V1-005. The provider is the neutral
deterministic mock (`DEC-TECH-007` `OPEN`).
