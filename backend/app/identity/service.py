"""The identity service: log in, prove a session, sign out, administer accounts.

Four responsibilities, deliberately kept apart:

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
* :meth:`IdentityService.create_account` / :meth:`update_account` /
  :meth:`delete_account` / :meth:`change_password` are the **directory** (V0-022,
  V0-023): create-or-link an account, change it, remove it, and set the password a
  subject signs in with. An administrator supplies an account's initial password and
  can reset it; an account holder changes their own. Disabling an account — and
  setting a password — revokes its live sessions in the same call, so the change
  takes effect on the next request rather than at session expiry
  (``DEC-RUNTIME-007``).
* :meth:`IdentityService.bootstrap_administrator` is the one-shot seam that gives a
  fresh installation its **first** administrator, because every other account verb
  requires an administrator to authorize it.

What this module deliberately does **not** know: whether an account may be removed
(a roster reference is another domain's fact — the API layer composes that check),
and how a credential is verified (that is the port's).

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
    ISSUE_INVALID_CREDENTIALS,
    ISSUE_SESSION_EXPIRED,
    ISSUE_SESSION_REQUIRED,
    ISSUE_SESSION_REVOKED,
    ISSUE_SESSION_UNKNOWN,
    BootstrapClosedError,
    CredentialDeniedError,
    CredentialPolicyError,
    InvitationConflictError,
    RoleNotManageableError,
    SessionError,
)
from app.identity.models import (
    MANAGEABLE_ROLES,
    Account,
    AccountMutation,
    AuthSession,
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

#: The shortest password this surface will store (V0-023). A **development guard, not
#: a decided password policy**: ``FND-002`` is ``TODO`` and V0-022 left password
#: policy out of scope, so this exists only so an administrator cannot set a
#: trivially guessable initial credential. A federation deployment replaces the whole
#: mechanism, and the policy with it.
MIN_CREDENTIAL_LENGTH = 8


def _require_secret(secret: str) -> str:
    """Validate a password this surface is about to store.

    Refused as a malformed request (``400 CREDENTIAL_TOO_WEAK``) rather than a
    denial, because the caller can fix it by supplying a longer one.
    """

    value = secret or ""
    if len(value) < MIN_CREDENTIAL_LENGTH:
        raise CredentialPolicyError(
            f"a password of at least {MIN_CREDENTIAL_LENGTH} characters is required"
        )
    return value


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
    def _verify(
        self, institution_id: str, subject: str, credential: str
    ) -> AuthenticationOutcome:
        """One credential verification through the replaceable authenticator.

        Shared by sign-in and by the current-password check of a password change, so
        both go through the same admission control, deadline and refusal shape.
        """

        request = AuthenticationRequest(
            institution_id=institution_id, subject=subject, credential=credential
        )
        if self._monotonic is None:
            return self._authenticator.authenticate(request, self._repository.resolve_subject)
        return self._authenticator.authenticate(
            request, self._repository.resolve_subject, clock=self._monotonic
        )

    def login(self, institution_id: str, subject: str, credential: str) -> LoginResult:
        """Verify a credential and, on success, mint a session. Never raises."""

        outcome = self._verify(institution_id, subject, credential)

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

    def find_account_by_email(self, institution_id: str, email: str) -> Optional[Account]:
        """One account of this tenant by address, or ``None`` (the enrolment lookup)."""

        return self._repository.find_account_by_email(institution_id, email)

    def list_accounts(self, institution_id: str, *, role: Role) -> list[Account]:
        """The tenant's accounts of one role, for a picker or a directory view."""

        return self._repository.list_accounts(institution_id, role=role)

    def create_account(
        self,
        institution_id: str,
        *,
        email: str,
        role: Role,
        secret: str,
        display_name: str = "",
        actor_role: str = "",
    ) -> AccountMutation:
        """Create-or-link an account of a manageable role (V0-022, V0-023).

        **Create-or-link, not create**: the same address and role is one account, so
        a retried request is not an error (``DEC-RUNTIME-003``) and a replay sets no
        credential — it can never overwrite the password the holder may already have.
        The same address with a *different* role is refused rather than silently
        promoted: changing what an account is is an administrative decision, and this
        route does not make it implicitly.

        ``secret`` is the initial password the administrator hands over.
        ``credential_set`` reports whether it was stored: a credential-managing
        adapter stores it, and a federation adapter reports ``False`` because the
        identity provider owns the credential.
        """

        if role not in MANAGEABLE_ROLES:
            raise RoleNotManageableError(
                f"{role.value!r} accounts are not created through this surface: an "
                "administrator is provisioned by the deployment bootstrap (or, with "
                "federation, by the identity provider)"
            )

        subject = normalize_email(email)
        if "@" not in subject or any(char.isspace() for char in subject) or len(subject) > 320:
            raise ValidationError("a valid email address is required")
        _require_secret(secret)

        existing = self._repository.find_account_by_email(institution_id, subject)
        if existing is not None:
            if existing.role is not role:
                raise InvitationConflictError(
                    f"{subject!r} already exists in this institution as a "
                    f"{existing.role.value}; an account's role is changed deliberately, "
                    "not as a side effect of creating one"
                )
            self._telemetry.record_account_created(
                institution_id=institution_id,
                subject=subject,
                role=existing.role.value,
                created=False,
                credential_set=False,
                actor_role=actor_role,
            )
            return AccountMutation(account=existing, created=False)

        account = self._repository.create_account(
            institution_id=institution_id,
            email=subject,
            display_name=display_name or subject,
            role=role,
        )
        credential_set = self._authenticator.provision_credential(
            institution_id, account.account_id, secret
        )
        self._telemetry.record_account_created(
            institution_id=institution_id,
            subject=subject,
            role=account.role.value,
            created=True,
            credential_set=credential_set,
            actor_role=actor_role,
        )
        return AccountMutation(
            account=account, created=True, credential_set=credential_set
        )

    def update_account(
        self,
        institution_id: str,
        account_id: str,
        *,
        display_name: Optional[str] = None,
        role: Optional[Role] = None,
        disabled: Optional[bool] = None,
        secret: Optional[str] = None,
        actor_role: str = "",
    ) -> AccountMutation:
        """Change an account's display name, role, enabled state or password (V0-022, V0-023).

        The account must exist in this tenant (``404`` from the repository) and the
        role must be manageable. **Disabling revokes the account's live sessions in
        the same call**, and reporting how many, because a disable that left a working
        token behind would not be a disable (``DEC-RUNTIME-007``); re-enabling
        restores sign-in. **Resetting a password revokes them too**, for the same
        reason: a credential change that left other live sessions working would not
        really have changed who can get in. A role change is applied the way any role
        edit is: a session's capabilities are re-derived from the account's current
        role, so a change can only remove — a promotion needs a fresh sign-in.
        """

        if role is not None and role not in MANAGEABLE_ROLES:
            raise RoleNotManageableError(
                f"{role.value!r} is not a manageable role; administrator accounts are "
                "provisioned by the deployment bootstrap, not assigned here"
            )
        if secret is not None:
            _require_secret(secret)

        account = self._repository.get_account(institution_id, account_id)
        changed: list[str] = []
        if display_name is not None and display_name.strip() != account.display_name:
            changed.append("display_name")
        if role is not None and role is not account.role:
            changed.append("role")
        if disabled is not None and disabled == account.is_active:
            changed.append("status")
        if secret is not None:
            changed.append("credential")

        updated = self._repository.update_account(
            institution_id=institution_id,
            account_id=account_id,
            display_name=display_name,
            role=role,
            disabled=disabled,
        )

        credential_set = False
        if secret is not None:
            credential_set = self._authenticator.provision_credential(
                institution_id, account_id, secret
            )

        revoked = 0
        if disabled or secret is not None:
            # Same call, so a disable — or a reset — is never "effective at the next
            # sign-in".
            revoked = self._repository.revoke_sessions_for_account(institution_id, account_id)

        self._telemetry.record_account_updated(
            institution_id=institution_id,
            account_id=account_id,
            changed=tuple(changed),
            role=updated.role.value,
            status="DISABLED" if not updated.is_active else "ACTIVE",
            sessions_revoked=revoked,
            actor_role=actor_role,
        )
        if secret is not None:
            self._telemetry.record_password_changed(
                institution_id=institution_id,
                account_id=account_id,
                changed_by="admin",
                sessions_revoked=revoked,
            )
        return AccountMutation(
            account=updated,
            created=False,
            credential_set=credential_set,
            sessions_revoked=revoked,
        )

    def change_password(
        self,
        institution_id: str,
        account_id: str,
        *,
        current_secret: str,
        new_secret: str,
        keep_session_id: Optional[str] = None,
    ) -> int:
        """Change an account holder's own password, verifying the current one first.

        The current password is checked through the *same* authenticator a sign-in
        uses, so this cannot become a weaker second path to an account. A wrong one is
        a refusal (``401 INVALID_CREDENTIALS``) and is deliberately indistinguishable
        from a sign-in refusal of the same subject.

        On success the new password is stored and every **other** live session of the
        account is revoked, because a credential change must invalidate what the old
        credential could reach (``DEC-RUNTIME-007``); ``keep_session_id`` preserves the
        caller's own session so the change does not sign them out of the page they are
        on. Returns how many sessions were revoked.
        """

        account = self._repository.get_account(institution_id, account_id)
        _require_secret(new_secret)

        outcome = self._verify(institution_id, account.email, current_secret)
        if not outcome.authenticated:
            self._telemetry.record_login(
                institution_id=institution_id,
                subject=account.email,
                authenticated=False,
                error_code=outcome.error_code,
                attempts=outcome.attempts,
                duration_ms=outcome.duration_ms,
                authenticator=self._authenticator.identity.id,
                role=account.role.value,
            )
            # The same generic words a refused sign-in uses: "the password you typed
            # is not this account's password" is the whole truth and all of it.
            raise CredentialDeniedError(
                "the current password was not accepted",
                issue_code=outcome.error_code or ISSUE_INVALID_CREDENTIALS,
            )

        self._authenticator.provision_credential(institution_id, account_id, new_secret)
        revoked = self._repository.revoke_sessions_for_account(
            institution_id, account_id, keep_session_id=keep_session_id
        )
        self._telemetry.record_password_changed(
            institution_id=institution_id,
            account_id=account_id,
            changed_by="self",
            sessions_revoked=revoked,
        )
        return revoked

    def delete_account(
        self, institution_id: str, account_id: str, *, actor_role: str = ""
    ) -> bool:
        """Remove an account with its credential material and sessions.

        Whether an account *may* be removed is not decided here: a roster reference
        is the classroom domain's fact, and the API layer composes that check before
        calling this (V0-022). This method only refuses an account of another tenant
        (``403``) or a nonexistent one (``404``).
        """

        account = self._repository.get_account(institution_id, account_id)
        removed = self._repository.delete_account(institution_id, account_id)
        if removed:
            self._telemetry.record_account_deleted(
                institution_id=institution_id,
                account_id=account_id,
                role=account.role.value,
                actor_role=actor_role,
            )
        return removed

    # -- the first administrator -----------------------------------------------------------------
    def bootstrap_administrator(
        self, institution_id: str, *, email: str, secret: str, display_name: str = ""
    ) -> AccountMutation:
        """Create the institution's **first** administrator, once.

        Under institutional federation the identity provider provisions this account,
        which is why the route that exposes this method exists only on a deployment
        that leaves the bootstrap on. The precondition is the whole security property:
        the moment this tenant *has* an administrator, every account verb requires that
        administrator to authorize it, so the bootstrap closes forever
        (``ISSUE_TENANT_ALREADY_PROVISIONED``). It refuses rather than returning an
        existing account, because "the bootstrap quietly handed you someone else's
        account" is not a thing this should be able to do.

        ``secret`` is the password the deployment's operator chooses for this account
        — the first thing they will sign in with.
        """

        subject = normalize_email(email)
        if "@" not in subject or any(char.isspace() for char in subject) or len(subject) > 320:
            raise ValidationError("a valid email address is required")
        _require_secret(secret)

        if self._repository.count_accounts(institution_id, role=Role.INSTITUTION_ADMIN) > 0:
            raise BootstrapClosedError(
                "this institution already has an administrator; sign in to create accounts"
            )

        account = self._repository.create_account(
            institution_id=institution_id,
            email=subject,
            display_name=display_name or subject,
            role=Role.INSTITUTION_ADMIN,
        )
        credential_set = self._authenticator.provision_credential(
            institution_id, account.account_id, secret
        )
        self._telemetry.record_admin_bootstrapped(
            institution_id=institution_id,
            subject=subject,
            credential_set=credential_set,
        )
        return AccountMutation(
            account=account, created=True, credential_set=credential_set
        )

    # -- the pre-auth development shortcut ---------------------------------------------
    def development_principal(self, institution_id: str) -> Principal:
        """The **pre-auth development** principal for one tenant.

        This is not authentication. It exists so the V0 flows (and their tests) keep
        working before an institutional-federation deployment replaces the
        ``X-Institution-Id`` header, and it is only ever produced when
        ``Settings.dev_tenant_header`` allows it — which **V0-023 makes off by
        default**, so a deployment requires a real session unless it is explicitly
        left open. ``authenticated=False`` travels in ``GET /auth/me`` so no client can
        mistake it for a signed-in user, and there is no account behind it — which is
        why it cannot request a class join.
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
