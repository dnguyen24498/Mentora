"""Classified failures of identity, credentials and sessions (V0-021).

``docs/security/IDENTITY_AUTHORIZATION_AND_TOKENS.md`` requires short-lived
least-privilege tokens and validated principals, and ``DEC-RELIABILITY-001``
requires a classified failure with an explicit retryable set. So a refusal carries
a **code**, never prose a caller has to parse.

The ``issue_code`` values are the client-visible branch points (the API passes a
subclass's ``issue_code`` through the error envelope, as V0-007 established).

Five HTTP shapes are used, and the distinction is deliberate:

* **401** — there is no usable principal (no session, unknown/expired/revoked one,
  or a refused credential). ``AUTHENTICATION_FAILED`` is the *same* response for an
  unknown account and a wrong credential, so login is not an enumeration oracle.
* **403 ``INSUFFICIENT_SCOPE``** — the principal is valid but lacks the capability.
  A student calling a teacher verb lands here, and so does a teacher calling an
  administrator verb.
* **403 ``TENANT_ACCESS_DENIED``** — a cross-tenant attempt (unchanged from V0-001).
* **404** — the account (or the roster entry's account) this tenant has no record
  of. V0-022 makes one of these a *precondition* rather than an absence: a caller
  who may not create accounts is told ``ACCOUNT_REQUIRED`` when the address has no
  account here, because teaching assigns people rather than creating them.
* **409 ``CONFLICT``** — the request is well-formed but cannot apply to the current
  state: an account on a roster that cannot be removed, an address that already
  exists as another role, a first administrator who already exists. ``issue_code``
  names which.
* **503** — the credential capability itself is unusable, which is an availability
  failure rather than a denial (``DEC-RELIABILITY-002``).
"""

from __future__ import annotations

from app.common.errors import (
    AuthenticationFailedError,
    AuthenticationUnavailableError,
    ConflictError,
    InsufficientScopeError,
    NotFoundError,
    UnauthenticatedError,
)

#: No session was presented, or the presented one is not usable.
ISSUE_SESSION_REQUIRED = "SESSION_REQUIRED"
#: The presented token is unknown to this tenant (never issued, or another tenant's).
ISSUE_SESSION_UNKNOWN = "SESSION_UNKNOWN"
#: The presented token is past its bounded lifetime.
ISSUE_SESSION_EXPIRED = "SESSION_EXPIRED"
#: The presented token was terminally revoked (sign-out).
ISSUE_SESSION_REVOKED = "SESSION_REVOKED"
#: The session is valid but the account behind it is disabled.
ISSUE_ACCOUNT_DISABLED = "ACCOUNT_DISABLED"
#: The principal is authenticated but lacks the scope the verb needs.
ISSUE_SCOPE_REQUIRED = "SCOPE_REQUIRED"
#: A credential was refused (wrong credential, or no such account: same code).
ISSUE_INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
#: Credential verification did not finish inside its deadline.
ISSUE_AUTHENTICATION_TIMEOUT = "AUTHENTICATION_TIMEOUT"
#: The credential capability is unusable (breaker open, no adapter configured).
ISSUE_AUTHENTICATION_UNAVAILABLE = "AUTHENTICATION_UNAVAILABLE"
#: An invitation names an email that already belongs to another role.
ISSUE_EMAIL_ROLE_CONFLICT = "EMAIL_ROLE_CONFLICT"
#: V0-022: the address has no account in this tenant and the caller may not create
#: one. A teacher assigns students; an administrator creates them.
ISSUE_ACCOUNT_REQUIRED = "ACCOUNT_REQUIRED"
#: V0-022: the account is referenced (it is on a class roster) and cannot be removed.
#: Deactivate it instead — a removal would orphan the roster and the audit trail.
ISSUE_ACCOUNT_IN_USE = "ACCOUNT_IN_USE"
#: V0-022: the role is not one this surface manages (an administrator account is
#: provisioned by the deployment bootstrap or, in a federated deployment, by the
#: identity provider — never created by another administrator here).
ISSUE_ROLE_NOT_MANAGEABLE = "ROLE_NOT_MANAGEABLE"
#: V0-022: this tenant already has an administrator, so the one-shot bootstrap is closed.
ISSUE_TENANT_ALREADY_PROVISIONED = "TENANT_ALREADY_PROVISIONED"
#: V0-022: the first-administrator bootstrap is not exposed on this deployment
#: (the development shortcut is off), so the route is absent rather than denied.
ISSUE_BOOTSTRAP_DISABLED = "BOOTSTRAP_DISABLED"

#: Only these may be retried (``DEC-RELIABILITY-001``). A refusal is never in this
#: set: retrying a wrong credential would be a brute-force amplifier.
RETRYABLE_IDENTITY_CODES = frozenset(
    {ISSUE_AUTHENTICATION_UNAVAILABLE, ISSUE_AUTHENTICATION_TIMEOUT}
)


