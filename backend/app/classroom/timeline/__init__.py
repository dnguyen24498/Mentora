"""Timeline narration and streaming (V0-013).

``docs/state-machines/TIMELINE_STATE_MACHINE.md`` and
``docs/architecture/12_TIMELINE_PRESENTATION_AND_RESUME.md`` define the
``TimelineController`` as the Actor module coordinating semantic speech markers,
visuals, pause, cancellation, checkpoints and resume.

This package is that module's V0 implementation. It is deliberately split from the
provider:

* :mod:`app.classroom.timeline.narration` reads the script from the package the
  session **pinned** (never the source deck or a newer publication) and cuts it
  into word-safe semantic chunks (``DEC-CONTENT-005``).
* :mod:`app.classroom.timeline.controller` is the pure state machine. It rejects a
  late/duplicate marker, a stale generation and an out-of-order audio chunk, and it
  records a semantic checkpoint before an interruption
  (``DEC-RUNTIME-005``/``006``/``007``).
* :mod:`app.classroom.timeline.service` and
  :mod:`app.classroom.timeline.stream` wire the neutral voice capability to one
  HTTP stream. The teacher's tab plays the audio; there is **no** shared student
  audio in V0 (the SFU path is V1-005 and ``DEC-TECH-004`` is ``OPEN``).

``DEC-TECH-007`` (TTS/OmniVoice) is ``OPEN``, so the only adapter used here is the
provider-neutral deterministic local one. Nothing in this package imports a vendor
SDK.
"""

from __future__ import annotations

from app.classroom.timeline.chunking import assign_markers, split_text
from app.classroom.timeline.controller import (
    ChunkDisposition,
    MarkerDisposition,
    TimelineController,
    TimelineGapError,
)
from app.classroom.timeline.models import (
    NarrationScript,
    NarrationSource,
    TextChunk,
    TimelineCheckpoint,
    TimelineStatus,
)
from app.classroom.timeline.narration import build_narration

__all__ = [
    "ChunkDisposition",
    "MarkerDisposition",
    "NarrationScript",
    "NarrationSource",
    "TextChunk",
    "TimelineCheckpoint",
    "TimelineController",
    "TimelineGapError",
    "TimelineStatus",
    "assign_markers",
    "build_narration",
    "split_text",
]
