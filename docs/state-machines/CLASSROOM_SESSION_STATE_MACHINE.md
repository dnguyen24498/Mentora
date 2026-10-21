# Classroom Session State Machine

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
SCHEDULED -> PREPARING -> ACTIVE <-> DEGRADED -> RECOVERING -> ACTIVE/DEGRADED -> ENDING -> COMPLETED -> (REOPEN, new epoch) ACTIVE; FAILED only when no safe continuation. Pin versions and epoch in PREPARING. Non-active states have no valid floor.
```

## End and reopen

`END` moves `ACTIVE`/`DEGRADED` to `COMPLETED`, writes the final checkpoint, and revokes the session's join credentials. A `COMPLETED` class is **ended**: its lesson content (snapshot and pinned scenes) is refused to participants, while the class metadata and the class list remain readable so a student can see that it ended.

`REOPEN` is the one transition out of `COMPLETED`: `COMPLETED -> ACTIVE`. It continues the **same class occurrence** — the roster and the pinned version tuple are retained (`DEC-CONTENT-005`) — and returns the lesson to its first position. It starts a **new actor epoch** before emitting `classroom.session.reopened`, so every join credential and fenced command from the previous epoch is stale (`DEC-RUNTIME-007`). `FAILED` is not reopened: it has no safe continuation and requires a new class occurrence.

## Universal transition contract

Command ID deduplication, authorization, expected epoch/state, preconditions, transition, emitted event, effects with idempotency IDs, deadline/timeout, compensation/recovery, and post-transition invariant check are mandatory. Timeouts are explicit ordered inputs.

## Requirement Trace

- `DEC-RUNTIME-003`
- `DEC-RUNTIME-007`
- `DEC-DATA-004`
