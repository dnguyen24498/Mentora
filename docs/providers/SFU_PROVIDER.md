# Sfu Provider

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define a provider-neutral replaceable capability.

## Dependencies

- `docs/architecture/13_MEDIA_SPEECH_AND_VOICE.md`
- `docs/architecture/14_LLM_RAG_AND_AI_SAFETY.md`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

## Interface

room/create/token/track callbacks/revoke/remove/health/drain. SFU state never decides floor or lesson truth.

## Common behavior

Every operation exposes stable error classification, idempotency where applicable, deadline/cancellation, concurrency/queue metrics, circuit-breaker signals, data region, usage/cost, trace propagation, and test double.

## Requirement Trace

- `DEC-RELIABILITY-001`
