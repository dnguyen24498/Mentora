# Turn Manager State Machine

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
IDLE -> HAND_RAISED -> QUEUED -> RESERVING -> WAITING_SAFE_MARKER -> CANCELLING_AUDIO -> FLOOR_GRANTED -> SPEAKING -> FINALIZING -> PROCESSING -> ANSWERED -> IDLE. Every state defines cancel, timeout, disconnect, stale epoch, and recovery transitions.
```

## Universal transition contract

Command ID deduplication, authorization, expected epoch/state, preconditions, transition, emitted event, effects with idempotency IDs, deadline/timeout, compensation/recovery, and post-transition invariant check are mandatory. Timeouts are explicit ordered inputs.

## Requirement Trace

- `DEC-RUNTIME-003`
- `DEC-RUNTIME-007`
- `DEC-DATA-004`
