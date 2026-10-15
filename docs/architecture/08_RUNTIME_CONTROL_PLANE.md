# Runtime Control Plane

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define command path, modules, and deployment boundary.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Gateway authenticates, validates schema, authorizes, then places commands in an ordered per-class mechanism. Classroom Actor deduplicates and validates epoch/version/invariants, transitions state, persists event/outbox, and invokes idempotent capabilities.

Actor contains session, lesson, turn, timeline, question, checkpoint coordination. Teacher Orchestrator is called for pedagogical decisions but cannot mutate authoritative state directly. V1 deploys control modules together.

## Locked Decisions Implemented

- `DEC-RUNTIME-001`
- `DEC-RUNTIME-002`
- `DEC-RUNTIME-003`
- `DEC-DATA-003`
- `DEC-DEPLOY-001`
