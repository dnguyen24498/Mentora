# Stt Capacity Unavailable

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
Reservation denied -> remain queued with bounded backoff or offer text; do not pause teacher/grant floor.
```

## Assertions

No stale epoch effect, duplicate side effect, leaked reservation/token, version change, unauthorized retrieval, or indefinite wait. Every terminal path emits metrics and user-visible state.

## Requirement Trace

- `DEC-RUNTIME-003`
- `DEC-RUNTIME-007`
- `DEC-RELIABILITY-001`
