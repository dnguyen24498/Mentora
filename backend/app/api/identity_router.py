"""The authentication surface: sign in, sign out, who am I (V0-021).

Routes (``contracts/openapi/openapi.yaml``):

* ``POST /auth/login`` — present a credential for a subject in a tenant; on success
  a short-lived session token is returned **once** (only its digest is stored).
* ``POST /auth/logout`` — revoke the presented session. Idempotent, and deliberately
  usable with an already-expired token, because signing out must never fail.
* ``GET  /auth/me`` — the principal the presented session authorizes.
* ``POST /auth/bootstrap-admin`` — the deployment's one-shot creation of the
  institution's **first** administrator (V0-022). It is unauthenticated by
  necessity (there is no administrator yet to authorize it), it exists only while
  the development shortcut is enabled, and it closes the moment the tenant has an
  administrator. Under institutional federation the identity provider provisions
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

    ``credential`` is opaque to the API: a development sign-in code today, an
    authorization-code result or an assertion once federation is decided.
    """

    institution_id: str = Field(min_length=1, max_length=256)
    email: str = Field(min_length=1, max_length=320)
    credential: str = Field(min_length=1, max_length=1024)


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
            payload.institution_id, payload.email, payload.credential
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

    @router.post("/auth/bootstrap-admin", status_code=201)
    def bootstrap_admin(
        institution_id: str,
        email: str,
        display_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create the institution's first administrator — once, in development.

        Refused with ``404 BOOTSTRAP_DISABLED`` when the deployment has the
        development shortcut off (institutional federation owns provisioning there,
        so the route is *absent* rather than denied), and with ``409`` once the
        tenant already has an administrator. It writes nothing when it refuses.
        """

        if not security.development_shortcut:
            raise BootstrapDisabledError(
                "this deployment does not expose the first-administrator bootstrap; "
                "an administrator is provisioned by the institution's identity provider"
            )
        mutation = identity.bootstrap_administrator(
            institution_id, email=email, display_name=display_name or ""
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
        }

    return router
