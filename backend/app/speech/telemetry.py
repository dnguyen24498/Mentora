"""Structured telemetry for the neutral voice capability (V0-012).

``docs/architecture/20_OBSERVABILITY_COST_AND_CAPACITY.md``: propagate tenant,
correlation and provider versions while **redacting sensitive text** — and spoken
teacher speech is authored content, so it is never logged. These records carry
counts, durations, characters, markers and identities only.

``docs/sequences/TTS_FAILURE.md`` asserts *"Every terminal path emits metrics and
user-visible state."* That is why a reservation refusal, a timeout and a text
fallback each emit their own event: the failure paths are observable, not just the
happy path.

Metrics are in-process counters. Per-tenant/per-provider bounded queues and real
queue-depth metrics belong to the job/gateway layer; this module records what the
capability itself observed.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from app.speech.errors import SpeechErrorCode
from app.speech.models import SpeechOutcomeStatus, SpeechSegment, VoiceState

logger = logging.getLogger("mentora.speech")


@dataclass
class SpeechMetrics:
    """Counters for reservations, generations and fallbacks."""

    reservations_granted: int = 0
    reservations_denied: int = 0
    reservations_released: int = 0
    generations_started: int = 0
    generations_completed: int = 0
    generations_failed: int = 0
    generations_cancelled: int = 0
    cancel_acks: int = 0
    cancel_replays: int = 0
    retries: int = 0
    timeouts: int = 0
    voice_fallbacks: int = 0
    text_fallbacks: int = 0
    characters_synthesized: int = 0
    audio_ms_total: int = 0
    cost_units_total: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class SpeechTelemetry:
    """Emits one structured record per outcome and keeps counters."""

    metrics: SpeechMetrics = field(default_factory=SpeechMetrics)
    _logger: logging.Logger = field(default=logger, repr=False)

    def emit(self, event: str, **fields: Any) -> dict[str, Any]:
        record = {"event": event, **fields}
        try:
            self._logger.info(json.dumps(record, sort_keys=True, default=str))
        except (TypeError, ValueError):  # pragma: no cover - telemetry must never break speech
            self._logger.info("event=%s", event)
        return record

    # -- reservation lifecycle ---------------------------------------------------
    def record_reserved(
        self, *, institution_id: Optional[str], reservation: dict, generation: int
    ) -> dict[str, Any]:
        self.metrics.reservations_granted += 1
        return self.emit(
            "speech.reserved",
            institution_id=institution_id,
            reservation_id=reservation.get("reservation_id"),
            provider=reservation.get("provider"),
            voice_id=reservation.get("voice_id"),
            capacity_units=reservation.get("capacity_units"),
            generation=generation,
        )

    def record_reservation_denied(
        self, *, institution_id: Optional[str], generation: int, code: SpeechErrorCode
    ) -> dict[str, Any]:
        self.metrics.reservations_denied += 1
        return self.emit(
            "speech.reservation_denied",
            institution_id=institution_id,
            generation=generation,
            code=code.value,
        )

    def record_released(self, *, institution_id: Optional[str], reservation_id: Optional[str]) -> dict[str, Any]:
        self.metrics.reservations_released += 1
        return self.emit(
            "speech.released",
            institution_id=institution_id,
            reservation_id=reservation_id,
        )

    # -- generation lifecycle ----------------------------------------------------
    def record_segment(
        self,
        *,
        institution_id: Optional[str],
        generation: int,
        segment: SpeechSegment,
        provider: str,
    ) -> dict[str, Any]:
        self.metrics.generations_started += 1
        if segment.status is VoiceState.COMPLETED:
            self.metrics.generations_completed += 1
            self.metrics.characters_synthesized += segment.usage.characters
            self.metrics.audio_ms_total += segment.usage.audio_ms
            self.metrics.cost_units_total += segment.usage.cost_units
        elif segment.status is VoiceState.CANCELLED:
            self.metrics.generations_cancelled += 1
        else:
            self.metrics.generations_failed += 1
        if segment.error_code is SpeechErrorCode.SYNTHESIS_TIMEOUT:
            self.metrics.timeouts += 1
        if segment.attempts > 1:
            self.metrics.retries += segment.attempts - 1
        return self.emit(
            "speech.segment",
            institution_id=institution_id,
            generation=generation,
            provider=provider,
            voice_id=segment.voice_id,
            status=segment.status.value,
            chunk_count=segment.chunk_count,
            audio_bytes=segment.audio_bytes,
            duration_ms=segment.duration_ms,
            markers=len(segment.markers),
            attempts=segment.attempts,
            code=segment.error_code.value if segment.error_code else None,
        )

    def record_cancel(self, *, institution_id: Optional[str], ack: dict) -> dict[str, Any]:
        if ack.get("duplicate"):
            self.metrics.cancel_replays += 1
        else:
            self.metrics.cancel_acks += 1
        return self.emit(
            "speech.cancel",
            institution_id=institution_id,
            generation=ack.get("generation"),
            acknowledged=ack.get("acknowledged"),
            duplicate=ack.get("duplicate"),
            status=ack.get("status"),
        )

    def record_voice_fallback(
        self, *, institution_id: Optional[str], generation: int, from_voice: str, to_voice: str
    ) -> dict[str, Any]:
        self.metrics.voice_fallbacks += 1
        return self.emit(
            "speech.voice_fallback",
            institution_id=institution_id,
            generation=generation,
            from_voice=from_voice,
            to_voice=to_voice,
        )

    def record_text_fallback(
        self, *, institution_id: Optional[str], generation: int, code: SpeechErrorCode, characters: int
    ) -> dict[str, Any]:
        self.metrics.text_fallbacks += 1
        return self.emit(
            "speech.text_fallback",
            institution_id=institution_id,
            generation=generation,
            code=code.value,
            # The utterance is authored speech: record its size, never the text.
            characters=characters,
        )

    def record_outcome(
        self, *, institution_id: Optional[str], generation: int, status: SpeechOutcomeStatus
    ) -> dict[str, Any]:
        return self.emit(
            "speech.outcome",
            institution_id=institution_id,
            generation=generation,
            status=status.value,
        )

    def record_health(self, *, provider: str, health: dict) -> None:
        self.emit("speech.health", provider=provider, **health)


__all__ = ["SpeechMetrics", "SpeechTelemetry"]
