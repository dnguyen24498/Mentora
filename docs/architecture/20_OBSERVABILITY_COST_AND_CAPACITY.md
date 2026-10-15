# Observability, Cost, and Capacity

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define experience metrics, tracing, cost, and scaling units.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Propagate trace, tenant, class, session, command, correlation/causation, epoch/version, and artifact versions while redacting sensitive text/audio.

Measure actor/state/invariant, queue/floor/STT/VAD, LLM/RAG/TTS, marker drift, WebRTC network, compiler fidelity/review, recovery and cost. Define Teaching Compute Unit empirically from actor and AI duty cycles. Alert immediately on invariant breach and use SLO burn alerts.

## Locked Decisions Implemented

- `DEC-RELIABILITY-001`
- `DEC-DEPLOY-002`
