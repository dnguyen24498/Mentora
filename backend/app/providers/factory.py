"""Speech-provider registry (V0-012).

The provider is replaceable infrastructure and ``DEC-TECH-007`` is ``OPEN``, so V0
ships one *local* implementation behind the ``SpeechProvider`` interface and
selects it here by name. Adding a real provider later is an addition to
``SPEECH_PROVIDERS`` plus one adapter module — never a change to the domain.

The default is the deterministic neutral adapter, which is V0's explicitly
approved temporary mock while the provider decision is pending (ADR-P007).
"""

from __future__ import annotations

import sqlite3
from typing import Optional

from app.common.errors import AppError, ErrorCode
from app.identity.port import AuthenticationConfig, Authenticator
from app.identity.repository import IdentityRepository
from app.identity.service import IdentityService
from app.identity.telemetry import IdentityTelemetry
from app.providers.deterministic import DeterministicSpeechProvider
from app.providers.local_credentials import (
    LocalCredentialAuthenticator,
    build_local_authenticator,
)
from app.speech.models import SpeechConfig
from app.speech.port import SpeechProvider
from app.speech.service import SpeechService
from app.speech.telemetry import SpeechTelemetry

#: The one provider V0 runs with: dependency-free, deterministic, local.
PROVIDER_DETERMINISTIC = "neutral-deterministic"
SPEECH_PROVIDERS: tuple[str, ...] = (PROVIDER_DETERMINISTIC,)
DEFAULT_SPEECH_PROVIDER = PROVIDER_DETERMINISTIC


class UnknownSpeechProviderError(AppError):
    """An unsupported speech provider was requested (fail fast, never a 500)."""

    code = ErrorCode.INVALID_REQUEST
    http_status = 400
    issue_code = "UNKNOWN_SPEECH_PROVIDER"

    def __init__(self, name: object) -> None:
        super().__init__(
            f"unknown speech provider {name!r}; expected one of {', '.join(SPEECH_PROVIDERS)}"
        )


def create_speech_provider(
    name: str = DEFAULT_SPEECH_PROVIDER,
    *,
    config: Optional[SpeechConfig] = None,
) -> SpeechProvider:
    """Build the provider for ``name`` (the deterministic neutral adapter by default)."""

    if name == PROVIDER_DETERMINISTIC:
        return DeterministicSpeechProvider(config)
    raise UnknownSpeechProviderError(name)


def build_speech_service(
    name: str = DEFAULT_SPEECH_PROVIDER,
    *,
    config: Optional[SpeechConfig] = None,
    telemetry: Optional[SpeechTelemetry] = None,
) -> SpeechService:
    """Wire the default provider into the domain service."""

    provider = create_speech_provider(name, config=config)
    return SpeechService(provider, config=config or provider.config, telemetry=telemetry)


# -- identity (V0-021) ------------------------------------------------------------
#
# The identity mechanism is **not** a decided technology: the canonical architecture
# names institutional federation (OIDC/OAuth) and no ADR accepts a mechanism, so the
# one registered provider below is a development mock standing in for it — the same
# shape ADR-P007 gives the TTS mock while DEC-TECH-007 is OPEN. Adding a federation
# adapter later is one entry here plus one adapter module; the domain never changes.
PROVIDER_LOCAL_CREDENTIALS = "local-credentials"
IDENTITY_PROVIDERS: tuple[str, ...] = (PROVIDER_LOCAL_CREDENTIALS,)
DEFAULT_IDENTITY_PROVIDER = PROVIDER_LOCAL_CREDENTIALS


class UnknownIdentityProviderError(AppError):
    """An unsupported identity provider was requested (fail fast, never a 500)."""

    code = ErrorCode.INVALID_REQUEST
    http_status = 400
    issue_code = "UNKNOWN_IDENTITY_PROVIDER"

    def __init__(self, name: object) -> None:
        super().__init__(
            f"unknown identity provider {name!r}; "
            f"expected one of {', '.join(IDENTITY_PROVIDERS)}"
        )


def create_authenticator(
    conn: sqlite3.Connection,
    name: str = DEFAULT_IDENTITY_PROVIDER,
    *,
    config: Optional[AuthenticationConfig] = None,
) -> Authenticator:
    """Build the credential capability for ``name``.

    The default is the **development** local-credential mock, because the real
    mechanism is undecided. ``identity.kind`` reports ``DEVELOPMENT_MOCK`` so a
    session issued through it can never be mistaken for federated authentication.
    """

    if name == PROVIDER_LOCAL_CREDENTIALS:
        return build_local_authenticator(conn, config=config)
    raise UnknownIdentityProviderError(name)


def build_identity_service(
    conn: sqlite3.Connection,
    *,
    name: str = DEFAULT_IDENTITY_PROVIDER,
    config: Optional[AuthenticationConfig] = None,
    session_ttl_seconds: Optional[int] = None,
    telemetry: Optional[IdentityTelemetry] = None,
) -> IdentityService:
    """Wire the credential capability and the account repository into the domain."""

    authenticator = create_authenticator(conn, name, config=config)
    kwargs = {}
    if session_ttl_seconds is not None:
        kwargs["session_ttl_seconds"] = session_ttl_seconds
    return IdentityService(
        IdentityRepository(conn),
        authenticator,
        telemetry=telemetry,
        **kwargs,
    )


__all__ = [
    "DEFAULT_IDENTITY_PROVIDER",
    "DEFAULT_SPEECH_PROVIDER",
    "IDENTITY_PROVIDERS",
    "PROVIDER_DETERMINISTIC",
    "PROVIDER_LOCAL_CREDENTIALS",
    "SPEECH_PROVIDERS",
    "LocalCredentialAuthenticator",
    "UnknownIdentityProviderError",
    "UnknownSpeechProviderError",
    "build_identity_service",
    "build_speech_service",
    "create_authenticator",
    "create_speech_provider",
]
