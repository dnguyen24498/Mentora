# V0-022: Administration accounts and role separation

**Week:** W8  
**Status:** IN_PROGRESS  
**Owner:** Solo developer  
**Target:** V0

## Objective

Separate the three account types the institution actually has — an **institution
administrator** who owns the directory, a **teacher** who runs classes, and a
**student** who attends them — and give each one a sign-in/sign-out session:

- an administrator can **create, read, update and remove** teacher and student
  accounts;
- a teacher can **assign and unassign students** on the classes they run, choosing
  from accounts the administrator created;
- every account — including an administrator's — signs in and out through the same
  session surface (`POST /auth/login`, `POST /auth/logout`, `GET /auth/me`).

Account provisioning moves out of the teacher's enrolment flow: a teacher may
*enrol an existing account*, only an administrator may *create* one. That is the
separation of duties the slice adds — not a new authentication mechanism.

## Dependencies

- V0-021 (accounts, roles, sessions, enrolment, join credential)

## Requirement IDs

- `DEC-RUNTIME-007` (session revocation; a disabled account cannot keep using a live session)
- `DEC-RUNTIME-003` (idempotent commands: create-or-link, enrol, unassign, sign out)
- `DEC-RELIABILITY-002` (an availability failure is not a denial; a refusal is a stable code)
- `DEC-DATA-001` (durable relational store owns institutional/account truth)
- `DEC-TURN-001` (the student's join credential stays subscribe-only)
- `DEC-CONTENT-005` (unchanged: the student still learns the pinned publication)

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/ARC_OVERVIEW.md` §27 (Identity, SSO, and Roles — the canonical role list)
- `docs/security/IDENTITY_AUTHORIZATION_AND_TOKENS.md`
- `docs/security/THREAT_MODEL_AND_CONTROLS.md`
- `docs/architecture/17_SECURITY_PRIVACY_AND_GOVERNANCE.md`
- `docs/architecture/15_FRONTEND_CLASSROOM_AND_STUDIO.md`
- `contracts/openapi/openapi.yaml`
- `contracts/security/session-claims.schema.json`
- `backend/app/identity/` (the V0-021 domain being extended)

## In Scope

- A third role, `institution_admin`, named from the canonical role list
  (`docs/ARC_OVERVIEW.md` §27 *Institution Administrator*), with the two capabilities
  it needs and nothing more: `account:read`, `account:write`. It also gets the two
  read-only oversight capabilities the permission model names ("view
  institution-wide usage"): `content:read`, `class:read`.
- An administration surface for accounts: create (teacher/student), list, read,
  update (display name, role, enabled/disabled), and remove — behind
  `account:*` capabilities, tenant-scoped.
- Disabling an account revokes its live sessions immediately; a disabled account
  cannot sign in and cannot keep using a token it already has.
- A one-shot, development-gated bootstrap for the institution's **first**
  administrator, so a fresh installation can create the account an administrator
  would otherwise have to create.
- Teacher roster management: assign an existing student to a class and unassign
  one; enrolment no longer creates accounts for a caller that cannot create them.
- The frontend: an Accounts section for the administrator, a student picker for the
  teacher's roster, a first-administrator panel on the sign-in page, and a
  role-aware nav for the third role.
- Contracts, docs, telemetry and traceability for all of the above.

## Out of Scope

- Platform administrator, IT operator, course administrator, teaching assistant,
  moderator and auditor roles: named by the specification, not modelled (inventing
  them would be inventing policy).
- Federated provisioning, group/cohort sync, SSO/SAML, password policy, multi-role
  accounts, guardians, and any bulk import.
- Self-service registration, password reset, e-mail delivery, and account
  invitations by e-mail — an administrator hands over the one-time credential the
  development adapter issues.
- Any change to the Classroom Actor, the snapshot shape, the join credential's
  claims, or the pinned-publication rule.
- A new service, broker, database or framework.

## Acceptance Criteria

| Criterion | How it is verified |
| --- | --- |
| Three roles, one session surface | Administrator, teacher and student each sign in and out; `GET /auth/me` reports the role and its capabilities; capabilities come from `ROLE_SCOPES` alone |
| An administrator manages the directory | Create/list/read/update/remove teacher and student accounts; every verb refused (`403`) for a teacher and a student |
| The administrator cannot be locked out or escalated | Only a caller holding `account:write` may write; the bootstrap exists only while no administrator does, and only on a development deployment |
| Disabling takes effect immediately | A disabled account's live session is refused (`401 ACCOUNT_DISABLED`) and a new sign-in is refused; re-enabling restores both |
| A teacher assigns, does not create | Enrolling an address this tenant has no account for is refused (`404 ACCOUNT_REQUIRED`) and **creates nothing**; enrolment never creates an account for any caller — provisioning is `POST /accounts` alone, which only an administrator holds |
| The roster can be corrected | Unassigning a student is idempotent and removes their ability to obtain a new join credential |
| Removing an account that is referenced is refused | `DELETE` on an enrolled account is `409 ACCOUNT_IN_USE`; an unreferenced account is removed with its credentials and sessions |
| The tenant boundary holds | No cross-tenant account read, write or enrolment; a token for tenant A cannot touch tenant B |
| Nothing is presented as decided | The credential adapter stays labelled a development mock; the three modelled roles are attributed to the canonical role list, and the unmodelled ones are named as unmodelled |

## Blocker

None. `FND-002` (the identity ADR) is still `TODO`, so the *mechanism* remains a
labelled development stand-in — the same position V0-021 and V0-012 took. The role
separation itself is authorization, not mechanism, and is fixed by V0-021's model.
