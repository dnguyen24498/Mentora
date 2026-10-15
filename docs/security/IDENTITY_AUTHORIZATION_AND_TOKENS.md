# Identity, Authorization, and Tokens

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Specify principals, roles, and token validation.

## Dependencies

- `docs/architecture/17_SECURITY_PRIVACY_AND_GOVERNANCE.md`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

Users authenticate through institutional federation; services use workload identity. Roles: platform/institution admin, IT operator, course admin, teacher, moderator, student, auditor. Every request validates tenant/course/class/resource. Normal student media permission is subscribe-only. Floor token independently binds class/room/student/request/floor/epoch/state/nonce/expiry and publish_audio only. Key rotation overlaps safely; revocation failure denies new publication.

## Requirement Trace

- `DEC-TURN-003`
- `DEC-TURN-008`
