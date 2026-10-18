# Security, Privacy, and Governance

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Define trust boundaries, authorization, threats, and institutional controls.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

OIDC/OAuth users, workload identity services, short-lived least-privilege tokens, tenant/resource authorization. Threats include cross-tenant access, replay, split brain, malicious documents, prompt injection, RAG poisoning, voice misuse, leakage, and operator abuse.

Controls include sandboxing, provenance, schema validation, pre-retrieval authorization, epoch-fenced tokens, dedup, secrets/network policies, audit, data minimization, consent, residency, provider/model registry, retention/export/deletion, and incident response.

## Locked Decisions Implemented

- `DEC-CONTENT-001`
- `DEC-TURN-008`
- `DEC-DATA-005`
- `DEC-RELIABILITY-002`
- `DEC-RUNTIME-007` (V0-021: a session is honoured against its current role, and revocation is checked on every read)

## Implemented identity boundary (V0-021)

Full detail is in `docs/security/IDENTITY_AUTHORIZATION_AND_TOKENS.md`. The part
that belongs to the trust boundary:

- **The tenant is derived, never supplied.** A request's tenant comes from the
  session the API resolves; `X-Institution-Id` is the *development* shortcut
  (`MENTORA_DEV_TENANT_HEADER`, default on) and is ignored whenever a session is
  present. A caller can therefore never widen its own institution by naming one.
- **Authorization is a capability, checked at the route.** Every verb on every
  router carries `require(scope)`; `ROLE_SCOPES` is the single place a role's
  capabilities are decided. No route is protected only by its client.
- **Least privilege is enforced where it is decided.** A student session carries
  `class:read`, `scene:read` and `join` and nothing else; it cannot publish, write
  content, review, or read the roster. A join credential carries `subscribe` only
  (`DEC-TURN-001`).
- **Credentials and tokens are stored as digests.** A session stores
  `sha256(token)`; a credential stores scrypt digest + per-account salt. Neither
  raw value is retrievable after the response that issued it.
- **No enumeration oracle.** An unknown account and a wrong credential are the
  same stable code and the same timing (a dummy salt is verified either way).
- **A refusal is not a fault.** Installed-capability unavailability is `503
  AUTHENTICATION_UNAVAILABLE`; a rejected credential is `401
  AUTHENTICATION_FAILED`; a missing principal is `401 UNAUTHENTICATED`; a missing
  capability is `403 INSUFFICIENT_SCOPE`. Clients and tests can tell them apart
  (`DEC-RELIABILITY-002`).
- **The stand-in is visible.** The credential adapter is a labelled
  `DEVELOPMENT_MOCK` and says so in every response and in the client UI; the
  mechanism is not a decided technology and is not presented as one.
