"""Provider-neutral speech models (V0-012).

These are the vocabulary of the neutral voice capability described by
``docs/providers/TTS_VOICE_PROVIDER.md`` (*"authorize voice, reserve, synthesize
normalized text with marker plan and generation, stream, cancel generation,
release, health/cost; neutral fallback required"*) and
``docs/state-machines/TEACHER_VOICE_STATE_MACHINE.md``.

Three decisions are load-bearing:

* **Generations are the idempotency key.** Every request names a ``generation``
  (``DEC-RUNTIME-003``: *"commands and externally visible side effects are
  idempotent"*), so a replayed synthesis returns its stored terminal verdict and a
  replayed cancel returns its stored acknowledgement. A *new* utterance is a
  *new* generation (``DEC-RUNTIME-005``: resume creates a new semantic segment),
  never a re-run of an old one.
* **Markers are semantic, not millisecond offsets.** A :class:`MarkerPlan` attaches
  markers to *character positions in the normalized text* (``DEC-RUNTIME-006``:
  *"semantic speech markers are preferred to fixed millisecond offsets"*). The
  millisecond :class:`SpeechMarkerRealization` a provider returns is *derived*
  output, never the source of truth, so a re-synthesis can move it without the
  lesson changing.
* **Only the neutral voice exists in V0.** ``VoiceKind`` has one member; cloned
  voice (consent/scope/expiry/revocation) is explicitly out of scope and is
  refused by :meth:`~app.speech.port.SpeechProvider.authorize_voice` rather than
  modelled, so nothing here implies a consent workflow that does not exist.

This module is stdlib-only and imports nothing outside ``app.speech``.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from app.speech.errors import RETRYABLE_SPEECH_CODES, SpeechError, SpeechErrorCode

#: The one voice this platform may use without an authorized clone. It is the
#: neutral fallback every other route lands on.
NEUTRAL_VOICE_ID = "mentora-neutral"

DEFAULT_LANGUAGE = "en"
DEFAULT_DATA_REGION = "local"
#: Bounded end-to-end deadline (``DEC-RELIABILITY-001``). A synthesis that cannot
#: finish inside this is classified and the lesson continues on the text fallback
#: rather than waiting.
DEFAULT_DEADLINE_SECONDS = 5.0
#: Bounded retry: a transient failure is retried at most this many times.
DEFAULT_MAX_ATTEMPTS = 2
#: Admission control: how many reservations one provider grants at once. Speech is
#: a scarce capability, so it is reserved before it is used
#: (``docs/architecture/19_RELIABILITY_SLO_AND_BACKPRESSURE.md``).
DEFAULT_MAX_RESERVATIONS = 2
DEFAULT_RESERVATION_TTL_SECONDS = 30.0
#: Deterministic chunking and a deterministic synthetic speaking rate, so a given
#: utterance always produces the same chunks and the same duration.
DEFAULT_CHUNK_CHARACTERS = 24
DEFAULT_CHARACTERS_PER_SECOND = 12.0
DEFAULT_SAMPLE_RATE = 8_000
DEFAULT_BYTES_PER_SAMPLE = 2
#: Bounded input: a pathological utterance must not allocate unbounded audio.
DEFAULT_MAX_CHARACTERS = 5_000
DEFAULT_CIRCUIT_FAILURE_THRESHOLD = 3

_WHITESPACE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Collapse whitespace to single spaces and strip the ends.

    This is the canonical text a provider speaks and the coordinate system a
    :class:`MarkerPlan` indexes into, so a caller builds its markers against
    ``normalize_text`` of the text it will submit.
    """

    return _WHITESPACE.sub(" ", (text or "").strip())


class VoiceState(str, Enum):
    """The teacher-voice machine (``docs/state-machines/TEACHER_VOICE_STATE_MACHINE.md``).

    The provider path drives ``RESERVING -> SYNTHESIZING -> BUFFERING ->
    COMPLETED`` and the ``CANCELLING -> CANCELLED`` branch; ``PLAYING`` belongs to
    the timeline/playback side (V0-013) and ``IDLE`` is the absence of a
    generation. The vocabulary is shared so a caller never has to invent a state.
    """

    IDLE = "IDLE"
    RESERVING = "RESERVING"
    SYNTHESIZING = "SYNTHESIZING"
    BUFFERING = "BUFFERING"
    PLAYING = "PLAYING"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class VoiceKind(str, Enum):
    """The voice families the platform recognizes. Only neutral exists in V0."""

    NEUTRAL = "NEUTRAL"


