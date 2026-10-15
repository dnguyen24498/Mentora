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
SCHEDULED -> PREPARING -> ACTIVE <-> DEGRADED -> RECOVERING -> ACTIVE/DEGRADED -> ENDING -> COMPLETED; FAILED only when no safe continuation. Pin versions and epoch in PREPARING. Non-active states have no valid floor.
```

## Universal transition contract

Command ID deduplication, authorization, expected epoch/state, preconditions, transition, emitted event, effects with idempotency IDs, deadline/timeout, compensation/recovery, and post-transition invariant check are mandatory. Timeouts are explicit ordered inputs.

## Requirement Trace

- `DEC-RUNTIME-003`
- `DEC-RUNTIME-007`
- `DEC-DATA-004`
