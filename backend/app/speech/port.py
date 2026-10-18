"""The provider-neutral ``SpeechProvider`` port (V0-012).

``docs/providers/TTS_VOICE_PROVIDER.md``: *"authorize voice, reserve, synthesize
normalized text with marker plan and generation, stream, cancel generation,
release, health/cost. Neutral fallback required."* ``docs/architecture/
19_RELIABILITY_SLO_AND_BACKPRESSURE.md``: *"reserve scarce capabilities before
granting user-visible permission. Bound queues ... Propagate end-to-end
deadline/cancellation. Retry transient idempotent work only. Circuit breakers
trigger ... neutral voice, text ..."* This ABC is that contract.

**The provider technology is not decided.** ``DEC-TECH-007`` ("TTS/OmniVoice
deployment and GPU capacity") is ``OPEN``, so ``docs/adr/proposed/
ADR-P007_TTS_OMNIVOICE.md`` applies: *"Until accepted, provider-neutral interfaces
and mocks are used."* This module is the interface;
``app/providers/deterministic.py`` is the dependency-free local implementation, and
it is reported as ``neutral-deterministic@1.0.0`` — never as a vendor provider.

The split of responsibility is like the renderer's (``renderers/base.py``): the
**adapter** implements the minimum that only it can know (authorize a voice, take
and give back capacity, produce chunks), while this base owns the *universal
transition contract* every capability must honour — admission control, the
end-to-end deadline, cooperative cancellation, idempotent cancel acknowledgements,
bounded retry, per-generation terminal verdicts, usage and circuit-breaker state —
so no adapter can accidentally skip one.

A *refusal* (malformed request, unauthorized voice, open circuit, refused
reservation) raises :class:`~app.speech.errors.SpeechError`. An *attempt outcome*
(a timeout, a provider error, a cancellation, a completed stream) is a
:class:`~app.speech.models.SpeechSegment` with a terminal ``status`` — the
difference matters because a refusal means "no work was attempted", which is not
the same thing as "the attempt failed".

This module imports only ``app.speech`` and the stdlib, so the domain never
depends on an adapter or a vendor SDK.
"""

from __future__ import annotations

import hashlib
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import replace
from typing import Callable, ClassVar, Iterator, Optional

from app.speech.errors import SpeechError, SpeechErrorCode
from app.speech.models import (
    AuthorizedVoice,
    CancelAck,
    ProviderHealth,
    ProviderIdentity,
    Reservation,
    ReservationRequest,
    SpeechChunk,
    SpeechConfig,
    SpeechMarkerRealization,
    SpeechRequest,
    SpeechSegment,
    SpeechUsage,
    VoiceState,
    normalize_text,
)


