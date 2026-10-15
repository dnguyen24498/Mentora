# Teacher Orchestrator

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Separate pedagogy from deterministic control.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Teacher Orchestrator decides explanation strategy, next approved instructional action, retrieval need, evidence use, quiz/check, adaptation, answer plan, and natural resume phrase. It receives pinned session context and returns schema-valid proposals.

Classroom Actor validates proposal against policy, current state/version, lesson plan, and permissions. Orchestrator does not own floor, lesson truth, attendance, grades, artifacts, or media transport.

## Locked Decisions Implemented

- `DEC-RUNTIME-002`
- `DEC-PERSONAL-001`
