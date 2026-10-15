# AI Implementation Guide

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Constrain implementation agents to the reconciled architecture.

## Dependencies

- None

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

## Before coding

1. Read `SOURCE_OF_TRUTH.md`, architecture baseline, relevant canonical component file, decision ledger, terminology registry, traceability rows, contracts, state machines, security, reliability, and tests.
2. List applicable requirement IDs and LOCKED decisions.
3. List ownership boundaries and invariants.
4. List commands, events, schemas, persistence, deadlines, retries, cancellation, fallback, and recovery.
5. If an OPEN decision blocks implementation, stop and request an ADR decision.
6. PROPOSED technology ADRs may be prototyped but MUST NOT be represented as accepted architecture.

## Forbidden

Do not rename canonical components, make LLM authoritative, activate group microphones without floor, use `latest` artifacts in a live class, make Redis durable truth, mutate published packages, bypass human review policies, or invent a provider-specific contract in domain code.

## Definition of done

Implementation, schemas, migrations, metrics, tests, docs, decision ledger, and traceability are updated together. Every critical invariant has an executable test.
