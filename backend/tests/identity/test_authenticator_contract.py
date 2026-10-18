"""The credential-verification contract every adapter inherits (V0-021).

These tests are about the *base class*, not about any adapter: admission control,
the bounded retry of retryable failures only, the terminal verdict, and the
timing-equalized refusal that makes login not an enumeration oracle
(``docs/security/IDENTITY_AUTHORIZATION_AND_TOKENS.md``, ``DEC-RELIABILITY-001``).
"""

from __future__ import annotations

import itertools

from app.identity.errors import (
    ISSUE_AUTHENTICATION_TIMEOUT,
    ISSUE_AUTHENTICATION_UNAVAILABLE,
    ISSUE_INVALID_CREDENTIALS,
)
from app.identity.port import (
    AuthenticationConfig,
    AuthenticationRequest,
    AuthenticationStatus,
)
from app.identity.testing import (
    TRANSIENT_TERMINAL,
    TRANSIENT_UNAVAILABLE,
    ScriptedAuthenticator,
    ScriptedOutcome,
)

REQUEST = AuthenticationRequest(institution_id="uni-1", subject="ana@uni.test", credential="s3cret")
RESOLVE_KNOWN = lambda institution_id, subject: "acc-1"  # noqa: E731
RESOLVE_UNKNOWN = lambda institution_id, subject: None  # noqa: E731


def stepping_clock(step: float = 1.0):
    """A deterministic monotonic clock: one second per call, so a deadline is exact."""

    ticks = itertools.count()
    return lambda: next(ticks) * step


def test_a_valid_credential_authenticates():
    authenticator = ScriptedAuthenticator(script=[ScriptedOutcome(accept=True)])

    outcome = authenticator.authenticate(REQUEST, RESOLVE_KNOWN)

    assert outcome.status is AuthenticationStatus.AUTHENTICATED
    assert outcome.authenticated
    assert outcome.subject is not None and outcome.subject.subject == "ana@uni.test"
    assert outcome.attempts == 1
    assert outcome.authenticator is not None and outcome.authenticator.kind == "TEST_DOUBLE"


def test_an_unknown_account_and_a_wrong_credential_are_indistinguishable():
    """No enumeration oracle: the same status *and* the same code for both causes."""

    unknown = ScriptedAuthenticator(script=[ScriptedOutcome(accept=False)])
    wrong = ScriptedAuthenticator(script=[ScriptedOutcome(accept=False)])

    unknown_outcome = unknown.authenticate(REQUEST, RESOLVE_UNKNOWN)
    wrong_outcome = wrong.authenticate(REQUEST, RESOLVE_KNOWN)

    assert unknown_outcome.status is wrong_outcome.status is AuthenticationStatus.DENIED
    assert unknown_outcome.error_code == wrong_outcome.error_code == ISSUE_INVALID_CREDENTIALS


def test_a_refusal_is_terminal_and_never_retried():
    """Retrying a wrong credential would be a brute-force amplifier."""

    authenticator = ScriptedAuthenticator(
        config=AuthenticationConfig(max_attempts=4),
        script=[ScriptedOutcome(accept=False)],
    )

    outcome = authenticator.authenticate(REQUEST, RESOLVE_KNOWN)

    assert outcome.status is AuthenticationStatus.DENIED
    assert outcome.attempts == 1
    assert len(authenticator.calls) == 1


def test_a_retryable_failure_is_retried_then_reported_unavailable():
    authenticator = ScriptedAuthenticator(
        config=AuthenticationConfig(max_attempts=3, timeout_ms=60_000),
        script=[
            ScriptedOutcome(transient=TRANSIENT_UNAVAILABLE),
            ScriptedOutcome(transient=TRANSIENT_UNAVAILABLE),
            ScriptedOutcome(transient=TRANSIENT_UNAVAILABLE),
        ],
    )

    outcome = authenticator.authenticate(REQUEST, RESOLVE_KNOWN)

    assert outcome.status is AuthenticationStatus.UNAVAILABLE
    assert outcome.error_code == ISSUE_AUTHENTICATION_UNAVAILABLE
    assert outcome.attempts == 3


