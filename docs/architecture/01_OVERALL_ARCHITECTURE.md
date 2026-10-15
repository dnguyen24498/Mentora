# Overall Architecture

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Show end-to-end components and flows.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

## Overall diagram

```text
Institution: IdP/SSO | LMS/SIS | Teachers | Students | IT
                              |
                    Edge / API / WebSocket
                 +------------+------------+
                 |                         |
Content & Publication                 Runtime Control
Teacher Studio                        Ordered commands by class_id
Secure Import                         Classroom Actor
Compiler/IR/Renderer/Media            Lesson/Turn/Timeline/Checkpoint
Baseline + AI Enrichment              Teacher Orchestrator
Review -> Published CTF               Snapshot/Event Recovery
                 |                         |
                 +------------+------------+
                              |
Capability: Knowledge/RAG | LLM | STT | Voice/TTS | Vision/OCR
Presentation: scene/step/quiz/caption events
Media: SFU/TURN, shared teacher track, granted student track
Data: durable DB, event log, Redis, search, object storage
Governance: identity, policy, consent, audit, retention, SLO
```

## Content flow

Source -> deterministic extract/render/media -> baseline -> optional semantic enrichment -> review -> immutable package/index.

## Classroom flow

Start -> pin versions/region -> initialize actor/media -> teach -> question -> grounded answer -> checkpoint resume -> complete.

## Locked Decisions Implemented

- `DEC-CONTENT-001`
- `DEC-CONTENT-002`
- `DEC-RUNTIME-001`
- `DEC-RUNTIME-002`
