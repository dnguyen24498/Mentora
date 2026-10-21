# Class End

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define a success or failure interaction with consistency assertions.

## Dependencies

- `docs/architecture/19_RELIABILITY_SLO_AND_BACKPRESSURE.md`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

## Flow

```text
Stop accepting turns -> revoke/cancel -> persist final checkpoint/outcomes -> stop media -> flush outbox/audit -> COMPLETED.
```

## Assertions

No stale epoch effect, duplicate side effect, leaked reservation/token, version change, unauthorized retrieval, or indefinite wait. Every terminal path emits metrics and user-visible state.

`COMPLETED` closes the **occurrence**, not the class record: the class metadata and list stay readable so a participant can see that it ended, while participant reads of the lesson content (the snapshot and the pinned scenes) are refused until an explicit `REOPEN` (`COMPLETED -> ACTIVE`) starts a new actor epoch. `REOPEN` keeps the roster and the pinned package and returns the lesson to its first position.

## Requirement Trace

- `DEC-RUNTIME-003`
- `DEC-RUNTIME-007`
- `DEC-RELIABILITY-001`
