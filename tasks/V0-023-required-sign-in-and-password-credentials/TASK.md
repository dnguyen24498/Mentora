# V0-023: Required sign-in and password credentials

**Week:** W8  
**Status:** DONE  
**Owner:** Solo developer  
**Target:** V0

## Objective

Close the platform behind a sign-in and give every account a **password**:

- **Nothing is reachable without a session.** The pre-auth `X-Institution-Id`
  development shortcut becomes *off by default*, so every API route requires a real
  session, and every frontend page except `/login` redirects to the sign-in form.
- **A password replaces the one-time sign-in code.** An institution administrator
  sets an initial password when creating an account (and can reset it); the account
  holder signs in with it, and can **change their own password**.
- The institution's **first administrator** is still the one-shot deployment
  bootstrap, now gated on its own setting rather than on the development shortcut.

This changes *which credential a subject presents* and *who may reach a page*. It
does **not** decide the credential mechanism: the canonical model is institutional
federation, no ADR accepts an implementation (`FND-002` is `TODO`), and the local
password adapter stays a labelled development stand-in.

## Dependencies

- V0-021 (accounts, roles, sessions), V0-022 (directory, role separation, bootstrap)

## Requirement IDs

- `DEC-RUNTIME-007` (revocation is immediate; only a digest is stored)
- `DEC-RUNTIME-003` (idempotent commands: create-or-link, sign in, sign out)
- `DEC-RELIABILITY-001` (bounded work: deadline, bounded retry, terminal verdict)
- `DEC-RELIABILITY-002` (an availability failure is not a denial)
- `DEC-DATA-001` (the relational store owns institutional/account truth)
- `DEC-TURN-001` (the student's join credential stays subscribe-only)
- `DEC-CONTENT-005` (unchanged: the student still learns the pinned publication)

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `docs/security/IDENTITY_AUTHORIZATION_AND_TOKENS.md`
- `docs/architecture/15_FRONTEND_CLASSROOM_AND_STUDIO.md`
- `docs/architecture/17_SECURITY_PRIVACY_AND_GOVERNANCE.md`
- `contracts/openapi/openapi.yaml`
- `contracts/security/session-claims.schema.json`
- `backend/app/identity/`, `backend/app/providers/local_credentials.py`
- `backend/app/api/{security,identity_router,accounts_router,app}.py`

## In Scope

- **A locked-by-default platform**: `Settings.dev_tenant_header` defaults to
  `False`, so a request with only `X-Institution-Id` is `401 SESSION_REQUIRED` on
  every route. The shortcut remains available as an explicit, development-only
  opt-in (`MENTORA_DEV_TENANT_HEADER=1`).
- **A first-administrator bootstrap with its own switch**: `Settings.admin_bootstrap`
  (default on) gates `POST /auth/bootstrap-admin` independently of the tenant-header
  shortcut, so a fresh installation can still create its first account while every
  feature stays behind a sign-in.
- **Password credentials**: `POST /auth/login` takes a password; an administrator
  supplies one when creating an account (`POST /accounts`) and can reset it
  (`PATCH /accounts/{id}`); a signed-in account can change its own
  (`POST /auth/password`).
- **Setting or resetting a password revokes that account's live sessions**
  (`DEC-RUNTIME-007`); a self-service change keeps the caller's own session.
- **The frontend is behind a guard**: every page except `/login` renders the
  sign-in form until a session exists, returning to the requested page afterwards; a
  session the server has revoked or expired is dropped and the guard re-applies.
- **A change-password surface** (`Settings → Security`) and a password field on the
  admin create/reset forms.
- Contracts, docs, telemetry and traceability for all of the above.

## Out of Scope

- Any decided credential mechanism: institutional federation (OIDC/OAuth) remains
  the model and is not implemented; the adapter stays a labelled development mock.
- Password policy beyond a minimum-length guard, password reset by e-mail,
  self-service registration, multi-factor authentication, account lockout/rate
  limiting beyond the authenticator's existing admission control.
- Federated provisioning, group/cohort sync, SSO/SAML, multi-role accounts.
- Any change to the Classroom Actor, the snapshot shape, the join credential's
  claims, or the pinned-publication rule.
- A new service, broker, database or framework.

## Acceptance Criteria

| Criterion | How it is verified |
| --- | --- |
| Nothing is reachable without a sign-in | With default settings, a representative set of routes is `401 SESSION_REQUIRED` with only the tenant header; only `/auth/login`, `/auth/me` and the one-shot bootstrap answer otherwise |
| A password signs you in | The bootstrap and the directory take a password; `POST /auth/login` with it returns a session; a wrong password is `401 INVALID_CREDENTIALS` |
| An administrator sets and resets passwords | `POST /accounts` requires a password; `PATCH /accounts/{id}` resets one; both are refused (`403`) for a teacher |
| A change invalidates the old password | `POST /auth/password` sets a new one; the old password is refused and the new one works |
| A reset revokes live sessions | Setting a password revokes the account's live sessions; a self-service change keeps only the caller's own |
| The first administrator is still creatable | The bootstrap works while `admin_bootstrap` is on and the tenant has no administrator, and is `404 BOOTSTRAP_DISABLED` when off |
| The frontend locks behind the form | No session ⇒ every route renders the sign-in form; a deep link returns to its page after signing in |
| Nothing is presented as decided | The credential adapter stays labelled a development mock; federation is named as the undecided model |

## Blocker

None. `FND-002` (the identity ADR) is still `TODO`, so the *mechanism* remains a
labelled development stand-in — the same position V0-021/V0-022 and V0-012 took.
Which pages require a session, and which credential a subject presents, are
product decisions that do not depend on that ADR.
