"""OmniVoice HTTP adapter — a **prototype**, not the decided provider.

``DEC-TECH-007`` (TTS/OmniVoice deployment and GPU capacity) is ``OPEN`` and
``ADR-P007`` is ``PROPOSED``. ``AI_IMPLEMENTATION_GUIDE.md``: *"PROPOSED technology
ADRs may be prototyped but MUST NOT be represented as accepted architecture."* So
this adapter is opt-in (``MENTORA_TTS_PROVIDER=omnivoice``), the default stays the
deterministic neutral mock, and it reports ``kind`` ``PROTOTYPE``.

It talks to the local sidecar in ``tools/omnivoice_server/server.py`` (which owns
PyTorch and the model) over plain HTTP using the stdlib, so the backend gains no
dependency. The sidecar answers raw 16-bit mono PCM at 24 kHz; this adapter reads
it in ~100 ms frames and yields them as :class:`SpeechChunk` s, honouring the
cancel token and the end-to-end deadline between frames. Everything else —
reservation bounds, retry, circuit breaker, text fallback — is the port's and the
service's, unchanged.
"""

from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
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

OMNIVOICE_SAMPLE_RATE = 24_000
DEFAULT_OMNIVOICE_URL = "http://127.0.0.1:8765"
#: A diffusion TTS on a laptop GPU is far slower than the mock; one sentence on an
#: M1 with 16 steps is a few seconds, the first call longer.
DEFAULT_OMNIVOICE_DEADLINE_SECONDS = 60.0


@dataclass(frozen=True)
class OmniVoiceSettings:
    base_url: str = DEFAULT_OMNIVOICE_URL
    deadline_seconds: float = DEFAULT_OMNIVOICE_DEADLINE_SECONDS

    @classmethod
    def from_env(cls) -> "OmniVoiceSettings":
        return cls(
            base_url=os.environ.get("MENTORA_OMNIVOICE_URL", DEFAULT_OMNIVOICE_URL).rstrip("/"),
            deadline_seconds=float(
                os.environ.get("MENTORA_OMNIVOICE_DEADLINE_SECONDS", DEFAULT_OMNIVOICE_DEADLINE_SECONDS)
            ),
        )


def omnivoice_config(settings: OmniVoiceSettings) -> SpeechConfig:
    return SpeechConfig(
        sample_rate=OMNIVOICE_SAMPLE_RATE,
        bytes_per_sample=2,
        deadline_seconds=settings.deadline_seconds,
        # Real speech: roughly 15 characters per second, used only for estimates.
        characters_per_second=15.0,
        # The GPU runs one generation at a time; do not stack retries on it.
        max_attempts=1,
    )


class OmniVoiceSpeechProvider(SpeechProvider):
    """Synthesize through a local OmniVoice sidecar (prototype; DEC-TECH-007 OPEN)."""

    provider_id = "omnivoice"
    provider_version = "0.1.0-prototype"
    provider_kind = "PROTOTYPE"

    def __init__(
        self,
        settings: Optional[OmniVoiceSettings] = None,
        config: Optional[SpeechConfig] = None,
        *,
        opener=urllib.request.urlopen,
    ) -> None:
        self.settings = settings or OmniVoiceSettings.from_env()
        super().__init__(config or omnivoice_config(self.settings))
        self._voice_id = self.config.voice_id or NEUTRAL_VOICE_ID
        self._open = opener
        self._reservation_sequence = 0

    # -- port --------------------------------------------------------------------
    def authorize_voice(self, voice_id: str) -> AuthorizedVoice:
        # The sidecar speaks one fixed voice; the platform still addresses it as
        # the neutral voice. Authorized cloned voices are V1.
        if voice_id == self._voice_id:
            return AuthorizedVoice(voice_id=voice_id, authorized=True, kind=VoiceKind.NEUTRAL)
        return AuthorizedVoice(voice_id=voice_id, authorized=False, reason="NOT_NEUTRAL")

    def _reserve(self, request: ReservationRequest) -> Reservation:
        self._reservation_sequence += 1
        now = time.monotonic()
        return Reservation(
            reservation_id=f"{self.provider_id}-{self._reservation_sequence}",
            voice_id=request.voice_id,
            provider=self.provider_id,
            capacity_units=1,
            expires_at=now + max(0.0, request.ttl_seconds),
            issued_at=now,
        )

    def _release(self, reservation: Reservation) -> None:
        return None

    def _stream(
        self, request: SpeechRequest, token: CancelToken, budget: SpeechBudget
    ) -> Iterator[SpeechChunk]:
        text = normalize_text(request.text)
        body = json.dumps({"text": text, "language": request.language}).encode("utf-8")
        http_request = urllib.request.Request(
            f"{self.settings.base_url}/synthesize",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        timeout = max(1.0, float(self.config.deadline_seconds))
        try:
            response = self._open(http_request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            code = SpeechErrorCode.INVALID_REQUEST if exc.code == 400 else SpeechErrorCode.SYNTHESIS_FAILED
            raise SpeechError(code, f"OmniVoice answered HTTP {exc.code}") from exc
        except (socket.timeout, TimeoutError) as exc:
            raise SpeechError(SpeechErrorCode.SYNTHESIS_TIMEOUT, "OmniVoice timed out") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise SpeechError(
                SpeechErrorCode.PROVIDER_UNAVAILABLE,
                f"OmniVoice sidecar is unreachable at {self.settings.base_url}",
            ) from exc

        frame_bytes = OMNIVOICE_SAMPLE_RATE // 10 * 2  # ~100 ms of 16-bit mono
        sequence = 0
        pending: Optional[bytes] = None
        markers = tuple(marker.marker_id for marker in request.marker_plan.ordered())
        with response:
            while True:
                if token.cancelled:
                    return
                if budget.expired():
                    raise SpeechError(SpeechErrorCode.SYNTHESIS_TIMEOUT, "deadline exceeded")
                try:
                    data = response.read(frame_bytes)
                except (socket.timeout, TimeoutError) as exc:
                    raise SpeechError(SpeechErrorCode.SYNTHESIS_TIMEOUT, "OmniVoice timed out") from exc
                if pending is not None:
                    yield self._chunk(request, sequence, pending, final=not data,
                                      marker_ids=markers if sequence == 0 else ())
                    sequence += 1
                if not data:
                    break
                pending = data
        if sequence == 0:
            raise SpeechError(SpeechErrorCode.SYNTHESIS_FAILED, "OmniVoice returned no audio")

    # -- internals ---------------------------------------------------------------
    def _chunk(
        self, request: SpeechRequest, sequence: int, audio: bytes, *, final: bool,
        marker_ids: tuple[str, ...],
    ) -> SpeechChunk:
        # Keep 16-bit frames aligned so a frame boundary never splits a sample.
        if len(audio) % 2:
            audio = audio[:-1]
        return SpeechChunk(
            generation=request.generation,
            sequence=sequence,
            audio=audio,
            duration_ms=int(len(audio) / 2 / OMNIVOICE_SAMPLE_RATE * 1000),
            final=final,
            marker_ids=marker_ids,
        )

    def probe(self, timeout: float = 2.0) -> dict:
        """The sidecar's ``/health`` (used for diagnostics, never on the hot path)."""

        with self._open(f"{self.settings.base_url}/health", timeout=timeout) as response:
            return json.loads(response.read() or b"{}")


__all__ = [
    "DEFAULT_OMNIVOICE_URL",
    "OmniVoiceSettings",
    "OmniVoiceSpeechProvider",
    "omnivoice_config",
]
