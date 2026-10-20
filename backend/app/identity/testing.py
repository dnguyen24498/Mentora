"""Test doubles for the identity capability (V0-021).

`docs/architecture/21_TESTING_CHAOS_AND_ACCEPTANCE.md` requires a test double for
every replaceable capability, and ``DEC-RELIABILITY-001`` requires the failure paths
to be *provable*: a deadline, a bounded retry, an open breaker. So this double is
deliberately **scripted** rather than random — a test states the exact sequence of
verdicts it wants and asserts what the contract did with them.

It is also usable as a dev stub: :class:`ScriptedAuthenticator` with no script
denies everything, which is the right default for "no credential capability is
wired".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.identity.errors import (
    ISSUE_AUTHENTICATION_TIMEOUT,
    ISSUE_AUTHENTICATION_UNAVAILABLE,
    ISSUE_INVALID_CREDENTIALS,
    CredentialUnavailableError,
)
from app.identity.port import (
    AuthenticationConfig,
    AuthenticationRequest,
    Authenticator,
    AuthenticatorIdentity,
)


@dataclass
class ScriptedOutcome:
    """One queued verdict for the double."""

    #: ``True`` accepts, ``False`` refuses, or name a transient failure to raise.
    accept: bool = False
    transient: Optional[str] = None
    retryable: bool = True


#: A transient failure that the contract should retry: the capability is briefly
#: unusable, which is not the caller's fault.
TRANSIENT_UNAVAILABLE = "unavailable"
#: A transient failure that must *not* be retried.
TRANSIENT_TERMINAL = "terminal"


class ScriptedAuthenticator(Authenticator):
    """An authenticator whose verdicts are queued by the test.

    With an empty script every attempt is refused, so a mis-wired test fails closed.
    """

    def __init__(
        self,
        *,
        config: Optional[AuthenticationConfig] = None,
        identity: Optional[AuthenticatorIdentity] = None,
        script: Optional[list[ScriptedOutcome]] = None,
        secrets: Optional[dict[str, str]] = None,
    ) -> None:
        super().__init__(config)
        self.identity_override = identity
        self.script: list[ScriptedOutcome] = list(script or [])
        self.calls: list[AuthenticationRequest] = []
        #: Credentials it accepts, when the script is empty (subject -> secret).
        self.secrets: dict[str, str] = dict(secrets or {})
        #: Credentials this double was asked to provision (institution, account, secret).
        self.provisioned: list[tuple[str, str, str]] = []

    @property
    def identity(self) -> AuthenticatorIdentity:
        return self.identity_override or AuthenticatorIdentity(
            name="scripted", version="1.0.0", kind="TEST_DOUBLE"
        )

    def _verify_credential(
        self, request: AuthenticationRequest, account_id: Optional[str]
    ) -> bool:
        self.calls.append(request)
        if self.script:
            step = self.script.pop(0)
            if step.transient == TRANSIENT_UNAVAILABLE:
                raise CredentialUnavailableError(
                    "scripted transient failure",
                    issue_code=ISSUE_AUTHENTICATION_UNAVAILABLE,
                    retryable=step.retryable,
                )
            if step.transient == TRANSIENT_TERMINAL:
                raise CredentialUnavailableError(
                    "scripted terminal failure",
                    issue_code=ISSUE_AUTHENTICATION_TIMEOUT,
                    retryable=False,
                )
            return step.accept
        if account_id is None:
            return False
        return self.secrets.get(account_id) == request.credential

    def provision_credential(self, institution_id: str, account_id: str, secret: str) -> bool:
        """Record a caller-supplied credential and accept it thereafter.

        Behaving like a credential *store* rather than a random issuer keeps a test
        simple: it can create an account with a password and sign in with the same
        value, without reading a secret back out of a mutation.
        """

        self.provisioned.append((institution_id, account_id, secret))
        self.secrets[account_id] = secret
        return True


__all__ = [
    "TRANSIENT_TERMINAL",
    "TRANSIENT_UNAVAILABLE",
    "ScriptedAuthenticator",
    "ScriptedOutcome",
]
