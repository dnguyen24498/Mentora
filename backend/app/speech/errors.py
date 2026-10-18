"""Classified failures of the neutral voice capability (V0-012).

``docs/providers/TTS_VOICE_PROVIDER.md`` requires *"stable error classification,
idempotency where applicable, deadline/cancellation, ... and test double"*. So a
speech failure carries a **code**, never prose a caller has to parse, and the set
of codes that may be retried is explicit (``DEC-RELIABILITY-001``: *retry transient
idempotent work only*).

The classification is deliberately provider-neutral: it names what the *capability*
failed at (a reservation was refused, synthesis exceeded its deadline, the voice is
not authorized), not which vendor said so. A vendor SDK error is translated into
one of these codes by the adapter, so nothing vendor-specific reaches the domain.

This module is stdlib-only and does not import the rest of the application, so the
domain port stays independent of any adapter or framework.
"""

from __future__ import annotations

from enum import Enum


class SpeechErrorCode(str, Enum):
    """Stable speech error classification (never parse the message)."""

    #: The request is malformed (empty text, oversized input, bad marker plan).
    INVALID_REQUEST = "INVALID_REQUEST"
    #: The requested voice is not one this platform may use (neutral-only in V0).
    VOICE_NOT_AUTHORIZED = "VOICE_NOT_AUTHORIZED"
    #: The capability is unusable right now (circuit open / not configured).
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    #: Admission control refused the reservation (capacity exhausted).
    RESERVATION_DENIED = "RESERVATION_DENIED"
    #: A reservation was used after its bounded lifetime.
    RESERVATION_EXPIRED = "RESERVATION_EXPIRED"
    #: Synthesis did not finish inside the end-to-end deadline.
    SYNTHESIS_TIMEOUT = "SYNTHESIS_TIMEOUT"
    #: Synthesis failed for a non-timeout reason (a vendor/transport error).
    SYNTHESIS_FAILED = "SYNTHESIS_FAILED"
    #: Releasing a reservation failed at the provider.
    RELEASE_FAILED = "RELEASE_FAILED"
    #: The generation was cancelled before it completed.
    CANCELLED = "CANCELLED"


#: Only these may be retried. Everything else must fail fast, so a permanent
#: error cannot loop (``DEC-RELIABILITY-001``).
RETRYABLE_SPEECH_CODES = frozenset(
    {SpeechErrorCode.SYNTHESIS_TIMEOUT, SpeechErrorCode.PROVIDER_UNAVAILABLE}
)


class SpeechError(Exception):
    """Raised for a refusal *before* work starts, or a classified failure.

    Two things raise this: a **refusal** (invalid request, unauthorized voice,
    open circuit, refused reservation) which is raised before any attempt, and a
    **synthesis failure** raised from inside a provider's stream, which the
    provider template converts into a ``FAILED`` segment instead of propagating.
    """

    def __init__(self, code: SpeechErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    @property
    def retryable(self) -> bool:
        return self.code in RETRYABLE_SPEECH_CODES


def is_retryable(code: SpeechErrorCode) -> bool:
    """Whether ``code`` may be retried (mirrors :attr:`SpeechError.retryable`)."""

    return code in RETRYABLE_SPEECH_CODES


__all__ = [
    "RETRYABLE_SPEECH_CODES",
    "SpeechError",
    "SpeechErrorCode",
    "is_retryable",
]
