-- PostgreSQL reference implementation of the V0-021 identity tables.
-- Technology decision remains governed by ADR (DEC-DATA-001: "PostgreSQL or
-- equivalent durable relational store"); SQLite is the V0 local/dev equivalent
-- (backend/app/db/schema.sql) and the repository layer targets both.
--
-- What is architecture here, and what is not:
--
-- * the *authorization* model is decided — docs/security/
--   IDENTITY_AUTHORIZATION_AND_TOKENS.md: "Users authenticate through institutional
--   federation; services use workload identity. Roles: ... teacher ... student ...
--   Every request validates tenant/course/class/resource." So `accounts` (one
--   person, one institution, one role) and `auth_sessions` (short-lived,
--   least-privilege, digest-only) are architecture.
-- * the *authentication mechanism* is NOT decided: no ADR accepts one (FND-002 is
--   TODO) and the canonical architecture names OIDC/OAuth. `account_credentials`
--   therefore belongs to the local development adapter and is not a platform
--   decision — a federation deployment does not use this table at all.
--
-- Only a digest is stored for a session token (sha256) and for a credential
-- (scrypt + per-account salt), so neither a database read nor a backup yields a
-- usable bearer token or secret. This mirrors bootstrap_tokens, where
-- DEC-RUNTIME-007 requires digest-only storage.

CREATE TABLE accounts (
    account_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    institution_id uuid NOT NULL REFERENCES institutions(institution_id),
    email          varchar(320) NOT NULL,
    display_name   varchar(512) NOT NULL,
    role           varchar(64) NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),
    disabled_at    timestamptz,
    CONSTRAINT accounts_email_per_tenant UNIQUE (institution_id, email)
);
CREATE INDEX idx_accounts_tenant_role ON accounts(institution_id, role);

-- Owned by the authenticator adapter, not by the domain: how a credential is
-- represented is the authentication mechanism's business, and that mechanism is
-- OPEN. A federation deployment replaces this table with the identity provider.
CREATE TABLE account_credentials (
    account_id     uuid PRIMARY KEY REFERENCES accounts(account_id) ON DELETE CASCADE,
    institution_id uuid NOT NULL,
    algorithm      varchar(64) NOT NULL,
    salt           varchar(128) NOT NULL,
    digest         varchar(256) NOT NULL,
    updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE auth_sessions (
    session_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    institution_id uuid NOT NULL,
    account_id     uuid NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
    token_sha256   char(64) NOT NULL UNIQUE,
    scopes         text NOT NULL,
    issued_at      timestamptz NOT NULL DEFAULT now(),
    expires_at     timestamptz NOT NULL,
    revoked_at     timestamptz
);
CREATE INDEX idx_auth_sessions_tenant_account ON auth_sessions(institution_id, account_id);
-- Revocation and expiry are the two authorization reads on the hot path, so they
-- are indexed; an expired session is refused rather than deleted, so the row keeps
-- saying when it was valid.
CREATE INDEX idx_auth_sessions_live ON auth_sessions(token_sha256) WHERE revoked_at IS NULL;
