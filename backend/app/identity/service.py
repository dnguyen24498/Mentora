"""The identity service: log in, prove a session, sign out, invite (V0-021).

Three responsibilities, deliberately kept apart:

* :meth:`IdentityService.login` verifies a credential through the replaceable
  :class:`~app.identity.port.Authenticator`, then mints a **short-lived,
  least-privilege** session (``docs/security/IDENTITY_AUTHORIZATION_AND_TOKENS.md``).
  It **never raises**: a refusal is a :class:`LoginResult`, because a login is a
  control-plane call on the lesson's critical path and "cannot sign in right now"
  must be an answer, not a 500.
* :meth:`IdentityService.principal_for_token` turns a presented token into a
  :class:`Principal`. This one *does* raise, and that is intentional: it is a
  deterministic local validation whose failure the transport must turn into a
  specific ``401``, in the same way ``ClassRepository.get_class`` raises rather than
  returning ``None`` (V0-009).
* :meth:`IdentityService.invite_student` creates-or-links a student account and
  returns the account plus, for the development mock only, a one-time credential.

The tenant always comes from the **session**, never from the request: a caller
cannot address another institution's data by naming it, and the token is the only
thing that decides whose data it is.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from app.common.errors import ValidationError
from app.config import DEFAULT_SESSION_TTL_SECONDS
from app.identity.errors import (
    ISSUE_ACCOUNT_DISABLED,
    ISSUE_SESSION_EXPIRED,
    ISSUE_SESSION_REQUIRED,
    ISSUE_SESSION_REVOKED,
    ISSUE_SESSION_UNKNOWN,
    InvitationConflictError,
    SessionError,
)
from app.identity.models import (
    Account,
    AuthSession,
    InvitedAccount,
    IssuedSession,
    Principal,
    Role,
    Scope,
    hash_token,
    scopes_for,
)
from app.identity.port import (
    AuthenticationOutcome,
    AuthenticationRequest,
    Authenticator,
)
from app.identity.repository import IdentityRepository, normalize_email
from app.identity.telemetry import IdentityTelemetry


@dataclass(frozen=True)
class LoginResult:
    """The outcome of a login attempt. Never an exception."""

    issuance: Optional[IssuedSession] = None
    error_code: Optional[str] = None
    message: str = ""
    outcome: Optional[AuthenticationOutcome] = None

    @property
    def authenticated(self) -> bool:
        return self.issuance is not None

    def to_dict(self) -> dict[str, Any]:
        if self.issuance is not None:
            return {"authenticated": True, **self.issuance.to_dict()}
        return {"authenticated": False, "error_code": self.error_code}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IdentityService:
    def __init__(
        self,
        repository: IdentityRepository,
        authenticator: Authenticator,
        *,
        telemetry: Optional[IdentityTelemetry] = None,
        session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
        clock: Callable[[], datetime] = _utcnow,
        monotonic: Optional[Callable[[], float]] = None,
    ) -> None:
        self._repository = repository
        self._authenticator = authenticator
        self._telemetry = telemetry or IdentityTelemetry()
        self._session_ttl_seconds = session_ttl_seconds
        self._clock = clock
        # The authenticator's deadline uses a monotonic clock; tests inject both so
        # a timeout is deterministic rather than wall-clock dependent.
        self._monotonic = monotonic

    # -- capability identity -----------------------------------------------------------
    @property
    def telemetry(self) -> IdentityTelemetry:
        return self._telemetry

    @property
    def authenticator_identity(self) -> dict[str, Any]:
        """Which credential capability is wired, and whether it is a mock."""

        return self._authenticator.identity.to_dict()

    def health(self) -> dict[str, Any]:
        return self._authenticator.health().to_dict()

    # -- login -------------------------------------------------------------------------
    def login(self, institution_id: str, subject: str, credential: str) -> LoginResult:
        """Verify a credential and, on success, mint a session. Never raises."""

        request = AuthenticationRequest(
            institution_id=institution_id, subject=subject, credential=credential
        )
        if self._monotonic is None:
            outcome = self._authenticator.authenticate(request, self._repository.resolve_subject)
        else:
            outcome = self._authenticator.authenticate(
                request, self._repository.resolve_subject, clock=self._monotonic
            )

        if not outcome.authenticated:
            self._telemetry.record_login(
                institution_id=institution_id,
                subject=subject,
                authenticated=False,
                error_code=outcome.error_code,
                attempts=outcome.attempts,
                duration_ms=outcome.duration_ms,
                authenticator=self._authenticator.identity.id,
            )
            # The message is deliberately generic: the same words for "no such
            # account" and "wrong credential", so the response cannot be used to
            # discover which accounts exist.
            return LoginResult(
                error_code=outcome.error_code,
                message="credentials were not accepted",
                outcome=outcome,
            )

        account = self._repository.find_account_by_email(institution_id, subject)
        if account is None or not account.is_active:
            self._telemetry.record_login(
                institution_id=institution_id,
                subject=subject,
                authenticated=False,
                error_code=ISSUE_ACCOUNT_DISABLED,
                attempts=outcome.attempts,
                duration_ms=outcome.duration_ms,
                authenticator=self._authenticator.identity.id,
            )
            return LoginResult(
                error_code=ISSUE_ACCOUNT_DISABLED,
                message="credentials were not accepted",
                outcome=outcome,
            )

        session, raw_token = self._mint_session(account)
        self._telemetry.record_login(
            institution_id=institution_id,
            subject=subject,
            authenticated=True,
            error_code=None,
            attempts=outcome.attempts,
            duration_ms=outcome.duration_ms,
            authenticator=self._authenticator.identity.id,
            role=account.role.value,
        )
        return LoginResult(
            issuance=IssuedSession(
                session=session,
                raw_token=raw_token,
                principal=self._principal(session, account),
            )
        )

    def _mint_session(self, account: Account) -> tuple[AuthSession, str]:
        """Issue a session for an account. Only the digest is stored."""

        raw_token = secrets.token_urlsafe(32)
        issued = self._clock()
        session = self._repository.create_session(
            institution_id=account.institution_id,
            account_id=account.account_id,
            token_sha256=hash_token(raw_token),
            scopes=scopes_for(account.role),
            issued_at=issued.isoformat(),
            expires_at=(issued + timedelta(seconds=self._session_ttl_seconds)).isoformat(),
        )
        return session, raw_token

    # -- session verification ----------------------------------------------------------
    def principal_for_token(self, raw_token: Optional[str]) -> Principal:
        """The principal a presented bearer token authorizes, or a classified refusal.

        The token is looked up by digest **without** a tenant filter, because the
        tenant is a property of the session rather than of the request.
        """

        token = (raw_token or "").strip()
        if not token:
            self._refused(None, ISSUE_SESSION_REQUIRED)
            raise SessionError("no session was presented", issue_code=ISSUE_SESSION_REQUIRED)

        session = self._repository.find_session(hash_token(token))
        if session is None:
            self._refused(None, ISSUE_SESSION_UNKNOWN)
            raise SessionError("session is not valid", issue_code=ISSUE_SESSION_UNKNOWN)
        if session.revoked_at is not None:
            self._refused(session.institution_id, ISSUE_SESSION_REVOKED)
            raise SessionError("session was revoked", issue_code=ISSUE_SESSION_REVOKED)
        if self._expired(session):
            self._refused(session.institution_id, ISSUE_SESSION_EXPIRED)
            raise SessionError("session expired", issue_code=ISSUE_SESSION_EXPIRED)

        account = self._repository.find_account(session.institution_id, session.account_id)
        if account is None or not account.is_active:
            self._refused(session.institution_id, ISSUE_ACCOUNT_DISABLED)
            raise SessionError(
                "the account behind this session is not usable",
                issue_code=ISSUE_ACCOUNT_DISABLED,
            )
        return self._principal(session, account)

    def _expired(self, session: AuthSession) -> bool:
        expires = _parse_instant(session.expires_at)
        return expires is None or expires <= self._clock()

    def _refused(self, institution_id: Optional[str], issue_code: str) -> None:
        self._telemetry.record_session_refused(
            institution_id=institution_id, issue_code=issue_code
        )

    def _principal(self, session: AuthSession, account: Account) -> Principal:
        """A principal whose capabilities cannot exceed the account's current role.

        Stored scopes are *intersected* with the role's scopes, so narrowing a
        role takes effect on the next request instead of waiting for the session to
        expire — least privilege held to, not assumed.
        """

        allowed = set(scopes_for(account.role))
        return Principal(
            institution_id=account.institution_id,
            role=account.role,
            scopes=tuple(scope for scope in session.scopes if scope in allowed),
            account_id=account.account_id,
            email=account.email,
            display_name=account.display_name,
            session_id=session.session_id,
            expires_at=session.expires_at,
            authenticated=True,
        )

    # -- sign out ----------------------------------------------------------------------
    def sign_out(self, raw_token: Optional[str]) -> bool:
        """Revoke a session. Idempotent: a replay revokes nothing and is not an error."""

        token = (raw_token or "").strip()
        if not token:
            return False
        digest = hash_token(token)
        session = self._repository.find_session(digest)
        revoked = self._repository.revoke_session(digest)
        self._telemetry.record_sign_out(
            institution_id=session.institution_id if session is not None else "unknown",
            revoked=revoked,
        )
        return revoked

    # -- accounts ----------------------------------------------------------------------
    def account(self, institution_id: str, account_id: str) -> Account:
        return self._repository.get_account(institution_id, account_id)

    def find_account(self, institution_id: str, account_id: str) -> Optional[Account]:
        """One account of this tenant, or ``None`` when there is no such account."""

        return self._repository.find_account(institution_id, account_id)

    def list_students(self, institution_id: str) -> list[Account]:
        """The tenant's student accounts, for a roster picker."""

        return self._repository.list_accounts(institution_id, role=Role.STUDENT)

    def invite_student(
        self,
        institution_id: str,
        email: str,
        display_name: str = "",
        *,
        class_id: Optional[str] = None,
    ) -> InvitedAccount:
        """Create-or-link a student account for ``email`` in this tenant.

        **Create-or-link, not create**: inviting the same address twice is one
        account, so a retried invitation is not an error (``DEC-RUNTIME-003``) and a
        student who was invited to two classes has one identity, not two.

        ``development_credential`` is populated **only** by a credential-issuing
        adapter. Institutional federation does not need it — the identity provider
        owns the credential — so with a federation adapter in place this is ``None``
        and an invitation grants no local secret at all.
        """

        subject = normalize_email(email)
        if "@" not in subject or any(char.isspace() for char in subject):
            raise ValidationError("a valid email address is required")

        existing = self._repository.find_account_by_email(institution_id, subject)
        if existing is not None:
            if existing.role is not Role.STUDENT:
                raise InvitationConflictError(
                    f"{subject!r} already exists in this institution as a "
                    f"{existing.role.value}; an invitation cannot change a role"
                )
            self._telemetry.record_invitation(
                institution_id=institution_id,
                class_id=class_id or "",
                subject=subject,
                created=False,
                credential_issued=False,
                role=existing.role.value,
            )
            return InvitedAccount(account=existing, created=False)

        account = self._repository.create_account(
            institution_id=institution_id,
            email=subject,
            display_name=display_name or subject,
            role=Role.STUDENT,
        )
        credential = self._authenticator.issue_credential(institution_id, account.account_id)
        self._telemetry.record_invitation(
            institution_id=institution_id,
            class_id=class_id or "",
            subject=subject,
            created=True,
            credential_issued=credential is not None,
            role=account.role.value,
        )
        return InvitedAccount(
            account=account,
            development_credential=credential,
            created=True,
        )

    # -- the pre-auth development shortcut ---------------------------------------------
    def development_principal(self, institution_id: str) -> Principal:
        """The **pre-auth development** principal for one tenant.

        This is not authentication. It exists so the V0 flows (and their tests) keep
        working before an institutional-federation deployment replaces the
        ``X-Institution-Id`` header, and it is only ever produced when
        ``Settings.dev_tenant_header`` allows it. ``authenticated=False`` travels in
        ``GET /auth/me`` so no client can mistake it for a signed-in user, and there
        is no account behind it — which is why it cannot request a class join.
        """

        return Principal(
            institution_id=institution_id,
            role=Role.TEACHER,
            scopes=scopes_for(Role.TEACHER),
            authenticated=False,
        )


def _parse_instant(value: str) -> Optional[datetime]:
    """Parse a stored ISO instant, tolerating a naive value (treated as UTC)."""

    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


__all__ = ["IdentityService", "LoginResult"]
