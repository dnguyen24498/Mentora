# Deployment and Scaling

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define deployment profiles and measured scale progression.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Profiles: managed cloud, institution cloud, hybrid, private/on-prem. V1 control plane modular monolith; separately scalable compiler, media, search, STT/LLM gateways, GPU voice.

A class has a home region for actor/gateway/SFU/STT/voice path. Drain nodes without terminating active classes. Validate 10, 50, 100, 250, 500 classes only after previous profile passes, separated by student count and interaction duty cycle.

## Locked Decisions Implemented

- `DEC-DEPLOY-001`
- `DEC-DEPLOY-002`