class CancelToken:
    """Cooperative cancellation flag, safe to set from another thread."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


class SpeechBudget:
    """End-to-end deadline and retry budget (``DEC-RELIABILITY-001``).

    The clock is injected so timeout behaviour is deterministic in tests instead of
    depending on wall-clock sleeps.
    """

    def __init__(
        self,
        deadline_seconds: float,
        *,
        max_attempts: int = 1,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock = clock
        self.deadline_seconds = deadline_seconds
        self.max_attempts = max(1, max_attempts)
        self._started_at = clock()
        self._deadline = self._started_at + max(0.0, deadline_seconds)

    def elapsed(self) -> float:
        return self._clock() - self._started_at

    def remaining(self) -> float:
        return self._deadline - self._clock()

    def expired(self) -> bool:
        return self._clock() >= self._deadline

    def duration_ms(self) -> int:
        return int(self.elapsed() * 1000)


class SpeechProvider(ABC):
    """Replaceable neutral-voice capability.

    Implementations must be **deterministic for a fixed ``(request, config)``** so a
    retry or a recompile cannot change the audio, and must not require the caller to
    know anything about a vendor.
    """

    provider_id: ClassVar[str] = "speech-provider"
    provider_version: ClassVar[str] = "0.0.0"

    def __init__(self, config: Optional[SpeechConfig] = None) -> None:
        self.config = config or SpeechConfig()
        self._lock = threading.Lock()
        self._active_tokens: dict[int, CancelToken] = {}
        self._cancel_acks: dict[int, CancelAck] = {}
        #: Terminal verdicts, keyed by generation: the idempotency memory.
        self._segments: dict[int, SpeechSegment] = {}
        self._held: dict[str, Reservation] = {}
        self._in_flight = 0
        self._total_synthesized = 0
        self._total_failed = 0
        self._total_cancelled = 0
        self._consecutive_failures = 0
        self._last_error: Optional[str] = None

    # -- what only an adapter can answer -----------------------------------------
    @abstractmethod
    def authorize_voice(self, voice_id: str) -> AuthorizedVoice:
        """Decide whether this platform may synthesize in ``voice_id``."""

    @abstractmethod
    def _reserve(self, request: ReservationRequest) -> Reservation:
        """Allocate one reservation (the base bounds how many may be held)."""

    @abstractmethod
    def _release(self, reservation: Reservation) -> None:
        """Return a reservation's capacity to the provider (best effort)."""

    @abstractmethod
    def _stream(
        self, request: SpeechRequest, token: CancelToken, budget: SpeechBudget
    ) -> Iterator[SpeechChunk]:
        """Yield the audio chunks of one generation, honouring ``token``/``budget``."""

    # -- provenance --------------------------------------------------------------
    def identity(self) -> ProviderIdentity:
        return ProviderIdentity(
            name=self.provider_id,
            version=self.provider_version,
            data_region=self.config.data_region,
            config_hash=self.config.config_hash(),
        )

    # -- reservation/release (admission control) ---------------------------------
    def reserve(self, request: ReservationRequest) -> Reservation:
        """Take one unit of capacity, or refuse (``RESERVATION_DENIED``).

        Speech is scarce, so capacity is reserved *before* any user-visible
        permission is granted. The refusal is classified and raises before any
        work, so a caller can fall back without side effects.
        """

        if request.estimated_characters > self.config.max_characters:
            raise SpeechError(
                SpeechErrorCode.INVALID_REQUEST,
                f"estimated {request.estimated_characters} characters exceeds "
                f"{self.config.max_characters}",
            )
        with self._lock:
            if len(self._held) >= max(1, self.config.max_concurrent_reservations):
                raise SpeechError(
                    SpeechErrorCode.RESERVATION_DENIED,
                    "speech capacity exhausted; retry or fall back",
                )
            reservation = self._reserve(request)
            self._held[reservation.reservation_id] = reservation
            return reservation

    def release(self, reservation_id: str) -> None:
        """Return capacity, idempotently and without ever raising.

        A release failure must not mask the synthesis outcome, and the reservation
        has a bounded lifetime anyway, so a provider error here is *recorded*, not
        propagated. Releasing an unknown or already-released reservation is a no-op.
        """

        with self._lock:
            reservation = self._held.pop(reservation_id, None)
        if reservation is None:
            return
        try:
            self._release(reservation)
        except Exception as exc:  # pragma: no cover - defensive; adapters are local
            with self._lock:
                self._last_error = f"release failed: {exc}"

    # -- cancellation (idempotent ACK) -------------------------------------------
    def cancel(self, generation: int) -> CancelAck:
        """Request cancellation; replayed cancels return the stored acknowledgement.

        ``DEC-RUNTIME-003``: a repeated cancel must not produce a second side
        effect, so the first acknowledgement is remembered and returned with
        ``duplicate: true``.
        """

        with self._lock:
            token = self._active_tokens.get(generation)
            if token is not None:
                token.cancel()
                ack = CancelAck(
                    generation=generation,
                    acknowledged=True,
                    duplicate=False,
                    status=VoiceState.CANCELLING.value,
                )
                self._cancel_acks[generation] = ack
                return ack
            prior = self._cancel_acks.get(generation)
            if prior is not None:
                return replace(prior, duplicate=True)
            segment = self._segments.get(generation)
            if segment is not None:
                # Nothing left to cancel; report the terminal state it reached.
                return CancelAck(
                    generation=generation,
                    acknowledged=False,
                    duplicate=False,
                    status=segment.status.value,
                )
            return CancelAck(
                generation=generation,
                acknowledged=False,
                duplicate=False,
                status=VoiceState.IDLE.value,
            )

    # -- synthesis (deadline, cancellation, bounded retry) -----------------------
    def synthesize(
        self,
        request: SpeechRequest,
        *,
        budget: SpeechBudget,
        cancel: Optional[CancelToken] = None,
        on_chunk: Optional[Callable[[SpeechChunk], None]] = None,
    ) -> SpeechSegment:
        """Synthesize one generation and return its terminal verdict.

        Streaming is exposed as the ``on_chunk`` sink *and* a returned summary, so a
        caller can push audio onward as it arrives while still getting a single
        classified outcome. Bounded retry is applied here so it is identical for
        every adapter: only classified-retryable failures are retried, at most
        ``budget.max_attempts`` times, never past the deadline, and — because a
        stream that already emitted audio cannot be un-emitted — **only before the
        first chunk**.
        """

        self._validate(request)

        with self._lock:
            existing = self._segments.get(request.generation)
            if existing is not None:
                # Idempotent replay: the terminal verdict is returned unchanged.
                return existing
            if self._consecutive_failures >= self.config.circuit_failure_threshold:
                raise SpeechError(
                    SpeechErrorCode.PROVIDER_UNAVAILABLE,
                    f"circuit open after {self._consecutive_failures} consecutive failures",
                )
            token = cancel or CancelToken()
            self._active_tokens[request.generation] = token
            self._in_flight += 1

        attempts = 0
        segment: SpeechSegment
        try:
            while True:
                attempts += 1
                segment = self._attempt(request, token, budget, on_chunk)
                if not segment.failed or not segment.retryable:
                    break
                if attempts >= budget.max_attempts:
                    break
                if budget.expired() or token.cancelled:
                    break
                if segment.chunk_count:
                    # Audio already left this attempt; a retry would duplicate it.
                    break
            segment = replace(segment, attempts=attempts)
        finally:
            with self._lock:
                self._active_tokens.pop(request.generation, None)
                self._in_flight -= 1
                self._segments[request.generation] = segment
                self._record(segment)

        return segment

    # -- health/usage ------------------------------------------------------------
    def health(self) -> ProviderHealth:
        with self._lock:
            return self._health_locked()

    def last_segment(self, generation: int) -> Optional[SpeechSegment]:
        """The stored terminal verdict for ``generation``, if one exists."""

        with self._lock:
            return self._segments.get(generation)

    # -- shared internals --------------------------------------------------------
    def _validate(self, request: SpeechRequest) -> None:
        if request.generation < 1:
            raise SpeechError(SpeechErrorCode.INVALID_REQUEST, "generation must be >= 1")
        normalized = normalize_text(request.text)
        if not normalized:
            raise SpeechError(SpeechErrorCode.INVALID_REQUEST, "text must not be empty")
        if len(request.text) > self.config.max_characters:
            raise SpeechError(
                SpeechErrorCode.INVALID_REQUEST,
                f"text exceeds {self.config.max_characters} characters",
            )
        # Markers index into the normalized text, so validate against it.
        request.marker_plan.validate(normalized)
        authorization = self.authorize_voice(request.voice_id)
        if not authorization.authorized:
            raise SpeechError(
                SpeechErrorCode.VOICE_NOT_AUTHORIZED,
                f"voice {request.voice_id!r} is not authorized "
                f"({authorization.reason or 'unknown'})",
            )

    def _attempt(
        self,
        request: SpeechRequest,
        token: CancelToken,
        budget: SpeechBudget,
        on_chunk: Optional[Callable[[SpeechChunk], None]],
    ) -> SpeechSegment:
        """One attempt: stream, with the deadline cancelled between chunks."""

        if token.cancelled:
            return self._cancelled(request)
        if budget.expired():
            return self._failed(request, SpeechErrorCode.SYNTHESIS_TIMEOUT, "deadline exceeded")

        chunk_count = 0
        audio_bytes = 0
        duration_ms = 0
        markers: list[SpeechMarkerRealization] = []
        emitted_ms = 0
        try:
            for chunk in self._stream(request, token, budget):
                if token.cancelled:
                    return self._cancelled(
                        request, chunk_count=chunk_count, audio_bytes=audio_bytes, markers=markers
                    )
                if budget.expired():
                    return self._failed(
                        request,
                        SpeechErrorCode.SYNTHESIS_TIMEOUT,
                        "deadline exceeded during synthesis",
                        chunk_count=chunk_count,
                        audio_bytes=audio_bytes,
                        markers=markers,
                    )
                for marker_id in chunk.marker_ids:
                    markers.append(
                        SpeechMarkerRealization(
                            marker_id=marker_id,
                            offset_ms=emitted_ms,
                            chunk_sequence=chunk.sequence,
                        )
                    )
                chunk_count += 1
                audio_bytes += chunk.byte_size
                emitted_ms += max(0, chunk.duration_ms)
                duration_ms += max(0, chunk.duration_ms)
                if on_chunk is not None:
                    on_chunk(chunk)
        except SpeechError as exc:
            return self._failed(
                request,
                exc.code,
                exc.message,
                chunk_count=chunk_count,
                audio_bytes=audio_bytes,
                markers=markers,
            )
        except Exception as exc:  # a vendor error is classified, never leaked
            return self._failed(
                request,
                SpeechErrorCode.SYNTHESIS_FAILED,
                str(exc),
                chunk_count=chunk_count,
                audio_bytes=audio_bytes,
                markers=markers,
            )

        return SpeechSegment(
            generation=request.generation,
            status=VoiceState.COMPLETED,
            voice_id=request.voice_id,
            chunk_count=chunk_count,
            audio_bytes=audio_bytes,
            duration_ms=duration_ms,
            markers=tuple(markers),
            sample_rate=self.config.sample_rate,
            bytes_per_sample=self.config.bytes_per_sample,
            channels=1,
            usage=SpeechUsage(
                characters=len(normalize_text(request.text)),
                audio_ms=duration_ms,
                audio_bytes=audio_bytes,
                cost_units=0.0,
                data_region=self.config.data_region,
            ),
        )

    def _failed(
        self,
        request: SpeechRequest,
        code: SpeechErrorCode,
        message: str,
        *,
        chunk_count: int = 0,
        audio_bytes: int = 0,
        markers: Optional[list[SpeechMarkerRealization]] = None,
    ) -> SpeechSegment:
        return SpeechSegment(
            generation=request.generation,
            status=VoiceState.FAILED,
            voice_id=request.voice_id,
            chunk_count=chunk_count,
            audio_bytes=audio_bytes,
            markers=tuple(markers or ()),
            error_code=code,
            error_message=message,
        )

    def _cancelled(
        self,
        request: SpeechRequest,
        *,
        chunk_count: int = 0,
        audio_bytes: int = 0,
        markers: Optional[list[SpeechMarkerRealization]] = None,
    ) -> SpeechSegment:
        return SpeechSegment(
            generation=request.generation,
            status=VoiceState.CANCELLED,
            voice_id=request.voice_id,
            chunk_count=chunk_count,
            audio_bytes=audio_bytes,
            markers=tuple(markers or ()),
            error_code=SpeechErrorCode.CANCELLED,
            error_message="generation cancelled",
        )

    def _record(self, segment: SpeechSegment) -> None:
        """Circuit-breaker and counter bookkeeping (caller holds the lock)."""

        if segment.status is VoiceState.FAILED:
            self._total_failed += 1
            self._consecutive_failures += 1
            self._last_error = segment.error_message
        elif segment.status is VoiceState.CANCELLED:
            self._total_cancelled += 1
            self._consecutive_failures = 0
        elif segment.status is VoiceState.COMPLETED:
            self._total_synthesized += 1
            self._consecutive_failures = 0

    def _health_locked(self) -> ProviderHealth:
        if self._consecutive_failures >= self.config.circuit_failure_threshold:
            state = "open"
        elif self._consecutive_failures:
            state = "half_open"
        else:
            state = "closed"
        return ProviderHealth(
            healthy=state != "open",
            provider=self.provider_id,
            voice_id=self.config.voice_id,
            region=self.config.data_region,
            state=state,
            consecutive_failures=self._consecutive_failures,
            in_flight=self._in_flight,
            capacity_units=max(0, self.config.max_concurrent_reservations - len(self._held)),
            reservations_held=len(self._held),
            total_synthesized=self._total_synthesized,
            total_failed=self._total_failed,
            total_cancelled=self._total_cancelled,
            last_error=self._last_error,
        )

    @staticmethod
    def deterministic_id(*parts: object) -> str:
        """A stable id derived from its inputs (no clock, no randomness)."""

        payload = "\u001f".join(str(part) for part in parts)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


__all__ = ["CancelToken", "SpeechBudget", "SpeechProvider"]
