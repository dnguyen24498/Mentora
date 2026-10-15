# Architectural Invariants

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define conditions that must remain true under success, retry, and failure.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

## Content invariants

Runtime never parses source. Published package immutable. Active version tuple immutable. Baseline usable without Teaching Graph. Retrieval cannot cross scope/version.

## Classroom invariants

Exactly one logical owner; at most one floor; STT implies floor; student SPEAKING excludes teacher PLAYING; stale epoch cannot mutate/authorize; duplicate command creates one logical effect.

## Recovery invariants

Snapshot/checksum/schema validated before replay. Recovery never silently upgrades artifacts. All reservations/tokens have terminal release/revoke paths.

## Security invariants

Every resource is tenant-scoped; provider credentials never reach clients; audio transmission is visible and authorized; raw student audio retention is disabled by default.

## Locked Decisions Implemented

- `DEC-RUNTIME-001`
- `DEC-RUNTIME-003`
- `DEC-RUNTIME-007`
- `DEC-TURN-004`
- `DEC-TURN-005`
- `DEC-DATA-004`
- `DEC-DATA-005`