class SessionError(UnauthenticatedError):
    """The session presented cannot authorize this request."""

    def __init__(
        self,
        message: str,
        *,
        issue_code: str = ISSUE_SESSION_REQUIRED,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.issue_code = issue_code
        #: Which principal/tenant was tried, for telemetry — never returned to
        #: the caller beyond the envelope.
        self.detail = detail


class ScopeDeniedError(InsufficientScopeError):
    """The principal is valid but lacks the scope the verb requires."""

    def __init__(
        self,
        message: str,
        *,
        issue_code: str = ISSUE_SCOPE_REQUIRED,
        scope: str | None = None,
    ) -> None:
        super().__init__(message)
        self.issue_code = issue_code
        #: The capability that was missing, so the client can explain *why*.
        self.scope = scope


class CredentialDeniedError(AuthenticationFailedError):
    """Credential verification was refused (identical for both refusal causes)."""

    def __init__(self, message: str, *, issue_code: str = ISSUE_INVALID_CREDENTIALS) -> None:
        super().__init__(message)
        self.issue_code = issue_code


class CredentialUnavailableError(AuthenticationUnavailableError):
    """The credential capability is unusable, or overran its deadline.

    ``retryable`` is what the :class:`~app.identity.port.Authenticator` template
    consults: a transient failure is retried inside the deadline, anything else is
    terminal. Classify a vendor error into one of these before raising it, so no
    vendor type reaches the domain.
    """

    def __init__(
        self,
        message: str,
        *,
        issue_code: str = ISSUE_AUTHENTICATION_UNAVAILABLE,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.issue_code = issue_code
        self.retryable = (
            issue_code in RETRYABLE_IDENTITY_CODES if retryable is None else retryable
        )


class InvitationConflictError(ConflictError):
    """An invitation names an account that already exists with another role.

    Refused rather than silently promoted: changing what an existing account *is*
    is an administrative decision, not a side effect of adding someone to a class.
    """

    def __init__(
        self, message: str, *, issue_code: str = ISSUE_EMAIL_ROLE_CONFLICT
    ) -> None:
        super().__init__(message)
        self.issue_code = issue_code


class AccountRequiredError(NotFoundError):
    """The address has no account here, and this caller may not create one (V0-022).

    A **precondition**, not an absence: the caller is allowed to enrol students, so
    the refusal names what is missing rather than pretending the request was wrong.
    Nothing is written — the teacher's request creates no account.
    """

    def __init__(
        self, message: str, *, issue_code: str = ISSUE_ACCOUNT_REQUIRED
    ) -> None:
        super().__init__(message)
        self.issue_code = issue_code


class AccountInUseError(ConflictError):
    """The account is referenced by a class roster, so it is deactivated, not removed."""

    def __init__(self, message: str, *, issue_code: str = ISSUE_ACCOUNT_IN_USE) -> None:
        super().__init__(message)
        self.issue_code = issue_code


class RoleNotManageableError(ConflictError):
    """The role is not one this surface manages."""

    def __init__(
        self, message: str, *, issue_code: str = ISSUE_ROLE_NOT_MANAGEABLE
    ) -> None:
        super().__init__(message)
        self.issue_code = issue_code


class BootstrapClosedError(ConflictError):
    """The one-shot first-administrator bootstrap is closed for this tenant."""

    def __init__(
        self, message: str, *, issue_code: str = ISSUE_TENANT_ALREADY_PROVISIONED
    ) -> None:
        super().__init__(message)
        self.issue_code = issue_code


class BootstrapDisabledError(NotFoundError):
    """This deployment does not expose the first-administrator bootstrap.

    A 404 rather than a 403: the capability is *absent* from a hardened deployment
    (federation owns provisioning), and it is reported with its own ``issue_code``
    so a client can tell "not here" apart from "no such tenant".
    """

    def __init__(
        self, message: str, *, issue_code: str = ISSUE_BOOTSTRAP_DISABLED
    ) -> None:
        super().__init__(message)
        self.issue_code = issue_code


__all__ = [
    "ISSUE_ACCOUNT_DISABLED",
    "ISSUE_ACCOUNT_IN_USE",
    "ISSUE_ACCOUNT_REQUIRED",
    "ISSUE_AUTHENTICATION_TIMEOUT",
    "ISSUE_AUTHENTICATION_UNAVAILABLE",
    "ISSUE_BOOTSTRAP_DISABLED",
    "ISSUE_EMAIL_ROLE_CONFLICT",
    "ISSUE_INVALID_CREDENTIALS",
    "ISSUE_ROLE_NOT_MANAGEABLE",
    "ISSUE_SCOPE_REQUIRED",
    "ISSUE_SESSION_EXPIRED",
    "ISSUE_SESSION_REQUIRED",
    "ISSUE_SESSION_REVOKED",
    "ISSUE_SESSION_UNKNOWN",
    "ISSUE_TENANT_ALREADY_PROVISIONED",
    "RETRYABLE_IDENTITY_CODES",
    "AccountInUseError",
    "AccountRequiredError",
    "BootstrapClosedError",
    "BootstrapDisabledError",
    "CredentialDeniedError",
    "CredentialUnavailableError",
    "InvitationConflictError",
    "RoleNotManageableError",
    "ScopeDeniedError",
    "SessionError",
]
