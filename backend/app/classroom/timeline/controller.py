"""The pure timeline state machine (V0-013).

The controller is the part of the timeline that can be reasoned about without a
provider, a socket or a clock: it accepts the events a synthesis produces and
decides whether they may mutate the current presentation.

The rules are the acceptance criteria made executable:

* **No old generation mutates the current presentation.** Every accepted event
  names its generation; a different generation is stale and is ignored.
* **A duplicate is not a second effect** (``DEC-RUNTIME-003``). A marker already
  realized, or an audio chunk already applied, is reported as a duplicate.
* **A gap is not silently repaired.** A missing audio chunk raises
  :class:`TimelineGapError`, so the caller resynchronises rather than playing a
  spliced stream.
* **A checkpoint precedes an interruption** (``DEC-RUNTIME-005``). It records the
  semantic segment/chunk/offset, never raw audio bytes.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional

from app.classroom.timeline.models import (
    TimelineCheckpoint,
    TimelineState,
    TimelineStatus,
)


class TimelineGapError(Exception):
    """An audio chunk arrived out of sequence; the stream must not be spliced."""


class ChunkDisposition(str, Enum):
    """What happened to an audio chunk offered to the controller."""

    ACCEPTED = "ACCEPTED"
    DUPLICATE = "DUPLICATE"
    STALE = "STALE"


class MarkerDisposition(str, Enum):
    """What happened to a marker offered to the controller."""

    ACCEPTED = "ACCEPTED"
    DUPLICATE = "DUPLICATE"
    LATE = "LATE"
    STALE = "STALE"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimelineController:
    """One timeline generation, from PREPARING to a terminal verdict."""

    def __init__(self, *, clock: Optional[Callable[[], datetime]] = None) -> None:
        self._clock = clock or _utcnow
        self.state = TimelineState()

    # -- lifecycle ---------------------------------------------------------------
    def begin(
        self,
        *,
        generation: int,
        actor_epoch: int,
        scene_id: str,
    ) -> TimelineState:
        """Start a new generation, replacing any previous one.

        Replacing the state is the structural form of "an old generation cannot
        mutate the current presentation": after ``begin`` the old generation is
        stale by identity.
        """

        if generation < 1:
            raise ValueError("generation must be >= 1")
        if actor_epoch < 1:
            raise ValueError("actor_epoch must be >= 1")
        self.state = TimelineState(
            status=TimelineStatus.PREPARING,
            generation=generation,
            actor_epoch=actor_epoch,
            scene_id=scene_id,
        )
        return self.state

    def begin_segment(self, segment_index: int) -> TimelineState:
        """Mark the semantic segment about to be synthesized."""

        if self.state.status.terminal:
            return self.state
        if segment_index < 0:
            raise ValueError("segment_index must be non-negative")
        self.state.segment_index = segment_index
        self.state.last_chunk_sequence = -1
        # Marker offsets are relative to one segment's audio, so a new segment
        # starts its own offset coordinate. The marker-id set persists, so a
        # repeated semantic marker is still a duplicate across the whole scene.
        self.state.last_marker_offset_ms = -1
        self.state.status = TimelineStatus.SYNTHESIZING
        return self.state

    def mark_playing(self) -> TimelineState:
        if not self.state.status.terminal:
            self.state.status = TimelineStatus.PLAYING
        return self.state

    def complete(self) -> TimelineState:
        if not self.state.status.terminal:
            self.state.status = TimelineStatus.COMPLETED
        return self.state

    def cancel(self) -> TimelineState:
        self.state.status = TimelineStatus.CANCELLED
        return self.state

    def fallback(self) -> TimelineState:
        self.state.status = TimelineStatus.FALLBACK
        return self.state

    def fail(self) -> TimelineState:
        self.state.status = TimelineStatus.FAILED
        return self.state

    # -- event admission ---------------------------------------------------------
    def accept_chunk(
        self,
        *,
        generation: int,
        sequence: int,
        duration_ms: int,
    ) -> ChunkDisposition:
        """Apply one audio chunk's duration, or classify why it cannot be applied."""

        if generation != self.state.generation:
            return ChunkDisposition.STALE
        if self.state.status.terminal or self.state.status not in (
            TimelineStatus.SYNTHESIZING,
            TimelineStatus.PLAYING,
        ):
            return ChunkDisposition.STALE
        if sequence < 0:
            raise ValueError("sequence must be non-negative")
        if sequence <= self.state.last_chunk_sequence:
            return ChunkDisposition.DUPLICATE
        if sequence != self.state.last_chunk_sequence + 1:
            raise TimelineGapError(
                f"expected audio chunk {self.state.last_chunk_sequence + 1}, got {sequence}"
            )
        self.state.last_chunk_sequence = sequence
        self.state.played_ms += max(0, int(duration_ms))
        self.state.status = TimelineStatus.PLAYING
        return ChunkDisposition.ACCEPTED

    def accept_marker(
        self,
        *,
        generation: int,
        marker_id: str,
        offset_ms: int,
    ) -> MarkerDisposition:
        """Apply a semantic marker, or classify it as duplicate/late/stale.

        A marker is *late* when it arrives after the generation reached a terminal
        state, or when its offset is behind the last accepted marker. A late marker
        is ignored rather than moving the presentation backwards
        (``DEC-RUNTIME-006``).
        """

        if generation != self.state.generation:
            return MarkerDisposition.STALE
        if self.state.status.terminal:
            return MarkerDisposition.LATE
        if marker_id in self.state.markers_seen:
            return MarkerDisposition.DUPLICATE
        if offset_ms < self.state.last_marker_offset_ms:
            return MarkerDisposition.LATE
        self.state.markers_seen.add(marker_id)
        self.state.last_marker_offset_ms = max(0, int(offset_ms))
        return MarkerDisposition.ACCEPTED

    # -- checkpoint/resume -------------------------------------------------------
    def checkpoint(
        self,
        *,
        label: Optional[str] = None,
        final: bool = False,
    ) -> TimelineCheckpoint:
        """A semantic checkpoint at the current position."""

        return TimelineCheckpoint(
            checkpoint_id=str(uuid.uuid4()),
            scene_id=self.state.scene_id,
            segment_index=self.state.segment_index,
            chunk_index=max(0, self.state.last_chunk_sequence),
            offset_ms=max(0, self.state.played_ms),
            label=label,
            final=final,
            created_at=self._clock().isoformat(),
        )

    def resume(self, *, generation: int) -> TimelineState:
        """Start a new generation at the current semantic segment.

        The checkpoint's segment is the resume point; the new generation starts
        with fresh sequence/marker memory, so late chunks from the interrupted
        generation can never be applied.
        """

        if generation < 1:
            raise ValueError("generation must be >= 1")
        self.state = replace(
            self.state,
            status=TimelineStatus.SYNTHESIZING,
            generation=generation,
            last_chunk_sequence=-1,
            played_ms=0,
            last_marker_offset_ms=-1,
            markers_seen=set(),
        )
        return self.state


__all__ = [
    "ChunkDisposition",
    "MarkerDisposition",
    "TimelineController",
    "TimelineGapError",
]
