# Data, Storage, and Events

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define durable truth, projections, ordering, and retention.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Durable relational store owns institution/course/publication/session/checkpoint/academic records. Ordered log stores per-class commands/events. Redis stores routing/projection/cache/revocation, never sole truth. Object storage stores immutable binaries; search is rebuildable.

Use transactional outbox to avoid database/event dual write. Delivery may be at-least-once; logical effects are idempotent. Raw student audio is off by default; retention policies are separate by data class.

## Locked Decisions Implemented

- `DEC-DATA-001`
- `DEC-DATA-002`
- `DEC-DATA-003`
- `DEC-DATA-004`
