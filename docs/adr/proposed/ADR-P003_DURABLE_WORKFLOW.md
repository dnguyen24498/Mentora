# Adr-P003 Durable Workflow

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Document a proposed technology decision without changing canonical architecture.

## Dependencies

- `governance/DECISION_LEDGER.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

## Status

PROPOSED

## Decision to make

Compare Temporal, explicit workflow tables, managed durable functions, and task queues for compilation/publication, excluding marker-level realtime control.

## Required evidence

Prototype benchmark, security/privacy impact, operational complexity, cost, migration/rollback, compatibility with LOCKED decisions, and owner approval. Until accepted, provider-neutral interfaces and mocks are used.
