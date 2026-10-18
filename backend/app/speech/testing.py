"""Deterministic test double for the neutral voice capability (V0-012).

``docs/providers/TTS_VOICE_PROVIDER.md`` requires every capability to expose a
*test double*. This one reproduces the modes the service and the reliability
contract care about — a normal stream, a permanent provider error, a transient
error (bounded retry), a deadline overrun, a cancellation mid-stream — with no I/O
and no clock of its own.

It is deliberately separate from the shipped adapter
(``app/providers/deterministic.py``): the adapter is the deterministic local
implementation the platform runs with, while this double is *scripted* to fail on
cue, which is what the timeout/error/retry tests need.
"""

from __future__ import annotations

from typing import Callable, Iterator, Optional

from app.speech.errors import SpeechError, SpeechErrorCode
from app.speech.models import (
    NEUTRAL_VOICE_ID,
    AuthorizedVoice,
    Reservation,
    ReservationRequest,
    SpeechChunk,
    SpeechConfig,
    SpeechRequest,
    VoiceKind,
    normalize_text,
)
from app.speech.port import CancelToken, SpeechBudget, SpeechProvider


class ScriptedSpeechProvider(SpeechProvider):
    """A provider whose every outcome can be scripted (no I/O, no sleeps)."""

    provider_id = "scripted-speech"
    provider_version = "0.0.0"

    def __init__(
        self,
        *,
        config: Optional[SpeechConfig] = None,
        chunk_count: int = 3,
        chunk_characters: int = 6,
        duration_ms_per_chunk: int = 20,
        fail_after_chunks: Optional[int] = None,
        fail_code: SpeechErrorCode = SpeechErrorCode.SYNTHESIS_FAILED,
        raise_immediately: Optional[SpeechErrorCode] = None,
        cancel_after_chunks: Optional[int] = None,
        clock: Optional[Callable[[], float]] = None,
        advance_per_chunk: float = 0.0,
        authorized_voices: tuple[str, ...] = (NEUTRAL_VOICE_ID,),
    ) -> None:
        super().__init__(config)
        self.chunk_count = max(1, chunk_count)
        self.chunk_characters = max(1, chunk_characters)
        self.duration_ms_per_chunk = duration_ms_per_chunk
        self.fail_after_chunks = fail_after_chunks
        self.fail_code = fail_code
        self.raise_immediately = raise_immediately
        self.cancel_after_chunks = cancel_after_chunks
        self.clock = clock
        self.advance_per_chunk = advance_per_chunk
        self.authorized_voices = tuple(authorized_voices)
        self.stream_calls = 0
        self._reservation_sequence = 0

    # -- port --------------------------------------------------------------------
    def authorize_voice(self, voice_id: str) -> AuthorizedVoice:
        if voice_id in self.authorized_voices:
            return AuthorizedVoice(voice_id=voice_id, authorized=True, kind=VoiceKind.NEUTRAL)
        return AuthorizedVoice(
            voice_id=voice_id, authorized=False, reason="UNKNOWN_VOICE"
        )

    def _reserve(self, request: ReservationRequest) -> Reservation:
        self._reservation_sequence += 1
        now = self.clock() if self.clock else 0.0
        return Reservation(
            reservation_id=self.deterministic_id(
                self.provider_id,
                self._reservation_sequence,
                request.voice_id,
                request.estimated_characters,
            ),
            voice_id=request.voice_id,
            provider=self.provider_id,
            capacity_units=1,
            expires_at=now + request.ttl_seconds,
            issued_at=now,
        )

    def _release(self, reservation: Reservation) -> None:  # pragma: no cover - no-op
        return None

    def _stream(
        self, request: SpeechRequest, token: CancelToken, budget: SpeechBudget
    ) -> Iterator[SpeechChunk]:
        self.stream_calls += 1
        if self.raise_immediately is not None:
            raise SpeechError(self.raise_immediately, "scripted immediate failure")
        text = normalize_text(request.text)
        markers_by_chunk = self._markers_by_chunk(request)
        for index in range(self.chunk_count):
            if self.clock is not None and self.advance_per_chunk:
                self.clock_advance(self.advance_per_chunk)
            if self.fail_after_chunks is not None and index >= self.fail_after_chunks:
                raise SpeechError(self.fail_code, f"scripted failure after {index} chunks")
            piece = text[index * self.chunk_characters : (index + 1) * self.chunk_characters]
            yield SpeechChunk(
                generation=request.generation,
                sequence=index,
                audio=f"scripted:{request.generation}:{index}".encode("utf-8"),
                duration_ms=self.duration_ms_per_chunk,
                final=index == self.chunk_count - 1,
                marker_ids=markers_by_chunk.get(index, ()),
            )
            if self.cancel_after_chunks is not None and index + 1 >= self.cancel_after_chunks:
                # Simulate a caller cancelling the generation mid-stream.
                token.cancel()

    # -- scripting helpers -------------------------------------------------------
    def clock_advance(self, seconds: float) -> None:
        advance = getattr(self.clock, "advance", None)
        if advance is not None:
            advance(seconds)

    def _markers_by_chunk(self, request: SpeechRequest) -> dict[int, tuple[str, ...]]:
        """One deterministic chunk per marker (order preserved, no duplicates)."""

        assigned: dict[int, list[str]] = {}
        for marker in request.marker_plan.ordered():
            index = min(marker.text_index // self.chunk_characters, self.chunk_count - 1)
            assigned.setdefault(index, []).append(marker.marker_id)
        return {index: tuple(ids) for index, ids in assigned.items()}


__all__ = ["ScriptedSpeechProvider"]
