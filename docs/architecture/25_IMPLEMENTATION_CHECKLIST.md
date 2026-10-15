# Implementation Checklist

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Provide the final architecture compliance gate.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Before coding list requirement IDs, locked/open decisions, owners, states, commands/events, schemas, data, provider deadlines, retry/cancellation/fallback/recovery, security/privacy/accessibility, telemetry, tests, rollback.

Every mutation has authority, authn/authz, ordering key, command ID, epoch/version, invariant validation, transaction/outbox, effect idempotency, response, metric, timeout, retry, and recovery.

Completion requires contract/migration validation, invariant/property/integration/E2E/chaos tests, telemetry/alerts, review gates, traceability update, and no unresolved contradiction.

## Locked Decisions Implemented

- `DEC-RUNTIME-003`
- `DEC-RELIABILITY-001`