def test_a_non_retryable_failure_does_not_loop():
    authenticator = ScriptedAuthenticator(
        config=AuthenticationConfig(max_attempts=4, timeout_ms=60_000),
        script=[ScriptedOutcome(transient=TRANSIENT_TERMINAL), ScriptedOutcome(accept=True)],
    )

    outcome = authenticator.authenticate(REQUEST, RESOLVE_KNOWN)

    assert outcome.status is AuthenticationStatus.UNAVAILABLE
    assert outcome.attempts == 1


def test_a_retryable_failure_recovers_within_the_retry_budget():
    """One transient failure must not deny a valid credential."""

    authenticator = ScriptedAuthenticator(
        config=AuthenticationConfig(max_attempts=3, timeout_ms=60_000),
        script=[ScriptedOutcome(transient=TRANSIENT_UNAVAILABLE), ScriptedOutcome(accept=True)],
    )

    outcome = authenticator.authenticate(REQUEST, RESOLVE_KNOWN)

    assert outcome.status is AuthenticationStatus.AUTHENTICATED
    assert outcome.attempts == 2


def test_the_deadline_bounds_the_work():
    """A capability that never answers must not hold the request open."""

    authenticator = ScriptedAuthenticator(
        config=AuthenticationConfig(max_attempts=10, timeout_ms=1_500),
        script=[ScriptedOutcome(transient=TRANSIENT_UNAVAILABLE) for _ in range(10)],
    )

    outcome = authenticator.authenticate(REQUEST, RESOLVE_KNOWN, clock=stepping_clock())

    assert outcome.status is AuthenticationStatus.TIMEOUT
    assert outcome.error_code == ISSUE_AUTHENTICATION_TIMEOUT
    assert outcome.attempts < 10


def test_an_empty_request_is_refused_without_work():
    authenticator = ScriptedAuthenticator(script=[ScriptedOutcome(accept=True)])

    outcome = authenticator.authenticate(
        AuthenticationRequest(institution_id="uni-1", subject="  ", credential=""), RESOLVE_KNOWN
    )

    assert outcome.status is AuthenticationStatus.DENIED
    assert outcome.attempts == 0
    assert authenticator.calls == []


def test_a_vendor_exception_cannot_escape_as_a_500():
    class Exploding(ScriptedAuthenticator):
        def _verify_credential(self, request, account_id):  # type: ignore[override]
            raise RuntimeError("vendor SDK blew up")

    outcome = Exploding().authenticate(REQUEST, RESOLVE_KNOWN)

    assert outcome.status is AuthenticationStatus.UNAVAILABLE
    assert outcome.error_code == ISSUE_AUTHENTICATION_UNAVAILABLE
    assert outcome.metadata["detail"] == "RuntimeError"


def test_admission_control_refuses_beyond_the_limit():
    """Bounded work: past the concurrency limit a caller is refused, not queued."""

    authenticator = ScriptedAuthenticator(config=AuthenticationConfig(max_in_flight=1))
    authenticator._in_flight = 1  # simulate an in-flight verification

    outcome = authenticator.authenticate(REQUEST, RESOLVE_KNOWN)

    assert outcome.status is AuthenticationStatus.UNAVAILABLE
    assert authenticator.calls == []


def test_the_breaker_opens_after_repeated_transient_failures():
    authenticator = ScriptedAuthenticator(
        config=AuthenticationConfig(max_attempts=1, breaker_threshold=2, timeout_ms=60_000),
        script=[
            ScriptedOutcome(transient=TRANSIENT_UNAVAILABLE),
            ScriptedOutcome(transient=TRANSIENT_UNAVAILABLE),
        ],
    )

    assert authenticator.health().available is True
    authenticator.authenticate(REQUEST, RESOLVE_KNOWN)
    assert authenticator.health().available is True
    authenticator.authenticate(REQUEST, RESOLVE_KNOWN)

    health = authenticator.health()
    assert health.available is False
    assert "circuit open" in health.detail


def test_the_unauthenticated_default_fails_closed():
    """No script and no secrets: an empty double denies, it does not accept."""

    assert ScriptedAuthenticator().authenticate(REQUEST, RESOLVE_KNOWN).status is (
        AuthenticationStatus.DENIED
    )
