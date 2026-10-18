"""Speech-provider registry (V0-012).

The provider is replaceable infrastructure and ``DEC-TECH-007`` is ``OPEN``, so V0
ships one *local* implementation behind the ``SpeechProvider`` interface and
selects it here by name. Adding a real provider later is an addition to
``SPEECH_PROVIDERS`` plus one adapter module — never a change to the domain.

The default is the deterministic neutral adapter, which is V0's explicitly
approved temporary mock while the provider decision is pending (ADR-P007).
"""

from __future__ import annotations

from typing import Optional

from app.common.errors import AppError, ErrorCode
from app.providers.deterministic import DeterministicSpeechProvider
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


__all__ = [
    "DEFAULT_SPEECH_PROVIDER",
    "PROVIDER_DETERMINISTIC",
    "SPEECH_PROVIDERS",
    "UnknownSpeechProviderError",
    "build_speech_service",
    "create_speech_provider",
]
