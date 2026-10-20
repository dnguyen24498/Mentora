"""Principal resolution and capability guards for the HTTP surface (V0-021).

``docs/security/IDENTITY_AUTHORIZATION_AND_TOKENS.md``: *"Every request validates
tenant/course/class/resource."* This module is where that happens for the transport:

* :func:`build_api_security` returns an :class:`ApiSecurity` whose ``principal``
  dependency turns an ``Authorization: Bearer <token>`` header into a
  :class:`~app.identity.models.Principal`, and whose ``tenant`` dependency is
  **derived from that principal** — so every existing route keeps reading a tenant
  string while the tenant can no longer come from a request parameter.
* ``require(scope)`` is a capability guard. Guards are written against
  :class:`~app.identity.models.Scope` rather than a role string, so "a student
  cannot publish" is enforced by the *absence of a capability*, the same way a join
  credential carries ``subscribe`` only (``DEC-TURN-001``).

One thing here is deliberately a shortcut and is named as one: when
``Settings.dev_tenant_header`` is on — which **V0-023 makes off by default** — a
request with **no** session is accepted for whatever ``X-Institution-Id`` it names,
and gets a principal marked ``authenticated=False``. It exists so the V0 flows (and
their tests) keep working before an institutional-federation deployment; it is not
authentication, it cannot request a class join (there is no account behind it), and
with the default now off every route requires a real session. The one-shot
first-administrator bootstrap is gated by its own switch (``admin_bootstrap``)
rather than by this one, so a locked deployment can still create its first account.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from fastapi import Depends, Header

from app.identity.errors import (
    ISSUE_SCOPE_REQUIRED,
    ISSUE_SESSION_REQUIRED,
    ScopeDeniedError,
    SessionError,
)
from app.identity.models import Principal, Scope
from app.identity.service import IdentityService
from app.identity.telemetry import IdentityTelemetry

#: The header a client presents a session token in.
AUTHORIZATION_HEADER = "Authorization"
#: The pre-auth development header (see the module docstring).
TENANT_HEADER = "X-Institution-Id"


def bearer_token(value: Optional[str]) -> Optional[str]:
    """The token of an ``Authorization: Bearer …`` header, or ``None``.

    Anything that is not a Bearer credential is treated as no credential, so a
    malformed header cannot be half-interpreted.
    """

    if not value:
        return None
    scheme, _, token = value.partition(" ")
    if scheme.strip().lower() != "bearer":
        return None
    token = token.strip()
    return token or None


@dataclass(frozen=True)
class ApiSecurity:
    """The dependencies every router receives.

    ``tenant`` stays the shape the V0 routers already take (a zero-argument
    dependency returning the institution id) so making the tenant come from a
    principal did not require rewriting every route — it required changing what
    *produces* it.
    """

    identity: IdentityService
    principal: Callable[..., Principal]
    tenant: Callable[..., str]
    require: Callable[[Scope], Callable[..., Principal]]
    #: True when the pre-auth development header is accepted (off by default, V0-023).
    development_shortcut: bool = False
    #: True when the one-shot first-administrator bootstrap is exposed (V0-023).
    admin_bootstrap: bool = True


def build_api_security(
    identity: IdentityService,
    *,
    allow_dev_header: bool = False,
    allow_admin_bootstrap: bool = True,
    telemetry: Optional[IdentityTelemetry] = None,
) -> ApiSecurity:
    """Wire principal resolution and the capability guards for one app."""

    events = telemetry

    def principal(
        authorization: Optional[str] = Header(None, alias=AUTHORIZATION_HEADER),
        institution_id: Optional[str] = Header(None, alias=TENANT_HEADER),
    ) -> Principal:
        """The authenticated caller, or a classified ``401``.

        A session always wins: when one is presented, the tenant comes from the
        session and the header is not consulted at all, so a caller cannot widen
        what a token authorizes by naming a tenant.
        """

        token = bearer_token(authorization)
        if token is not None:
            return identity.principal_for_token(token)
        if allow_dev_header and institution_id:
            return identity.development_principal(institution_id)
        raise SessionError(
            "sign in to continue; a session is required on every route",
            issue_code=ISSUE_SESSION_REQUIRED,
        )

    def tenant(principal: Principal = Depends(principal)) -> str:
        """The tenant of the authenticated principal.

        Every repository call is scoped by this value, so deriving it here is what
        makes the tenant boundary hold for routes that never mention identity.
        """

        return principal.institution_id

    def require(scope: Scope) -> Callable[..., Principal]:
        """A dependency that refuses a principal lacking ``scope``."""

        def guard(principal: Principal = Depends(principal)) -> Principal:
            if not principal.has(scope):
                if events is not None:
                    events.record_scope_denied(
                        institution_id=principal.institution_id,
                        role=principal.role.value,
                        scope=scope.value,
                    )
                raise ScopeDeniedError(
                    f"this action requires the {scope.value} capability",
                    issue_code=ISSUE_SCOPE_REQUIRED,
                    scope=scope.value,
                )
            return principal

        return guard

    return ApiSecurity(
        identity=identity,
        principal=principal,
        tenant=tenant,
        require=require,
        development_shortcut=allow_dev_header,
        admin_bootstrap=allow_admin_bootstrap,
    )


__all__ = ["AUTHORIZATION_HEADER", "TENANT_HEADER", "ApiSecurity", "bearer_token", "build_api_security"]
