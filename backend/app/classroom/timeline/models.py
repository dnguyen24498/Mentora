"""The timeline vocabulary (V0-013).

These are the semantic units the timeline coordinates, not raw audio bytes:

* a :class:`TextChunk` is a word-safe semantic segment of the authored script. Its
  character offsets index the normalized script, so a UI can map a caption or a
  marker back to the authored text without re-deriving anything.
* a :class:`NarrationScript` is one scene's script, its source, and the chunks the
  provider will synthesize.
* a :class:`TimelineCheckpoint` names the semantic position a resume starts from.
  ``DEC-RUNTIME-005`` requires a resume to continue at a semantic segment, never at
  a byte offset.

The vocabulary is stdlib-only. The provider models are used only as the marker
coordinate system (``app.speech.models``), which is itself stdlib-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from app.speech.models import (
    DEFAULT_LANGUAGE,
    NEUTRAL_VOICE_ID,
    SpeechMarker,
)


class NarrationSource(str, Enum):
    """Where the spoken text came from, in the fixed precedence order."""

    #: The pinned package's lesson-plan section ``script``.
    LESSON_SCRIPT = "lesson-script"
    #: The authored fallback script for that section.
    FALLBACK_SCRIPT = "fallback-script"
    #: The scene's speaker notes.
    SPEAKER_NOTES = "speaker-notes"
    #: The slide's own text (read in paint order).
    SLIDE_TEXT = "slide-text"
    #: The scene has no authored text at all; the timeline has nothing to say.
    NONE = "none"


class TimelineStatus(str, Enum):
    """The timeline's own state machine.

    ``PLAYING`` is a timeline/playback state; the provider only reaches
    ``COMPLETED``/``FAILED``/``CANCELLED``. ``FALLBACK`` means the appended text is
    authoritative for this segment so the lesson continues (``DEC-TURN-009``).
    """

    IDLE = "IDLE"
    PREPARING = "PREPARING"
    SYNTHESIZING = "SYNTHESIZING"
    PLAYING = "PLAYING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    FALLBACK = "FALLBACK"

    @property
    def terminal(self) -> bool:
        return self in (
            TimelineStatus.COMPLETED,
            TimelineStatus.CANCELLED,
            TimelineStatus.FAILED,
            TimelineStatus.FALLBACK,
        )


@dataclass(frozen=True)
class TextChunk:
    """One word-safe segment of the script, with markers that land in it."""

    index: int
    text: str
    char_start: int
    char_end: int
    marker_ids: tuple[str, ...] = ()

    @property
    def word_count(self) -> int:
        return len([word for word in self.text.split() if word])

    def marker_plan(self) -> tuple[SpeechMarker, ...]:
        """The markers this chunk realizes, all at its semantic start.

        Safe markers name reveal steps, not word positions. A chunk is the
        semantic unit that begins at its first word, so every marker assigned to
        it indexes offset zero of that chunk. The provider's realized milliseconds
        remain derived output (``DEC-RUNTIME-006``).
        """

        return tuple(
            SpeechMarker(marker_id=marker_id, text_index=0, label=marker_id)
            for marker_id in self.marker_ids
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "text": self.text,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "word_count": self.word_count,
            "marker_ids": list(self.marker_ids),
        }


@dataclass(frozen=True)
class NarrationScript:
    """One scene's authored narration, cut into semantic chunks."""

    scene_id: str
    order: int
    source: NarrationSource
    text: str
    chunks: tuple[TextChunk, ...]
    voice_id: str = NEUTRAL_VOICE_ID
    language: str = DEFAULT_LANGUAGE

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    @property
    def word_count(self) -> int:
        return sum(chunk.word_count for chunk in self.chunks)

    @property
    def empty(self) -> bool:
        return not self.chunks

    def to_dict(self, *, include_text: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "scene_id": self.scene_id,
            "order": self.order,
            "source": self.source.value,
            "chunk_count": self.chunk_count,
            "word_count": self.word_count,
            "voice_id": self.voice_id,
            "language": self.language,
            "empty": self.empty,
        }
        if include_text:
            # The text is authored content, not telemetry. Callers that expose it
            # are the fallback path and the optional caption/transcript UI.
            payload["text"] = self.text
            payload["chunks"] = [chunk.to_dict() for chunk in self.chunks]
        return payload


@dataclass(frozen=True)
class TimelineCheckpoint:
    """A semantic resume point, not a byte offset (``DEC-RUNTIME-005``)."""

    checkpoint_id: str
    scene_id: Optional[str]
    segment_index: int
    chunk_index: int
    offset_ms: int
    label: Optional[str]
    final: bool
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "scene_id": self.scene_id,
            "segment_index": self.segment_index,
            "chunk_index": self.chunk_index,
            "offset_ms": self.offset_ms,
            "label": self.label,
            "final": self.final,
            "created_at": self.created_at,
        }


@dataclass
class TimelineState:
    """The mutable state one timeline generation owns."""

    status: TimelineStatus = TimelineStatus.IDLE
    generation: int = 0
    actor_epoch: int = 0
    scene_id: Optional[str] = None
    segment_index: int = 0
    last_chunk_sequence: int = -1
    played_ms: int = 0
    last_marker_offset_ms: int = -1
    markers_seen: set[str] = field(default_factory=set)

    @property
    def terminal(self) -> bool:
        return self.status.terminal
