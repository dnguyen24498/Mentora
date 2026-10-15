# Testing, Chaos, and Acceptance

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Make architecture correctness executable.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Unit reducers, property invariants, schema/consumer contracts, provider conformance, persistence/outbox integration, browser/media E2E, load/soak, chaos/DR, security, accessibility, and content fidelity.

Chaos includes actor death/network partition, stale callbacks, Redis restart, DB failover, SFU loss, late audio, STT final loss, TTS marker loss, slow/cancelled RAG/LLM, token replay, and capacity saturation. Pass requires safe degradation and zero invariant breach.

## Locked Decisions Implemented

- `DEC-RUNTIME-003`
- `DEC-RUNTIME-007`
- `DEC-RELIABILITY-001`
- `DEC-RELIABILITY-002`