class SpeechOutcomeStatus(str, Enum):
    """The terminal results of one :meth:`~app.speech.service.SpeechService.speak`."""

    COMPLETED = "COMPLETED"
    #: Spoken audio was not produced and the caller must render the text instead.
    FALLBACK = "FALLBACK"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class SpeechMarker:
    """A semantic anchor on the normalized text (``DEC-RUNTIME-006``)."""

    marker_id: str
    text_index: int
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"marker_id": self.marker_id, "text_index": self.text_index, "label": self.label}


@dataclass(frozen=True)
class MarkerPlan:
    """Where the semantic markers of one utterance sit on the normalized text."""

    markers: tuple[SpeechMarker, ...] = ()

    def validate(self, text: str) -> None:
        """Refuse a plan that cannot be realized (indices in range, ids unique)."""

        seen: set[str] = set()
        for marker in self.markers:
            if not marker.marker_id:
                raise SpeechError(SpeechErrorCode.INVALID_REQUEST, "marker_id must not be empty")
            if marker.marker_id in seen:
                raise SpeechError(
                    SpeechErrorCode.INVALID_REQUEST,
                    f"duplicate marker_id {marker.marker_id!r}",
                )
            seen.add(marker.marker_id)
            if marker.text_index < 0 or marker.text_index > len(text):
                raise SpeechError(
                    SpeechErrorCode.INVALID_REQUEST,
                    f"marker {marker.marker_id!r} text_index {marker.text_index} is outside the text",
                )

    def ordered(self) -> tuple[SpeechMarker, ...]:
        return tuple(sorted(self.markers, key=lambda m: (m.text_index, m.marker_id)))

    def to_dict(self) -> dict[str, Any]:
        return {"markers": [m.to_dict() for m in self.markers]}


@dataclass(frozen=True)
class SpeechMarkerRealization:
    """Where a marker landed in *this* synthesis — derived output, not truth."""

    marker_id: str
    offset_ms: int
    chunk_sequence: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "marker_id": self.marker_id,
            "offset_ms": self.offset_ms,
            "chunk_sequence": self.chunk_sequence,
        }


@dataclass(frozen=True)
class SpeechConfig:
    """Provider configuration. ``config_hash`` is the determinism key."""

    voice_id: str = NEUTRAL_VOICE_ID
    language: str = DEFAULT_LANGUAGE
    data_region: str = DEFAULT_DATA_REGION
    deadline_seconds: float = DEFAULT_DEADLINE_SECONDS
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    max_concurrent_reservations: int = DEFAULT_MAX_RESERVATIONS
    reservation_ttl_seconds: float = DEFAULT_RESERVATION_TTL_SECONDS
    chunk_characters: int = DEFAULT_CHUNK_CHARACTERS
    characters_per_second: float = DEFAULT_CHARACTERS_PER_SECOND
    sample_rate: int = DEFAULT_SAMPLE_RATE
    bytes_per_sample: int = DEFAULT_BYTES_PER_SAMPLE
    max_characters: int = DEFAULT_MAX_CHARACTERS
    circuit_failure_threshold: int = DEFAULT_CIRCUIT_FAILURE_THRESHOLD

    def samples_per_character(self) -> int:
        rate = max(1.0, float(self.characters_per_second))
        return max(1, int(round(self.sample_rate / rate)))

    def duration_ms_for(self, characters: int) -> int:
        rate = max(1.0, float(self.characters_per_second))
        return int(characters / rate * 1000)

    def canonical(self) -> dict[str, Any]:
        return {
            "voice_id": self.voice_id,
            "language": self.language,
            "data_region": self.data_region,
            "deadline_seconds": self.deadline_seconds,
            "max_attempts": self.max_attempts,
            "max_concurrent_reservations": self.max_concurrent_reservations,
            "reservation_ttl_seconds": self.reservation_ttl_seconds,
            "chunk_characters": self.chunk_characters,
            "characters_per_second": self.characters_per_second,
            "sample_rate": self.sample_rate,
            "bytes_per_sample": self.bytes_per_sample,
            "max_characters": self.max_characters,
            "circuit_failure_threshold": self.circuit_failure_threshold,
        }

    def config_hash(self) -> str:
        payload = json.dumps(self.canonical(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProviderIdentity:
    """Who synthesized what, with which config — the capability's provenance."""

    name: str
    version: str
    data_region: str
    config_hash: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "version": self.version,
            "data_region": self.data_region,
            "config_hash": self.config_hash,
        }


@dataclass(frozen=True)
class AuthorizedVoice:
    """The decision of ``authorize_voice``: may this platform speak in this voice?"""

    voice_id: str
    authorized: bool
    kind: Optional[VoiceKind] = None
    reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "voice_id": self.voice_id,
            "authorized": self.authorized,
            "kind": self.kind.value if self.kind else None,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ReservationRequest:
    """Ask for capacity before any user-visible speech is promised."""

    voice_id: str = NEUTRAL_VOICE_ID
    estimated_characters: int = 0
    institution_id: Optional[str] = None
    ttl_seconds: float = DEFAULT_RESERVATION_TTL_SECONDS


@dataclass(frozen=True)
class Reservation:
    """A held unit of speech capacity; has a bounded lifetime."""

    reservation_id: str
    voice_id: str
    provider: str
    capacity_units: int
    expires_at: float
    issued_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "reservation_id": self.reservation_id,
            "voice_id": self.voice_id,
            "provider": self.provider,
            "capacity_units": self.capacity_units,
            "expires_at": self.expires_at,
            "issued_at": self.issued_at,
        }


