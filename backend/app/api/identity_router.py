"""The authentication surface: sign in, sign out, who am I (V0-021).

Routes (``contracts/openapi/openapi.yaml``):

* ``POST /auth/login`` — present a password for a subject in a tenant; on success a
  short-lived session token is returned **once** (only its digest is stored).
* ``POST /auth/logout`` — revoke the presented session. Idempotent, and deliberately
  usable with an already-expired token, because signing out must never fail.
* ``POST /auth/password`` — change the presented account's own password (V0-023).
* ``GET  /auth/me`` — the principal the presented session authorizes.
* ``POST /auth/bootstrap-admin`` — the deployment's one-shot creation of the
  institution's **first** administrator (V0-022). It is unauthenticated by
  necessity (there is no administrator yet to authorize it), it is exposed only
  while ``Settings.admin_bootstrap`` is on, and it closes the moment the tenant has
  an administrator. Under institutional federation the identity provider provisions
  that account, which is why this route is a development seam and not the platform's
  account-creation path.

Two honesty requirements shape the responses:

* the **credential capability** is reported (``local-credentials@1.0.0``,
  ``kind: DEVELOPMENT_MOCK``), so a client can see that the mechanism is a mock
  standing in for the undecided institutional federation, rather than presenting it
  as the platform's authentication;
* a request with no session that was admitted by the development tenant shortcut
  reports ``authenticated: false``. The client can then say "development mode"
  instead of pretending the user is signed in.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from app.api.security import AUTHORIZATION_HEADER, ApiSecurity, bearer_token
from app.identity.errors import (
    ISSUE_ACCOUNT_DISABLED,
    ISSUE_INVALID_CREDENTIALS,
    RETRYABLE_IDENTITY_CODES,
    BootstrapDisabledError,
    CredentialDeniedError,
    CredentialUnavailableError,
)
from app.identity.models import Principal


class LoginRequest(BaseModel):
    """A subject proving it is an account in a tenant.

    ``password`` is the credential for the development adapter; the port keeps it
    opaque, so an authorization-code result or an assertion takes its place once
    federation is decided.
    """

    institution_id: str = Field(min_length=1, max_length=256)
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class PasswordChangeRequest(BaseModel):
    """A signed-in account changing its own password (V0-023)."""

    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=1, max_length=1024)


class BootstrapRequest(BaseModel):
    """The deployment's first administrator (V0-023).

    A **body**, like every other request that carries a password: a password in a
    URL would be written to access logs and browser history.
    """

    institution_id: str = Field(min_length=1, max_length=256)
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=1024)
    display_name: Optional[str] = Field(default=None, max_length=256)


def _notice(identity: dict[str, Any]) -> str:
    """A sentence a client may show verbatim about *which* mechanism answered."""

    if identity.get("kind") == "DEVELOPMENT_MOCK":
        return (
            "Signed in through the local development credential mock "
            f"({identity.get('id')}). Institutional federation (OIDC/OAuth) is not "
            "decided yet, so this adapter is a stand-in, not the platform's "
            "authentication."
        )
    return f"Signed in through {identity.get('id')}."


def build_identity_router(security: ApiSecurity) -> APIRouter:
    router = APIRouter(tags=["identity"])
    identity = security.identity
    capability = identity.authenticator_identity

    @router.post("/auth/login")
    def login(payload: LoginRequest) -> dict[str, Any]:
        """Sign in. A refusal is a stable code, never prose to parse."""

        result = identity.login(
            payload.institution_id, payload.email, payload.password
        )
        if not result.authenticated:
            code = result.error_code or ""
            if code in RETRYABLE_IDENTITY_CODES:
                # An availability failure is not a denial (DEC-RELIABILITY-002).
                raise CredentialUnavailableError(result.message, issue_code=code)
            if code == ISSUE_ACCOUNT_DISABLED:
                raise CredentialDeniedError(
                    "this account is not usable", issue_code=ISSUE_ACCOUNT_DISABLED
                )
            raise CredentialDeniedError(
                result.message or "credentials were not accepted",
                issue_code=code or ISSUE_INVALID_CREDENTIALS,
            )

        return {
            **result.to_dict(),
            "authenticator": capability,
            "notice": _notice(capability),
        }

    @router.post("/auth/password")
    def change_password(
        payload: PasswordChangeRequest,
        principal: Principal = Depends(security.principal),
    ) -> dict[str, Any]:
        """Change the presented account's own password (V0-023).

        A wrong current password is refused exactly as a refused sign-in is
        (``401 AUTHENTICATION_FAILED``/``INVALID_CREDENTIALS``) — the *session* is
        still valid, which is why the client keeps it. On success every other live
        session of the account is revoked, so the old password cannot keep a stale tab
        working; the caller's own session is deliberately spared.
        """

        revoked = identity.change_password(
            principal.institution_id,
            principal.account_id or "",
            current_secret=payload.current_password,
            new_secret=payload.new_password,
            keep_session_id=principal.session_id,
        )
        return {"changed": True, "sessions_revoked": revoked}

    @router.post("/auth/bootstrap-admin", status_code=201)
    def bootstrap_admin(payload: BootstrapRequest) -> dict[str, Any]:
        """Create the institution's first administrator — once.

        Refused with ``404 BOOTSTRAP_DISABLED`` when the deployment does not expose
        the bootstrap (institutional federation owns provisioning there, so the route
        is *absent* rather than denied), and with ``409`` once the tenant already has
        an administrator. It writes nothing when it refuses.
        """

        if not security.admin_bootstrap:
            raise BootstrapDisabledError(
                "this deployment does not expose the first-administrator bootstrap; "
                "an administrator is provisioned by the institution's identity provider"
            )
        mutation = identity.bootstrap_administrator(
            payload.institution_id,
            email=payload.email,
            secret=payload.password,
            display_name=payload.display_name or "",
        )
        return mutation.to_dict()

    @router.post("/auth/logout")
    def logout(
        authorization: Optional[str] = Header(None, alias=AUTHORIZATION_HEADER),
    ) -> dict[str, Any]:
        """Revoke the presented session. Never fails, and never leaks a token."""

        revoked = identity.sign_out(bearer_token(authorization))
        return {"revoked": revoked}

    @router.get("/auth/me")
    def me(principal: Principal = Depends(security.principal)) -> dict[str, Any]:
        """The principal the presented session authorizes.

        Requiring a principal means this route answers ``401`` with a named cause
        rather than an empty document, so a client can distinguish "not signed in"
        from "signed in".
        """

        return {
            "principal": principal.to_dict(),
            "authenticator": capability,
            "notice": _notice(capability),
            "development_shortcut": security.development_shortcut,
            "admin_bootstrap": security.admin_bootstrap,
        }

    return router
