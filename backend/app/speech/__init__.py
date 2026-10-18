"""Neutral voice: the provider port, models, service, telemetry and test double (V0-012).

``DEC-TECH-007`` (TTS/OmniVoice deployment and GPU capacity) is ``OPEN``, so per
``docs/adr/proposed/ADR-P007_TTS_OMNIVOICE.md`` — *"Until accepted, provider-neutral
interfaces and mocks are used"* — V0 ships the **interface** here and one
dependency-free deterministic adapter in :mod:`app.providers.deterministic`.

This package is the **domain**: it defines the ``SpeechProvider`` port and the
``SpeechService`` that reserves, synthesizes, cancels, releases and falls back to
text. It imports nothing outside itself and the stdlib, so no provider SDK or
vendor error can reach the classroom domain
(``tests/speech/test_layering.py`` asserts that import boundary).
"""

from __future__ import annotations

from app.speech.errors import (
    RETRYABLE_SPEECH_CODES,
    SpeechError,
    SpeechErrorCode,
    is_retryable,
)
from app.speech.models import (
    NEUTRAL_VOICE_ID,
    AuthorizedVoice,
    CancelAck,
    MarkerPlan,
    ProviderHealth,
    ProviderIdentity,
    Reservation,
    ReservationRequest,
    SpeechChunk,
    SpeechConfig,
    SpeechMarker,
    SpeechMarkerRealization,
    SpeechOutcome,
    SpeechOutcomeStatus,
    SpeechRequest,
    SpeechSegment,
    SpeechUsage,
    TextFallback,
    VoiceKind,
    VoiceState,
    normalize_text,
)
from app.speech.port import CancelToken, SpeechBudget, SpeechProvider
from app.speech.service import SpeechService
from app.speech.telemetry import SpeechMetrics, SpeechTelemetry
from app.speech.testing import ScriptedSpeechProvider

__all__ = [
    "NEUTRAL_VOICE_ID",
    "RETRYABLE_SPEECH_CODES",
    "AuthorizedVoice",
    "CancelAck",
    "CancelToken",
    "MarkerPlan",
    "ProviderHealth",
    "ProviderIdentity",
    "Reservation",
    "ReservationRequest",
    "ScriptedSpeechProvider",
    "SpeechBudget",
    "SpeechChunk",
    "SpeechConfig",
    "SpeechError",
    "SpeechErrorCode",
    "SpeechMarker",
    "SpeechMarkerRealization",
    "SpeechMetrics",
    "SpeechOutcome",
    "SpeechOutcomeStatus",
    "SpeechProvider",
    "SpeechRequest",
    "SpeechSegment",
    "SpeechService",
    "SpeechTelemetry",
    "SpeechUsage",
    "TextFallback",
    "VoiceKind",
    "VoiceState",
    "is_retryable",
    "normalize_text",
]
