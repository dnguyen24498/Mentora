"""The neutral-voice domain service (V0-012).

Where :mod:`app.speech.port` owns the *universal transition contract* for one
provider, this service owns the *lesson-level* routing that no single provider can
decide: reserve capacity, attempt the requested voice, route a refused voice to the
neutral voice, and — if speech still cannot be produced inside its deadline — fall
back to **text** so the lesson always continues
(``docs/state-machines/TEACHER_VOICE_STATE_MACHINE.md``: *"Failure routes alternate
provider/neutral voice/text"*; ``DEC-TURN-009``).

The service is deliberately synchronous and provider-agnostic. It holds no
classroom state and never decides *whether* to speak, only *how* one already-decided
utterance is produced — the Classroom Actor owns that decision (``DEC-RUNTIME-001``),
the Teacher Orchestrator owns the pedagogy (``DEC-RUNTIME-002``).

This module imports only ``app.speech`` and the stdlib, so the domain never depends
on an adapter or a vendor SDK.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Optional

from app.speech.errors import SpeechError, SpeechErrorCode
from app.speech.models import (
    DEFAULT_RESERVATION_TTL_SECONDS,
    CancelAck,
    MarkerPlan,
    NEUTRAL_VOICE_ID,
    ProviderHealth,
    ReservationRequest,
    SpeechChunk,
    SpeechConfig,
    SpeechOutcome,
    SpeechOutcomeStatus,
    SpeechRequest,
    SpeechSegment,
    SpeechUsage,
    TextFallback,
)
from app.speech.port import CancelToken, SpeechBudget, SpeechProvider
from app.speech.telemetry import SpeechTelemetry


class SpeechService:
    """Produce one utterance through a replaceable provider, with neutral/text fallback."""

    def __init__(
        self,
        provider: SpeechProvider,
        *,
        config: Optional[SpeechConfig] = None,
        telemetry: Optional[SpeechTelemetry] = None,
    ) -> None:
        self.provider = provider
        self.config = config or provider.config
        self.telemetry = telemetry or SpeechTelemetry()
        self._usage = SpeechUsage()

    # -- the one operation a caller needs ----------------------------------------
    def speak(
        self,
        request: SpeechRequest,
        *,
        on_chunk: Optional[Callable[[SpeechChunk], None]] = None,
        cancel: Optional[CancelToken] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> SpeechOutcome:
        """Produce ``request``; a refusal or failure never raises out of here.

        Every terminal path emits telemetry and returns a user-visible outcome: a
        completed segment with audio, a cancellation, or a text fallback. The
        reservation is released on every path (best effort) so a failed utterance
        cannot leak capacity.
        """

        budget_kwargs = {"max_attempts": self.config.max_attempts}
        if clock is not None:
            budget_kwargs["clock"] = clock
        budget = SpeechBudget(request.deadline_seconds, **budget_kwargs)

        try:
            reservation = self.provider.reserve(
                ReservationRequest(
                    voice_id=request.voice_id,
                    estimated_characters=len(request.text),
                    institution_id=request.institution_id,
                    ttl_seconds=self.config.reservation_ttl_seconds
                    or DEFAULT_RESERVATION_TTL_SECONDS,
                )
            )
        except SpeechError as exc:
            self.telemetry.record_reservation_denied(
                institution_id=request.institution_id, generation=request.generation, code=exc.code
            )
            return self._fallback(request, exc.code, reservation_id=None)

        self.telemetry.record_reserved(
            institution_id=request.institution_id,
            reservation=reservation.to_dict(),
            generation=request.generation,
        )
        try:
            return self._synthesize(request, reservation.reservation_id, budget, on_chunk, cancel)
        finally:
            self.provider.release(reservation.reservation_id)
            self.telemetry.record_released(
                institution_id=request.institution_id,
                reservation_id=reservation.reservation_id,
            )

    # -- cancellation passthrough (idempotent) -----------------------------------
    def cancel(self, generation: int, *, institution_id: Optional[str] = None) -> CancelAck:
        ack = self.provider.cancel(generation)
        self.telemetry.record_cancel(institution_id=institution_id, ack=ack.to_dict())
        return ack

    def health(self) -> ProviderHealth:
        return self.provider.health()

    def usage(self) -> SpeechUsage:
        """Aggregated usage/cost across every completed synthesis."""

        return self._usage

    # -- internals ---------------------------------------------------------------
    def _synthesize(
        self,
        request: SpeechRequest,
        reservation_id: str,
        budget: SpeechBudget,
        on_chunk: Optional[Callable[[SpeechChunk], None]],
        cancel: Optional[CancelToken],
    ) -> SpeechOutcome:
        attempt = self._attempt(request, reservation_id, budget, on_chunk, cancel)
        if isinstance(attempt, SpeechError):
            return self._fallback(request, attempt.code, reservation_id)
        return self._from_segment(request, attempt, reservation_id)

    def _attempt(
        self,
        request: SpeechRequest,
        reservation_id: str,
        budget: SpeechBudget,
        on_chunk: Optional[Callable[[SpeechChunk], None]],
        cancel: Optional[CancelToken],
    ) -> "SpeechSegment | SpeechError":
        """Attempt the requested voice, then the neutral voice on a voice refusal."""

        attempt = self._invoke(request, reservation_id, budget, on_chunk, cancel)
        if (
            isinstance(attempt, SpeechError)
            and attempt.code is SpeechErrorCode.VOICE_NOT_AUTHORIZED
            and request.voice_id != NEUTRAL_VOICE_ID
        ):
            # Neutral voice is the fallback for a refused voice.
            self.telemetry.record_voice_fallback(
                institution_id=request.institution_id,
                generation=request.generation,
                from_voice=request.voice_id,
                to_voice=NEUTRAL_VOICE_ID,
            )
            neutral = replace(request, voice_id=NEUTRAL_VOICE_ID)
            attempt = self._invoke(neutral, reservation_id, budget, on_chunk, cancel)
        return attempt

    def _invoke(
        self,
        request: SpeechRequest,
        reservation_id: str,
        budget: SpeechBudget,
        on_chunk: Optional[Callable[[SpeechChunk], None]],
        cancel: Optional[CancelToken],
    ) -> "SpeechSegment | SpeechError":
        bound = request if request.reservation_id else replace(
            request, reservation_id=reservation_id
        )
        try:
            return self.provider.synthesize(
                bound, budget=budget, cancel=cancel, on_chunk=on_chunk
            )
        except SpeechError as exc:
            return exc

    def _from_segment(
        self, request: SpeechRequest, segment: SpeechSegment, reservation_id: str
    ) -> SpeechOutcome:
        self.telemetry.record_segment(
            institution_id=request.institution_id,
            generation=request.generation,
            segment=segment,
            provider=self.provider.provider_id,
        )
        if segment.completed:
            self._usage = self._usage.add(segment.usage)
            outcome = SpeechOutcome(
                status=SpeechOutcomeStatus.COMPLETED,
                generation=request.generation,
                reservation_id=reservation_id,
                segment=segment,
                attempts=segment.attempts,
            )
        elif segment.cancelled:
            outcome = SpeechOutcome(
                status=SpeechOutcomeStatus.CANCELLED,
                generation=request.generation,
                reservation_id=reservation_id,
                segment=segment,
                error_code=SpeechErrorCode.CANCELLED,
                attempts=segment.attempts,
            )
        else:
            return self._fallback(
                request,
                segment.error_code or SpeechErrorCode.SYNTHESIS_FAILED,
                reservation_id,
                attempts=segment.attempts,
            )
        self.telemetry.record_outcome(
            institution_id=request.institution_id,
            generation=request.generation,
            status=outcome.status,
        )
        return outcome

    def _fallback(
        self,
        request: SpeechRequest,
        code: SpeechErrorCode,
        reservation_id: Optional[str],
        *,
        attempts: int = 1,
    ) -> SpeechOutcome:
        self.telemetry.record_text_fallback(
            institution_id=request.institution_id,
            generation=request.generation,
            code=code,
            characters=len(request.text),
        )
        plan: MarkerPlan = request.marker_plan
        outcome = SpeechOutcome(
            status=SpeechOutcomeStatus.FALLBACK,
            generation=request.generation,
            reservation_id=reservation_id,
            fallback=TextFallback(
                text=request.text,
                language=request.language,
                markers=plan.markers,
                reason=code,
            ),
            error_code=code,
            attempts=attempts,
        )
        self.telemetry.record_outcome(
            institution_id=request.institution_id,
            generation=request.generation,
            status=outcome.status,
        )
        return outcome


__all__ = ["SpeechService"]
