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

## Implemented identities and authorization (V0-021)

Implemented in `backend/app/identity/` (the domain), `backend/app/providers/local_credentials.py` (the one registered credential adapter) and `backend/app/api/security.py` (the request-time enforcement). The frontend half is `frontend/src/auth/`.

**The credential mechanism is NOT a decided technology.** The paragraph above — institutional federation — is the canonical requirement; every entry in `governance/DECISION_LEDGER.yaml` about an identity provider, token format or federation protocol is `OPEN`/`PROPOSED`, and no ADR accepts one. `FND-002` is still `TODO`. So, exactly as with the voice capability (`DEC-TECH-007`) and the renderer (`DEC-TECH-005`), the implementation is the **provider-neutral interface plus an explicitly-labelled stand-in**, and the stand-in says so in the response (`authenticator.kind: DEVELOPMENT_MOCK`) and in `GET /auth/me`. Nothing here may be presented as the platform's authentication.

The seam is `app/identity/port.py::Authenticator` — `authenticate(institution_id, email, credential) -> AuthenticatedSubject | None`, `provision(...) -> IssuedCredential | None`, plus an `identity` property naming the capability. An OIDC/OAuth adapter is a second implementation of that ABC; no domain code changes when it arrives (the adapter depends on the port, never the reverse, enforced by the same layering rule the speech domain uses). The registered adapter is `local-credentials@1.0.0` (`app/providers/factory.py::create_authenticator`): stdlib `hashlib.scrypt` with a per-account random salt, **digest-only** storage, and a constant dummy-salt verification on an unknown address so a missing account and a wrong credential take the same time and are indistinguishable. It issues a one-time sign-in code (`provision`) because federation would not — that is the one behaviour a federation adapter would remove, which is why the API returns it as an explicitly named `development_credential`.

**The tenant is a session claim, never a request field.** `POST /auth/login` resolves the account in the institution named in its **body** (that is what the credential proves); every later request derives `institution_id` from the session `app/api/security.py` resolves, and the API ignores `X-Institution-Id` when a session is present. A session therefore cannot be widened by anything a caller names. Only the token's SHA-256 digest is stored (`auth_sessions.token_sha256`); the raw token exists once, in the login response. Claims and their invariants are contracted in `contracts/security/session-claims.schema.json`.

**Capabilities, not role names.** `Scope` (`app/identity/models.py`) is the unit of authorization and `ROLE_SCOPES` is the single place a role's capabilities are decided, so a role can never accumulate a capability because an endpoint forgot to check. Guards are written against a *missing capability* (`app/api/security.py::require(scope)`), and every route verb on every router carries one. A request without a principal is `401 UNAUTHENTICATED` (`issue_code SESSION_REQUIRED`); a principal without the scope is `403 INSUFFICIENT_SCOPE` (`issue_code SCOPE_REQUIRED`) — both stable codes, distinct from `AUTHENTICATION_FAILED` (`401`, a credential the mechanism rejected) and `AUTHENTICATION_UNAVAILABLE` (`503`, the capability could not be reached — an availability failure, never a denial, `DEC-RELIABILITY-002`).

**Session scopes are re-derived, not remembered.** A session row stores the scopes it was issued with and every read **intersects** them with what the account's role currently grants. Narrowing a role therefore takes effect on the account's next request rather than at session expiry, and revoking a session is a `revoked_at` write the same read honours (`DEC-RUNTIME-007`). The intersection can only ever *remove*: widening a role takes effect on the account's next sign-in, because a role edit must never retroactively hand a live session a capability it was never issued.

Two roles are modelled: `teacher` and `student`. The spec's wider list (institution admin, IT operator, moderator, auditor) is **not** modelled in V0, and the enum in the session-claims schema says so rather than implying it exists. `student` is exactly *"attend the class"*: `class:read`, `scene:read`, `join` — nothing that writes. A student on a teacher verb is refused by the guard, not by a page choosing to hide a button.

The reciprocal also holds, as a capability rather than a role test: `join` is the **participant** capability, so it belongs to the student role alone and a teacher holds none. That is "a teacher token is refused where student identity is required" in practice — a teacher principal asking for a join credential is refused `403 INSUFFICIENT_SCOPE` (`SCOPE_REQUIRED`) at the guard, before any class is read. A teacher's access to a class is the classroom session (`class:read` plus the Actor), not a seat in it.

**Enrolment is the class-scoped authorization.** A join is authorized by the *pair*: the class is `ACTIVE` **and** the caller's own account is enrolled in it, in the caller's own tenant (`403 NOT_ENROLLED` otherwise; a class of another institution is `TENANT_ACCESS_DENIED`). `POST /classes/{id}/bootstrap-token` takes **no body** — there is no student id in the request, so the credential is bound to the session's account and a caller cannot ask for someone else's join. It carries `subscribe` scope only (`DEC-TURN-001`) and binds class/student/session/`actor_epoch`/nonce/expiry (`DEC-RUNTIME-007`). Only its SHA-256 digest is stored. The roster is other people's identities, so *listing* it is a teacher capability (`enrollment:write`); a student's own enrolment is reported by the join check and `GET /classes/{id}`, never by the roster list.

**What the class is shown is what it pinned.** `GET /classes/{id}/scenes` and `GET /classes/{id}/scenes/{order}` resolve the session's own `RuntimeSessionPlan` — never the course's current publication — so a correction published mid-lesson changes nothing a student sees (`DEC-CONTENT-005`). The render is served **through the package manifest** (a path the manifest does not list is not readable, so this cannot become an arbitrary object read) and every served file is re-checked against the digest the manifest recorded: a file swapped in storage is refused with `502 STORAGE_FAILURE` (`issue_code SCENE_CHECKSUM_MISMATCH`) rather than presented. A request that has no session reads nothing.

**The development tenant shortcut, and its limit.** `Settings.dev_tenant_header` (`MENTORA_DEV_TENANT_HEADER`, default on) keeps the V0 authoring flows usable before federation exists: with no session and a valid `X-Institution-Id`, a request resolves a **teacher** principal marked `authenticated: false` with **no account**. It is reported as such by `GET /auth/me` (and rendered as "Development mode", never as a user) rather than being smoothed over. It cannot join a class — not because a header is not a session, but because it *is a teacher*, and `join` is the student's participant capability: the guard refuses it `403 INSUFFICIENT_SCOPE` before the class is read. (Having no account is a second, independent reason: a join credential binds to the authenticated student's own account.) Switching the flag off makes every route require a real session, and the client reports that too — it asks `GET /auth/me` instead of assuming.

## Requirement Trace

- `DEC-TURN-003`
- `DEC-TURN-008`
- `DEC-RUNTIME-007` (implementation: epoch fencing on the join credential and on session revocation)
- `DEC-CONTENT-005` (implementation: a class reads the package it pinned)
- `DEC-RELIABILITY-002` (implementation: an unavailable credential capability is `503`, never a denial)
