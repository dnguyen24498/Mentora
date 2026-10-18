# V0-021: Identity accounts, roles, and the student learning surface

**Week:** W8  
**Status:** IN_PROGRESS  
**Owner:** Solo developer  
**Target:** V0

## Objective

Replace the "whoever sends the header is whoever they say" tenant model with real
principals: accounts with roles, authenticated sessions, tenant-bound
authorization, a login surface, a teacher roster, and the student join + fullscreen
learning surface that consumes the pinned session.

## Dependencies

- V0-009 (class, enrolment, join credential)
- V0-011 (classroom client, snapshot projection)

## Requirement IDs

- `DEC-TURN-001` (student media stays subscribe-only)
- `DEC-TURN-003` / `DEC-TURN-008` (floor authority; the join credential is fenced)
- `DEC-CONTENT-005` (the student learns the pinned publication, never `latest`)
- `DEC-RUNTIME-007` (the credential is epoch-fenced)
- `DEC-DATA-004` (the client projection is validated before use)
- `DEC-RELIABILITY-001` (deadline, bounded retry, classified failure)

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/architecture/17_SECURITY_PRIVACY_AND_GOVERNANCE.md`
- `docs/security/IDENTITY_AUTHORIZATION_AND_TOKENS.md`
- `docs/security/THREAT_MODEL_AND_CONTROLS.md`
- `docs/architecture/15_FRONTEND_CLASSROOM_AND_STUDIO.md`
- `contracts/openapi/openapi.yaml`
- `contracts/security/floor-token-claims.schema.json`

## In Scope

- An `identity` domain: accounts, roles, principals, and short-lived sessions, with
  a provider-neutral `Authenticator` port and an explicitly-labelled local
  development adapter (the identity mechanism is **not** a decided technology; the
  canonical architecture names institutional federation / OIDC-OAuth and there is
  no accepted ADR for it, so the adapter is a temporary mock — the same shape
  `ADR-P007` gives the TTS mock in V0-012).
- Role-scoped authorization on the existing verbs: teacher-only for course, upload,
  compile, review, publish, schedule, start and enrolment; student read of the
  class, its snapshot and the pinned scene renders; the join credential issued for
  the authenticated student only.
- Login / logout / current-principal endpoints and contracts.
- Teacher roster: invite a student by email, creating-or-linking the account in the
  tenant and enrolling in one step.
- Student surface: join a class and learn it fullscreen from the pinned session.
- A `GET /classes/{classId}/scenes/{order}` read that serves the slide from the
  session's **pinned** package (`DEC-CONTENT-005`: no runtime `latest` lookup).

## Out of Scope

- Federated login (OIDC/SAML) itself, and any password/credential policy presented
  as the platform's authentication decision. The seam is what is built.
- Groups, cohorts, guardians, multi-role accounts, and account administration UI.
- Live media of any kind: no SFU, no microphone, no floor, no audio
  (`DEC-TURN-001`; the ordered per-class log is `DEC-DATA-003`, `OPEN`).
- Any change to the Classroom Actor's transitions or the snapshot's shape.

## Acceptance Criteria

| Criterion | How it is verified |
| --- | --- |
| A principal's tenant comes from the session, never from a request field | A session for tenant A cannot read or write tenant B; a spoofed header is ignored when a session is present |
| Roles are enforced server-side, not by hiding UI | A student token is refused (`403`) on every teacher verb; a teacher token is refused where student identity is required |
| The join credential is the authenticated student's own | `POST /classes/{id}/bootstrap-token` takes no student id; it uses the session's account and refuses a non-enrolled student |
| Login has no enumeration oracle | Unknown account and wrong credential return the same code/status; the check is deadline-bounded and retried only when retryable |
| A revoked or expired session is refused | `401` with a stable code; logout is idempotent |
| The student learns the pinned publication | The scene read resolves the session plan's `package_id`, so publishing a correction mid-session does not change what the student sees |
| Nothing is presented as decided | The local adapter is named a development mock in code, API surface, docs, and ledger traceability |

## Blocker

The identity mechanism has **no accepted ADR** (`FND-002` is `TODO`), so no provider
adapter may be presented as architecture. Resolution: build the seam and label the
adapter a mock, exactly as V0-012 did for `DEC-TECH-007`.
