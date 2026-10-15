# LLM, RAG, and AI Safety

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define grounded generation and guardrails.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Knowledge Service applies authorization and pinned version filters before hybrid retrieval, returns evidence IDs/source/index version, and rejects incompatible results. LLM Router selects allowed model by task, latency, cost, residency, and capability.

LLM output is explanatory text or schema-valid proposal. Application re-authorizes tool actions. Prefer approved evidence, label supplement/uncertainty, never fabricate citations, and escalate high-impact/safety issues.

## Locked Decisions Implemented

- `DEC-DATA-005`
- `DEC-RELIABILITY-001`
- `DEC-RUNTIME-002`
