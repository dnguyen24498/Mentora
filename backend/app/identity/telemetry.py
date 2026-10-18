"""Structured telemetry for authentication and authorization (V0-021).

Follows the render-stage, publication and class-start telemetry
(``docs/architecture/20_OBSERVABILITY_COST_AND_CAPACITY.md``). Three things are
**never** recorded, and that is the point of this module:

* the credential (a password or an assertion) — not even its length;
* a raw session token — only that one was issued, and when it expires;
* the subject in clear. An email identifies a person, so it is recorded as
  *presence* plus a short digest, which correlates events for one account without
  storing the address in a log.

``docs/sequences/CLASS_START.md`` asserts *"Every terminal path emits metrics and
user-visible state."* The same applies here: a **refused** login and a
**scope-denied** call are the security-relevant events, so they are emitted with
their ``issue_code`` rather than only counting the successes.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("mentora.identity")


def subject_digest(subject: str) -> str:
    """A pseudonymous correlation id for a subject: not reversible to the email."""

    return hashlib.sha256((subject or "").strip().lower().encode("utf-8")).hexdigest()[:12]


@dataclass
class IdentityMetrics:
    """Counters for the identity flow."""

    logins_succeeded: int = 0
    logins_denied: int = 0
    logins_unavailable: int = 0
    session_refusals: int = 0
    sessions_revoked: int = 0
    scope_denials: int = 0
    accounts_created: int = 0
    accounts_linked: int = 0
    invitations_issued: int = 0

    def to_dict(self) -> dict[str, int]:
        return dict(self.__dict__)


@dataclass
class IdentityTelemetry:
    """Emits one structured record per outcome and keeps counters."""

    metrics: IdentityMetrics = field(default_factory=IdentityMetrics)
    _logger: logging.Logger = field(default=logger, repr=False)

    def emit(self, event: str, **fields: Any) -> dict[str, Any]:
        record = {"event": event, **fields}
        try:
            self._logger.info(json.dumps(record, sort_keys=True, default=str))
        except (TypeError, ValueError):  # pragma: no cover - telemetry must never break a login
            self._logger.info("event=%s", event)
        return record

    def record_login(
        self,
        *,
        institution_id: str,
        subject: str,
        authenticated: bool,
        error_code: Optional[str],
        attempts: int,
        duration_ms: int,
        authenticator: Optional[str] = None,
        role: Optional[str] = None,
    ) -> dict[str, Any]:
        if authenticated:
            self.metrics.logins_succeeded += 1
        elif error_code in {"AUTHENTICATION_TIMEOUT", "AUTHENTICATION_UNAVAILABLE"}:
            self.metrics.logins_unavailable += 1
        else:
            self.metrics.logins_denied += 1
        return self.emit(
            "identity.login",
            institution_id=institution_id,
            # Correlation without the address (a subject identifies a person).
            subject_digest=subject_digest(subject),
            authenticated=authenticated,
            error_code=error_code,
            attempts=attempts,
            duration_ms=duration_ms,
            authenticator=authenticator,
            role=role,
        )

    def record_session_refused(
        self, *, institution_id: Optional[str], issue_code: str, route: Optional[str] = None
    ) -> dict[str, Any]:
        self.metrics.session_refusals += 1
        return self.emit(
            "identity.session_refused",
            institution_id=institution_id,
            issue_code=issue_code,
            route=route,
        )

    def record_sign_out(self, *, institution_id: str, revoked: bool) -> dict[str, Any]:
        if revoked:
            self.metrics.sessions_revoked += 1
        return self.emit("identity.sign_out", institution_id=institution_id, revoked=revoked)

    def record_scope_denied(
        self, *, institution_id: str, role: str, scope: str, route: Optional[str] = None
    ) -> dict[str, Any]:
        self.metrics.scope_denials += 1
        return self.emit(
            "identity.scope_denied",
            institution_id=institution_id,
            role=role,
            scope=scope,
            route=route,
        )

    def record_invitation(
        self,
        *,
        institution_id: str,
        class_id: str,
        subject: str,
        created: bool,
        credential_issued: bool,
        role: str,
    ) -> dict[str, Any]:
        if created:
            self.metrics.accounts_created += 1
        else:
            self.metrics.accounts_linked += 1
        if credential_issued:
            self.metrics.invitations_issued += 1
        return self.emit(
            "identity.invitation",
            institution_id=institution_id,
            class_id=class_id,
            subject_digest=subject_digest(subject),
            created=created,
            credential_issued=credential_issued,
            role=role,
        )


__all__ = ["IdentityMetrics", "IdentityTelemetry", "subject_digest"]
