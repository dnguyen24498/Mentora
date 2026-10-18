"""The deterministic neutral-voice adapter and mock (V0-012).

``DEC-TECH-007`` ("TTS/OmniVoice deployment and GPU capacity") is ``OPEN``, so
``docs/adr/proposed/ADR-P007_TTS_OMNIVOICE.md`` applies: *"Until accepted,
provider-neutral interfaces and mocks are used."* This adapter **is** V0's
neutral voice in the meantime — a dependency-free, deterministic local
implementation behind :class:`~app.speech.port.SpeechProvider`:

* **Deterministic.** The audio for a piece of text is a pure function of
  ``(voice_id, language, piece)`` — sha256-seeded PCM frames — so a retry, a re-run
  or a restarted process produces byte-identical output. Nothing about the host (a
  sound card, an installed voice, the wall clock) can change it.
* **Chunked and marker-realizing.** The normalized text is cut into fixed-size
  chunks, and a semantic marker lands on the chunk that contains its text index;
  the millisecond realization it returns is derived output (`DEC-RUNTIME-006`).
* **Local and honest.** It makes no network call and holds no credentials, and it
  is reported as ``neutral-deterministic@1.0.0`` — never as a vendor provider.

It therefore serves two roles the task names at once: the **deterministic mock**
tests and the dev stack use, and the **one neutral adapter** V0 runs with while the
provider decision is OPEN. Fault injection for the reliability tests lives in the
separate scripted double (:class:`app.speech.testing.ScriptedSpeechProvider`).
"""

from __future__ import annotations

import hashlib
import time
from typing import Iterator, Optional

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


def wav_bytes(
    pcm: bytes, *, sample_rate: int, bytes_per_sample: int, channels: int = 1
) -> bytes:
    """Wrap raw PCM in a canonical 44-byte RIFF/WAVE header.

    Exposed so the dev mock (and anything else holding concatenated frames) can
    turn the headerless stream into a playable file without duplicating the layout.
    """

    byte_rate = sample_rate * channels * bytes_per_sample
    block_align = channels * bytes_per_sample
    header = b"RIFF" + (36 + len(pcm)).to_bytes(4, "little") + b"WAVE"
    header += b"fmt " + (16).to_bytes(4, "little") + (1).to_bytes(2, "little")
    header += channels.to_bytes(2, "little") + sample_rate.to_bytes(4, "little")
    header += byte_rate.to_bytes(4, "little") + block_align.to_bytes(2, "little")
    header += (8 * bytes_per_sample).to_bytes(2, "little")
    header += b"data" + len(pcm).to_bytes(4, "little")
    return header + pcm


def _pcm(seed: bytes, samples: int, bytes_per_sample: int) -> bytes:
    """Derive ``samples`` deterministic samples from a 32-byte digest."""

    out = bytearray(samples * bytes_per_sample)
    for index in range(samples):
        value = ((seed[index % 32] << 8) | seed[(index * 7 + 3) % 32]) & 0xFFFF
        for byte in range(bytes_per_sample):
            out[index * bytes_per_sample + byte] = (value >> (8 * byte)) & 0xFF
    return bytes(out)


def chunk_ranges(text: str, size: int) -> list[tuple[int, int]]:
    """Cut ``text`` into contiguous ``[start, end)`` ranges of at most ``size``."""

    size = max(1, size)
    return [(start, min(start + size, len(text))) for start in range(0, len(text), size)]


class DeterministicSpeechProvider(SpeechProvider):
    """The deterministic local neutral-voice adapter (V0's approved temporary mock)."""

    provider_id = "neutral-deterministic"
    provider_version = "1.0.0"

    def __init__(self, config: Optional[SpeechConfig] = None) -> None:
        super().__init__(config)
        # The voice this adapter speaks in is fixed by configuration; a request
        # naming a different voice is refused (neutral-only in V0).
        self._voice_id = self.config.voice_id or NEUTRAL_VOICE_ID
        self._reservation_sequence = 0

    # -- port --------------------------------------------------------------------
    def authorize_voice(self, voice_id: str) -> AuthorizedVoice:
        if voice_id == self._voice_id:
            return AuthorizedVoice(voice_id=voice_id, authorized=True, kind=VoiceKind.NEUTRAL)
        # Only the neutral voice exists in V0; an authorized cloned voice is V1.
        return AuthorizedVoice(voice_id=voice_id, authorized=False, reason="NOT_NEUTRAL")

    def _reserve(self, request: ReservationRequest) -> Reservation:
        # A per-instance sequence keeps two identical asks from colliding on one
        # reservation id (capacity accounting must count real leases), while a
        # fresh provider still reproduces the same id sequence.
        self._reservation_sequence += 1
        now = time.monotonic()
        return Reservation(
            reservation_id=self.deterministic_id(
                self.provider_id,
                self._reservation_sequence,
                request.institution_id or "",
                request.voice_id,
                request.estimated_characters,
            ),
            voice_id=request.voice_id,
            provider=self.provider_id,
            capacity_units=1,
            expires_at=now + max(0.0, request.ttl_seconds),
            issued_at=now,
        )

    def _release(self, reservation: Reservation) -> None:  # pragma: no cover - nothing to free
        return None

    def _stream(
        self, request: SpeechRequest, token: CancelToken, budget: SpeechBudget
    ) -> Iterator[SpeechChunk]:
        text = normalize_text(request.text)
        ranges = chunk_ranges(text, self.config.chunk_characters)
        markers_by_chunk = self._markers_by_chunk(request, ranges, text)
        for index, (start, end) in enumerate(ranges):
            if token.cancelled:
                return
            if budget.expired():
                raise SpeechError(SpeechErrorCode.SYNTHESIS_TIMEOUT, "deadline exceeded")
            piece = text[start:end]
            yield SpeechChunk(
                generation=request.generation,
                sequence=index,
                audio=self._audio_for(request.voice_id, request.language, piece),
                duration_ms=self.config.duration_ms_for(len(piece)),
                final=index == len(ranges) - 1,
                marker_ids=markers_by_chunk.get(index, ()),
            )

    # -- internals ---------------------------------------------------------------
    def _audio_for(self, voice_id: str, language: str, piece: str) -> bytes:
        seed = hashlib.sha256(
            f"{voice_id}\u001f{language}\u001f{piece}".encode("utf-8")
        ).digest()
        samples = len(piece) * self.config.samples_per_character()
        return _pcm(seed, max(1, samples), self.config.bytes_per_sample)

    @staticmethod
    def _markers_by_chunk(
        request: SpeechRequest, ranges: list[tuple[int, int]], text: str
    ) -> dict[int, tuple[str, ...]]:
        """Assign each marker to the chunk that contains its text index."""

        assigned: dict[int, list[str]] = {}
        last = len(ranges) - 1
        for marker in request.marker_plan.ordered():
            index = last if marker.text_index >= len(text) else 0
            if marker.text_index < len(text):
                for position, (start, end) in enumerate(ranges):
                    if start <= marker.text_index < end:
                        index = position
                        break
            assigned.setdefault(index, []).append(marker.marker_id)
        return {index: tuple(ids) for index, ids in assigned.items()}


__all__ = ["DeterministicSpeechProvider", "chunk_ranges", "wav_bytes"]
