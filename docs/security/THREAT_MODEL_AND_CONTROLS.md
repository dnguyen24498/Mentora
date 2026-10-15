# Threat Model and Controls

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Tie threats and controls to locked architecture.

## Dependencies

- `docs/architecture/17_SECURITY_PRIVACY_AND_GOVERNANCE.md`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Assets: education records, voice references, source/published content, tokens, classroom state, outcomes, audit. Threats: cross-tenant, replay, stale owner, malicious archive, prompt injection, poisoned index, voice impersonation, leakage, admin misuse, supply chain. Controls: tenant authorization, short-lived epoch-fenced tokens, sandbox, provenance, immutable publication, constrained tools, retrieval filters, consent/revocation, redaction, least privilege, audit, signing/SBOM/scanning.

## Requirement Trace

- `DEC-RUNTIME-007`
- `DEC-TURN-008`
- `DEC-DATA-005`
