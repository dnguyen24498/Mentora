# Test Strategy

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define executable coverage for every architecture layer.

## Dependencies

- `docs/architecture/21_TESTING_CHAOS_AND_ACCEPTANCE.md`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Pure reducer/state tests; property generated commands; schema and consumer contracts; provider adapter conformance; persistence/outbox integration; browser/media E2E; content fidelity; RAG grounding; Vietnamese STT/voice benchmarks; security/accessibility; load/soak; chaos/DR. Deterministic mocks inject timeout, duplicate, late callback, and capacity faults.

## Requirement Trace

- `DEC-RUNTIME-003`
- `DEC-RELIABILITY-001`
