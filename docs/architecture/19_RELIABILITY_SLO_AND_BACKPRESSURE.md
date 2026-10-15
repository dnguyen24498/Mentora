# Reliability, SLO, and Backpressure

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define bounded latency, overload behavior, and fallback.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Candidate targets: control p95 <250ms, hand ACK <300ms, floor-to-mic <1s, audio cancel <300ms, end-turn to first answer audio p95 <5s, presentation drift <200ms, recovery <10s, resume >99.5%, invariant violations zero.

Reserve scarce capabilities before granting user-visible permission. Bound queues per tenant/provider/class. Propagate end-to-end deadline/cancellation. Retry transient idempotent work only. Circuit breakers trigger cached script, neutral voice, text/captions, typed question, or controlled pause.

## Locked Decisions Implemented

- `DEC-RELIABILITY-001`
- `DEC-RELIABILITY-002`