@dataclass(frozen=True)
class SpeechRequest:
    """Everything a synthesis needs, including trace propagation."""

    text: str
    generation: int
    voice_id: str = NEUTRAL_VOICE_ID
    language: str = DEFAULT_LANGUAGE
    marker_plan: MarkerPlan = field(default_factory=MarkerPlan)
    reservation_id: Optional[str] = None
    deadline_seconds: float = DEFAULT_DEADLINE_SECONDS
    institution_id: Optional[str] = None
    trace_id: Optional[str] = None
    correlation_id: Optional[str] = None


@dataclass(frozen=True)
class SpeechChunk:
    """One streamed piece of audio for a generation.

    ``audio`` is a *stream frame*, not a self-contained file: the deterministic
    adapter emits raw PCM (:data:`content_type` ``audio/pcm``) and the terminal
    :class:`SpeechSegment` describes the sample format once, so concatenating the
    frames in order reconstructs the utterance.
    """

    generation: int
    sequence: int
    audio: bytes
    content_type: str = "audio/pcm"
    final: bool = False
    duration_ms: int = 0
    #: Markers this chunk realizes (the base resolves their offsets in order).
    marker_ids: tuple[str, ...] = ()

    @property
    def byte_size(self) -> int:
        return len(self.audio)


@dataclass(frozen=True)
class SpeechUsage:
    """Usage/cost and region accounting for one synthesis."""

    characters: int = 0
    audio_ms: int = 0
    audio_bytes: int = 0
    cost_units: float = 0.0
    data_region: str = DEFAULT_DATA_REGION

    def add(self, other: "SpeechUsage") -> "SpeechUsage":
        return SpeechUsage(
            characters=self.characters + other.characters,
            audio_ms=self.audio_ms + other.audio_ms,
            audio_bytes=self.audio_bytes + other.audio_bytes,
            cost_units=self.cost_units + other.cost_units,
            data_region=other.data_region or self.data_region,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "characters": self.characters,
            "audio_ms": self.audio_ms,
            "audio_bytes": self.audio_bytes,
            "cost_units": self.cost_units,
            "data_region": self.data_region,
        }


@dataclass(frozen=True)
class SpeechSegment:
    """The terminal verdict of one synthesis attempt for one generation."""

    generation: int
    status: VoiceState
    voice_id: str
    chunk_count: int = 0
    audio_bytes: int = 0
    duration_ms: int = 0
    markers: tuple[SpeechMarkerRealization, ...] = ()
    usage: SpeechUsage = field(default_factory=SpeechUsage)
    error_code: Optional[SpeechErrorCode] = None
    error_message: Optional[str] = None
    attempts: int = 1
    #: How to interpret the streamed frames (the frames themselves are headerless).
    content_type: str = "audio/pcm"
    sample_rate: int = 0
    bytes_per_sample: int = 0
    channels: int = 1

    @property
    def completed(self) -> bool:
        return self.status is VoiceState.COMPLETED

    @property
    def cancelled(self) -> bool:
        return self.status is VoiceState.CANCELLED

    @property
    def failed(self) -> bool:
        return self.status is VoiceState.FAILED

    @property
    def retryable(self) -> bool:
        return self.error_code in RETRYABLE_SPEECH_CODES if self.error_code else False

    def to_dict(self) -> dict[str, Any]:
        return {
            "generation": self.generation,
            "status": self.status.value,
            "voice_id": self.voice_id,
            "chunk_count": self.chunk_count,
            "audio_bytes": self.audio_bytes,
            "duration_ms": self.duration_ms,
            "markers": [m.to_dict() for m in self.markers],
            "usage": self.usage.to_dict(),
            "audio": {
                "content_type": self.content_type,
                "sample_rate": self.sample_rate,
                "bytes_per_sample": self.bytes_per_sample,
                "channels": self.channels,
            },
            "error": (
                {
                    "code": self.error_code.value,
                    "message": self.error_message,
                    "retryable": self.retryable,
                }
                if self.error_code
                else None
            ),
            "attempts": self.attempts,
        }


