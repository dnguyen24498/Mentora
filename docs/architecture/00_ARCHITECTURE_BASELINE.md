# Architecture Baseline

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Declare the canonical stable architecture agreed across the design discussion.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

## Stable core

```text
Source Materials -> Secure Import Gateway -> Deterministic Content Compiler
-> Content IR -> Baseline Content Package
-> Selective AI Enrichment + RAG Indexing
-> Validation/Human Review -> Published CTF Package
-> Runtime Session Plan -> Classroom Actor
-> Lesson / Turn / Timeline / Question / Checkpoint modules
-> Teacher Orchestrator and replaceable Capability Services
-> WebSocket presentation + WebRTC SFU -> React Classroom
```

## Baseline promise

Mentora promises approved-content teaching, deterministic classroom control, grounded answers, controlled student speech, version consistency, recoverable failure, and measurable realtime behavior. It does not promise perfect arbitrary-document understanding, absolute zero failure, or autonomous replacement of lecturers.

## Planes

Compiler, Publication, Runtime Control, Capability, Media, Presentation, Data, and Governance planes. Their logical boundaries are stable even if V1 deployment groups modules.

## Locked Decisions Implemented

- `DEC-CONTENT-001`
- `DEC-CONTENT-002`
- `DEC-CONTENT-003`
- `DEC-CONTENT-004`
- `DEC-CONTENT-005`
- `DEC-CONTENT-006`
- `DEC-CONTENT-007`
- `DEC-CONTENT-008`
- `DEC-CONTENT-009`
- `DEC-RUNTIME-001`
- `DEC-RUNTIME-002`
- `DEC-RUNTIME-003`
- `DEC-RUNTIME-004`
- `DEC-RUNTIME-005`
- `DEC-RUNTIME-006`
- `DEC-RUNTIME-007`
- `DEC-TURN-001`
- `DEC-TURN-002`
- `DEC-TURN-003`
- `DEC-TURN-004`
- `DEC-TURN-005`
- `DEC-TURN-006`
- `DEC-TURN-007`
- `DEC-TURN-008`
- `DEC-TURN-009`
- `DEC-DATA-001`
- `DEC-DATA-002`
- `DEC-DATA-003`
- `DEC-DATA-004`
- `DEC-DATA-005`
- `DEC-RELIABILITY-001`
- `DEC-RELIABILITY-002`
- `DEC-DEPLOY-001`
- `DEC-DEPLOY-002`
- `DEC-PERSONAL-001`
- `DEC-SCORM-001`
