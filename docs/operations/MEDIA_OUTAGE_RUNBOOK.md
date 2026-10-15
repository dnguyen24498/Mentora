# Media Outage Runbook

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define operator response and validation.

## Dependencies

- `docs/architecture/19_RELIABILITY_SLO_AND_BACKPRESSURE.md`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Trigger from alerts or reported experience. Immediate response: MEDIA_RECOVERING, stop grant, revoke floor, reconnect/recreate, republish, snapshot restore, segment resume. Validate user recovery, no invariant breach, no stale token/reservation, queue/latency/error health, and durable consistency. Escalate by severity and create post-incident actions/tests.

## Requirement Trace

- `DEC-RELIABILITY-001`
- `DEC-RELIABILITY-002`
