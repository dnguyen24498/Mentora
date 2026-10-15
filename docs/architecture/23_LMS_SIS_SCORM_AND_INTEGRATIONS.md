# LMS, SIS, SCORM, and Integrations

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define institutional integration boundaries.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Identity and LMS adapters synchronize launches, courses, rosters, deep links, and approved outcomes with explicit field ownership/conflict policy. Official records are not inferred by LLM.

SCORM manifest/organizations/sequencing may be structurally imported. Interactive non-convertible SCO runs in isolated origin/iframe with CSP, restricted network/API, and compatibility adapter. Never claim universal native conversion.

## Locked Decisions Implemented

- `DEC-SCORM-001`
