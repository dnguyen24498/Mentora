# Invariant and Chaos Tests

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Enumerate correctness tests under faults.

## Dependencies

- `docs/architecture/02_ARCHITECTURAL_INVARIANTS.md`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Generate duplicate/stale/reordered client commands, timeout races, epoch changes, reconnects, and provider callbacks. Assert one floor, no STT without floor, no teacher/student overlap, no old epoch, one effect per command, immutable versions, compatible evidence, released reservations, and eventual terminal cancellation. Inject actor death/partition, Redis restart, DB failover, SFU failure, late frames, missing STT final/markers, slow cancelled AI, token replay, and capacity saturation.

## Requirement Trace

- `DEC-RUNTIME-007`
- `DEC-TURN-004`
- `DEC-TURN-005`
- `DEC-DATA-004`
