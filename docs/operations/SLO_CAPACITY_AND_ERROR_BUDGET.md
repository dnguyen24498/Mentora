# SLO, Capacity, and Error Budget

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Turn candidate targets into a validation plan.

## Dependencies

- `docs/architecture/19_RELIABILITY_SLO_AND_BACKPRESSURE.md`
- `docs/architecture/20_OBSERVABILITY_COST_AND_CAPACITY.md`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

SLIs are user-observed control latency, floor readiness, answer audio, drift, recovery, resume, and invariant violations. Targets remain candidates until load validation. Capacity tracks compiler throughput, classes, students, active floors/STT/TTS/LLM, SFU bandwidth, and GPU RTF. Error budget never permits correctness/security violations. Scale by measured TCU and profile, not class count alone.

## Requirement Trace

- `DEC-RELIABILITY-001`
- `DEC-RELIABILITY-002`
