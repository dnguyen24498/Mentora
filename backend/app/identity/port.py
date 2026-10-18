"""The provider-neutral credential-verification contract (V0-021).

``docs/security/IDENTITY_AUTHORIZATION_AND_TOKENS.md`` fixes *institutional
federation* as the authentication model but — because ``FND-002`` is still ``TODO``
and no ADR accepts a mechanism — decides no implementation. So this module is the
seam, and it is deliberately the smallest thing that can be a seam:

* the **domain** owns accounts (who exists) and sessions (what a caller may do);
* an **adapter** owns credentials (how a subject proves it is that account).

:class:`Authenticator` is the second half. It is an ABC because the base owns the
parts that must not vary between adapters — admission control, the end-to-end
deadline, bounded retry of *retryable* failures only, timing-equalized refusal, and
a terminal verdict — so a federation adapter cannot skip any of them
(``DEC-RELIABILITY-001``).

**Never raises.** :meth:`Authenticator.authenticate` returns an
:class:`AuthenticationOutcome`; a refusal is a value, not an exception. That is the
same shape :class:`app.speech.service.SpeechService` has, and for the same reason:
a login is a control-plane operation on the lesson's critical path, and the caller
must be able to answer "can't sign in right now" without an exception unwinding
into a 500.

Nothing in this module imports the application, an HTTP framework or a vendor SDK.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from app.identity.errors import (
    ISSUE_AUTHENTICATION_TIMEOUT,
    ISSUE_AUTHENTICATION_UNAVAILABLE,
    ISSUE_INVALID_CREDENTIALS,
    CredentialUnavailableError,
)

#: ``(institution_id, subject) -> account_id`` or ``None`` when no such account
#: exists in that tenant. Supplied by the domain (the repository), so an adapter
#: never learns how accounts are stored.
AccountResolver = Callable[[str, str], Optional[str]]


class AuthenticationStatus(str, Enum):
    """Terminal verdict of one authentication attempt."""

    AUTHENTICATED = "AUTHENTICATED"
    #: The credential was refused — the same verdict for an unknown account and a
    #: wrong credential, so the outcome is not an enumeration oracle.
    DENIED = "DENIED"
    #: The capability is unusable (breaker open, no adapter, transient failure that
    #: outlived its retries).
    UNAVAILABLE = "UNAVAILABLE"
    #: The deadline was exceeded before a verdict was reached.
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True)
class AuthenticatorIdentity:
    """Which credential capability answered. Recorded on every login.

    ``kind`` is what keeps this honest: ``DEVELOPMENT_MOCK`` says the adapter stands
    in for the undecided federation mechanism, so a session can always be traced
    back to a mock instead of silently looking like production authentication.
    """

    name: str
    version: str
    kind: str = "DEVELOPMENT_MOCK"

    @property
    def id(self) -> str:
        return f"{self.name}@{self.version}"

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "version": self.version, "kind": self.kind, "id": self.id}


@dataclass(frozen=True)
class AuthenticationRequest:
    """A subject proving it is an account in a tenant.

    ``credential`` is intentionally opaque: a password for the development adapter,
    an assertion or authorization-code result for a federation adapter. The port
    never inspects it, so the domain cannot become credential-shaped.
    """

    institution_id: str
    subject: str
    credential: str


@dataclass(frozen=True)
class VerifiedSubject:
    """A subject whose credential checked out. Not yet a principal."""

    subject: str
    institution_id: str
    display_name: str = ""


@dataclass(frozen=True)
class AuthenticationOutcome:
    """What credential verification concluded. Never an exception."""

    status: AuthenticationStatus
    subject: Optional[VerifiedSubject] = None
    error_code: Optional[str] = None
    attempts: int = 0
    duration_ms: int = 0
    authenticator: Optional[AuthenticatorIdentity] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def authenticated(self) -> bool:
        return self.status is AuthenticationStatus.AUTHENTICATED

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "error_code": self.error_code,
            "attempts": self.attempts,
            "duration_ms": self.duration_ms,
            "authenticator": self.authenticator.to_dict() if self.authenticator else None,
        }


@dataclass(frozen=True)
class AuthenticationConfig:
    """Bounded work: a deadline and a retry ceiling (``DEC-RELIABILITY-001``)."""

    #: End-to-end deadline for one authentication attempt set.
    timeout_ms: int = 2_000
    #: Attempts for a *retryable* (transient) failure. A refusal is terminal, so a
    #: wrong credential is never retried — that would be a brute-force amplifier.
    max_attempts: int = 2
    #: Concurrent verifications this process will admit. Beyond it, callers are
    #: refused as UNAVAILABLE rather than queueing without bound.
    max_in_flight: int = 32
    #: Consecutive transient failures that open the breaker.
    breaker_threshold: int = 5


class AuthenticationBudget:
    """Injected-clock deadline for one authentication (testable, not wall-clock)."""

    def __init__(self, timeout_ms: int, clock: Callable[[], float] = time.monotonic) -> None:
        self._timeout_ms = timeout_ms
        self._clock = clock
        self._started = clock()

    def elapsed_ms(self) -> int:
        return int((self._clock() - self._started) * 1000)

    def remaining_ms(self) -> int:
        return self._timeout_ms - self.elapsed_ms()

    def expired(self) -> bool:
        return self.remaining_ms() <= 0


@dataclass
class AuthenticatorHealth:
    """Whether the capability is usable, and why not when it is not."""

    available: bool
    detail: str = ""
    consecutive_failures: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "detail": self.detail,
            "consecutive_failures": self.consecutive_failures,
        }


class Authenticator(ABC):
    """Base class owning the credential-verification contract.

    Subclasses implement exactly two things: :meth:`identity` (which capability
    answered) and :meth:`_verify_credential` (compare the credential). Everything
    else — admission, deadline, retry, breaker, verdict — happens here so it cannot
    be omitted.
    """

    def __init__(self, config: Optional[AuthenticationConfig] = None) -> None:
        self.config = config or AuthenticationConfig()
        self._in_flight = 0
        self._consecutive_failures = 0

    # -- what an adapter must provide -------------------------------------------------
    @property
    @abstractmethod
    def identity(self) -> AuthenticatorIdentity:
        """Which credential capability this is (recorded on every session)."""

    @abstractmethod
    def _verify_credential(self, request: AuthenticationRequest, account_id: Optional[str]) -> bool:
        """Return True when ``request.credential`` is valid for ``account_id``.

        **Contract**

        * ``account_id`` is ``None`` when the tenant has no such subject. The
          implementation **MUST** still perform comparable work — a dummy
          verification against a throwaway record — so an unknown account and a
          wrong credential cost the same and cannot be told apart by timing.
        * Return ``False`` for a refusal. Raise
          :class:`~app.identity.errors.CredentialUnavailableError` for a *transient*
          failure (the retryable set is named there); the template converts it into
          a bounded retry, then ``UNAVAILABLE``.
        * Never let a vendor exception escape; classify it first, so no vendor type
          reaches the domain.
        """

    # -- the contract (final) ---------------------------------------------------------
    def authenticate(
        self,
        request: AuthenticationRequest,
        resolve_account: AccountResolver,
        clock: Callable[[], float] = time.monotonic,
    ) -> AuthenticationOutcome:
        """Verify a credential. Returns a verdict; never raises."""

        budget = AuthenticationBudget(self.config.timeout_ms, clock=clock)

        if not (request.subject or "").strip() or not request.credential:
            return self._denied(request, budget, attempts=0)

        if self._in_flight >= self.config.max_in_flight:
            return AuthenticationOutcome(
                status=AuthenticationStatus.UNAVAILABLE,
                error_code=ISSUE_AUTHENTICATION_UNAVAILABLE,
                attempts=0,
                duration_ms=budget.elapsed_ms(),
                authenticator=self.identity,
                metadata={"detail": "admission control refused the attempt"},
            )

        self._in_flight += 1
        attempts = 0
        try:
            while attempts < max(1, self.config.max_attempts):
                if budget.expired():
                    return self._timed_out(budget, attempts)
                attempts += 1
                try:
                    account_id = resolve_account(request.institution_id, request.subject)
                    if self._verify_credential(request, account_id):
                        if account_id is None:  # a defensive guard, not a path
                            return self._denied(request, budget, attempts)
                        self._consecutive_failures = 0
                        return AuthenticationOutcome(
                            status=AuthenticationStatus.AUTHENTICATED,
                            subject=VerifiedSubject(
                                subject=request.subject,
                                institution_id=request.institution_id,
                            ),
                            attempts=attempts,
                            duration_ms=budget.elapsed_ms(),
                            authenticator=self.identity,
                        )
                    # A refusal is terminal: retrying a wrong credential is a
                    # brute-force amplifier, so only transient failures loop.
                    return self._denied(request, budget, attempts)
                except CredentialUnavailableError as exc:
                    self._consecutive_failures += 1
                    if not exc.retryable or attempts >= max(1, self.config.max_attempts):
                        return AuthenticationOutcome(
                            status=AuthenticationStatus.UNAVAILABLE,
                            error_code=exc.issue_code,
                            attempts=attempts,
                            duration_ms=budget.elapsed_ms(),
                            authenticator=self.identity,
                            metadata={"detail": exc.message},
                        )
                except Exception as exc:  # noqa: BLE001 - a vendor error must not escape
                    self._consecutive_failures += 1
                    return AuthenticationOutcome(
                        status=AuthenticationStatus.UNAVAILABLE,
                        error_code=ISSUE_AUTHENTICATION_UNAVAILABLE,
                        attempts=attempts,
                        duration_ms=budget.elapsed_ms(),
                        authenticator=self.identity,
                        metadata={"detail": f"{type(exc).__name__}"},
                    )
            return self._timed_out(budget, attempts)
        finally:
            self._in_flight -= 1

    def health(self) -> AuthenticatorHealth:
        """Whether the capability is usable. Opens after consecutive failures."""

        open_breaker = self._consecutive_failures >= self.config.breaker_threshold
        return AuthenticatorHealth(
            available=not open_breaker,
            detail="circuit open after repeated transient failures" if open_breaker else "ok",
            consecutive_failures=self._consecutive_failures,
        )

    def issue_credential(self, institution_id: str, account_id: str) -> Optional[str]:
        """Provision a first credential for a newly invited account, returned **once**.

        Provisioning is optional, and the default says so: a federation deployment
        does not need it, because the identity provider owns the credential and an
        invitation grants no local secret. Only a credential-issuing adapter (the
        development mock) overrides this, and an override **MUST** store only a
        digest.
        """

        return None

    # -- internals --------------------------------------------------------------------
    def _denied(
        self,
        request: AuthenticationRequest,
        budget: AuthenticationBudget,
        attempts: int,
    ) -> AuthenticationOutcome:
        return AuthenticationOutcome(
            status=AuthenticationStatus.DENIED,
            error_code=ISSUE_INVALID_CREDENTIALS,
            attempts=attempts,
            duration_ms=budget.elapsed_ms(),
            authenticator=self.identity,
            metadata={"subject_hash_available": bool(request.subject)},
        )

    def _timed_out(self, budget: AuthenticationBudget, attempts: int) -> AuthenticationOutcome:
        return AuthenticationOutcome(
            status=AuthenticationStatus.TIMEOUT,
            error_code=ISSUE_AUTHENTICATION_TIMEOUT,
            attempts=attempts,
            duration_ms=budget.elapsed_ms(),
            authenticator=self.identity,
        )


@dataclass(frozen=True)
class CredentialRecord:
    """It is entirely the adapter's business how a credential is represented."""

    algorithm: str
    salt: str
    digest: str


class CredentialStore(ABC):
    """Where an adapter keeps its own credential material.

    The domain stores *accounts*; this stores the adapter's representation of how a
    subject proves one. Keeping it behind a seam is what lets a federation adapter
    replace the local one without the domain ever seeing a credential.
    """

    @abstractmethod
    def get(self, institution_id: str, account_id: str) -> Optional[CredentialRecord]:
        """The stored record, or ``None`` when the account has no credential yet."""

    @abstractmethod
    def put(self, institution_id: str, account_id: str, record: CredentialRecord) -> None:
        """Store (or replace) the record. Idempotent per account."""