@dataclass(frozen=True)
class CancelAck:
    """The acknowledgement of a generation cancel. Idempotent (``DEC-RUNTIME-003``)."""

    generation: int
    acknowledged: bool
    duplicate: bool
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "generation": self.generation,
            "acknowledged": self.acknowledged,
            "duplicate": self.duplicate,
            "status": self.status,
        }


@dataclass(frozen=True)
class ProviderHealth:
    """Circuit-breaker state, capacity and counters for admission control."""

    healthy: bool
    provider: str
    voice_id: str
    region: str
    state: str  # closed | open | half_open
    consecutive_failures: int = 0
    in_flight: int = 0
    capacity_units: int = 0
    reservations_held: int = 0
    total_synthesized: int = 0
    total_failed: int = 0
    total_cancelled: int = 0
    last_error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "healthy": self.healthy,
            "provider": self.provider,
            "voice_id": self.voice_id,
            "region": self.region,
            "state": self.state,
            "consecutive_failures": self.consecutive_failures,
            "in_flight": self.in_flight,
            "capacity_units": self.capacity_units,
            "reservations_held": self.reservations_held,
            "total_synthesized": self.total_synthesized,
            "total_failed": self.total_failed,
            "total_cancelled": self.total_cancelled,
            "last_error": self.last_error,
        }


@dataclass(frozen=True)
class TextFallback:
    """The user-visible fallback when speech cannot be produced.

    ``DEC-TURN-009``: *"typed questions remain an accessibility and failure
    fallback."* The same holds for teacher speech — the utterance is shown as text
    and its **semantic** markers are carried over so captions and the timeline can
    still sync (`DEC-RUNTIME-006`), without any provider-specific offset.
    """

    text: str
    language: str
    markers: tuple[SpeechMarker, ...]
    reason: SpeechErrorCode

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "language": self.language,
            "markers": [m.to_dict() for m in self.markers],
            "reason": self.reason.value,
        }


@dataclass(frozen=True)
class SpeechOutcome:
    """What the domain service returns for one spoken utterance."""

    status: SpeechOutcomeStatus
    generation: int
    reservation_id: Optional[str] = None
    segment: Optional[SpeechSegment] = None
    fallback: Optional[TextFallback] = None
    error_code: Optional[SpeechErrorCode] = None
    attempts: int = 1

    @property
    def spoken(self) -> bool:
        return self.status is SpeechOutcomeStatus.COMPLETED

    @property
    def fell_back(self) -> bool:
        return self.status is SpeechOutcomeStatus.FALLBACK

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "generation": self.generation,
            "reservation_id": self.reservation_id,
            "segment": self.segment.to_dict() if self.segment else None,
            "fallback": self.fallback.to_dict() if self.fallback else None,
            "error_code": self.error_code.value if self.error_code else None,
            "attempts": self.attempts,
        }


__all__ = [
    "DEFAULT_BYTES_PER_SAMPLE",
    "DEFAULT_CHARACTERS_PER_SECOND",
    "DEFAULT_CHUNK_CHARACTERS",
    "DEFAULT_CIRCUIT_FAILURE_THRESHOLD",
    "DEFAULT_DATA_REGION",
    "DEFAULT_DEADLINE_SECONDS",
    "DEFAULT_LANGUAGE",
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_MAX_CHARACTERS",
    "DEFAULT_MAX_RESERVATIONS",
    "DEFAULT_RESERVATION_TTL_SECONDS",
    "DEFAULT_SAMPLE_RATE",
    "NEUTRAL_VOICE_ID",
    "AuthorizedVoice",
    "CancelAck",
    "MarkerPlan",
    "ProviderHealth",
    "ProviderIdentity",
    "Reservation",
    "ReservationRequest",
    "SpeechChunk",
    "SpeechConfig",
    "SpeechMarker",
    "SpeechMarkerRealization",
    "SpeechOutcome",
    "SpeechOutcomeStatus",
    "SpeechRequest",
    "SpeechSegment",
    "SpeechUsage",
    "TextFallback",
    "VoiceKind",
    "VoiceState",
    "normalize_text",
]
