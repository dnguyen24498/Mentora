"""Structured telemetry for timeline narration (V0-013).

``docs/architecture/20_OBSERVABILITY_COST_AND_CAPACITY.md`` and the timeline
sequence assert that every terminal path emits metrics and a user-visible state.
Authored text is never logged; only its size, the source, the provider identity
and the outcome are.

The counters are in-process, like the classroom's. A tenant-scoped metrics
backend is not a decided technology (``DEC-TECH-*``), so this module records what
the timeline itself observed and leaves export to the deployment.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("mentora.timeline")


@dataclass
class TimelineMetrics:
    streams_started: int = 0
    streams_completed: int = 0
    streams_cancelled: int = 0
    streams_failed: int = 0
    segments_synthesized: int = 0
    segments_fallback: int = 0
    audio_bytes: int = 0
    audio_ms: int = 0
    late_markers: int = 0
    duplicate_markers: int = 0
    stale_events: int = 0

    def to_dict(self) -> dict[str, int]:
        return dict(self.__dict__)


@dataclass
class TimelineTelemetry:
    """Emits one structured record per timeline outcome and keeps counters."""

    metrics: TimelineMetrics = field(default_factory=TimelineMetrics)
    _logger: logging.Logger = field(default=logger, repr=False)

    def emit(self, event: str, **fields: Any) -> dict[str, Any]:
        record = {"event": event, **fields}
        try:
            self._logger.info(json.dumps(record, sort_keys=True, default=str))
        except (TypeError, ValueError):  # pragma: no cover - telemetry must not break
            self._logger.info("event=%s", event)
        return record

    def record_started(
        self,
        *,
        institution_id: str,
        class_id: str,
        session_id: str,
        scene_id: str,
        source: str,
        chunk_count: int,
        word_count: int,
        provider: str,
        voice_id: str,
        actor_epoch: int,
        state_version: int,
    ) -> dict[str, Any]:
        self.metrics.streams_started += 1
        return self.emit(
            "timeline.started",
            institution_id=institution_id,
            class_id=class_id,
            session_id=session_id,
            scene_id=scene_id,
            source=source,
            chunk_count=chunk_count,
            word_count=word_count,
            provider=provider,
            voice_id=voice_id,
            actor_epoch=actor_epoch,
            state_version=state_version,
        )

    def record_segment(
        self,
        *,
        institution_id: str,
        class_id: str,
        scene_id: str,
        chunk_index: int,
        status: str,
        audio_ms: int = 0,
        audio_bytes: int = 0,
        marker_count: int = 0,
        reason: Optional[str] = None,
    ) -> dict[str, Any]:
        self.metrics.segments_synthesized += 1
        self.metrics.audio_ms += max(0, audio_ms)
        self.metrics.audio_bytes += max(0, audio_bytes)
        if status == "FALLBACK":
            self.metrics.segments_fallback += 1
        return self.emit(
            "timeline.segment",
            institution_id=institution_id,
            class_id=class_id,
            scene_id=scene_id,
            chunk_index=chunk_index,
            status=status,
            audio_ms=audio_ms,
            audio_bytes=audio_bytes,
            marker_count=marker_count,
            reason=reason,
        )

    def record_completed(
        self,
        *,
        institution_id: str,
        class_id: str,
        scene_id: str,
        status: str,
        duration_ms: int,
        fallback: bool = False,
    ) -> dict[str, Any]:
        if status == "COMPLETED":
            self.metrics.streams_completed += 1
        elif status == "CANCELLED":
            self.metrics.streams_cancelled += 1
        elif fallback:
            self.metrics.streams_failed += 1
        else:
            self.metrics.streams_failed += 1
        return self.emit(
            "timeline.completed",
            institution_id=institution_id,
            class_id=class_id,
            scene_id=scene_id,
            status=status,
            duration_ms=duration_ms,
            fallback=fallback,
        )

    def record_late_marker(self, *, class_id: str, scene_id: str, marker_id: str) -> dict[str, Any]:
        self.metrics.late_markers += 1
        return self.emit(
            "timeline.marker_late",
            class_id=class_id,
            scene_id=scene_id,
            marker_id=marker_id,
        )

    def record_duplicate_marker(
        self, *, class_id: str, scene_id: str, marker_id: str
    ) -> dict[str, Any]:
        self.metrics.duplicate_markers += 1
        return self.emit(
            "timeline.marker_duplicate",
            class_id=class_id,
            scene_id=scene_id,
            marker_id=marker_id,
        )

    def record_stale_event(self, *, class_id: str, scene_id: str, kind: str) -> dict[str, Any]:
        self.metrics.stale_events += 1
        return self.emit(
            "timeline.event_stale",
            class_id=class_id,
            scene_id=scene_id,
            kind=kind,
        )


__all__ = ["TimelineMetrics", "TimelineTelemetry"]
