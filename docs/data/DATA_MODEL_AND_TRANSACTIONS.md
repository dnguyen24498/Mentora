# Data Model and Transactions

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define physical ownership and transaction rules without locking a vendor beyond required capability.

## Dependencies

- `docs/architecture/16_DATA_STORAGE_AND_EVENTS.md`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Tables/collections cover institutions, users, courses, versions, source artifacts, compiler jobs, content packages, lesson plans, classes, sessions, snapshots, turns, questions, voice authorizations, idempotency, outbox, and audit. Every tenant-owned row has tenant ID. Unique constraints enforce one live session and one command result. State/event/outbox commit atomically. Published metadata/index relationship commits only after immutable artifacts exist.

## Requirement Trace

- `DEC-DATA-001`
- `DEC-DATA-002`
- `DEC-DATA-004`
