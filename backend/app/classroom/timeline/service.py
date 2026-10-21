"""The timeline read path: pinned script -> semantic chunks -> stream events (V0-013).

This service is the seam between the classroom (which owns state and the pinned
package) and the neutral voice capability (which owns provider lifecycle). It does
not mutate classroom state: a narration read is not a command. The only state it
observes is the session's epoch/version/state, and it refuses a stale or closed
presentation before any synthesis is started.

The teacher's stage is the only consumer in V0. Remote students hear the teacher
through the SFU in V1-005; opening a per-student HTTP audio path here would put
realtime audio on the general API hot path and would not be the architecture.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator, Optional

from app.classroom.models import ClassroomSession, RuntimeSessionPlan
from app.classroom.scene_source import PinnedSceneSummary
from app.classroom.service import ClassroomService
from app.classroom.timeline.chunking import (
    DEFAULT_MAX_CHUNK_CHARACTERS,
    DEFAULT_MIN_CHUNK_CHARACTERS,
)
from app.classroom.timeline.models import NarrationScript
from app.classroom.timeline.narration import build_narration
from app.classroom.timeline.stream import NarrationStreamer
from app.classroom.timeline.telemetry import TimelineTelemetry
from app.common.errors import NotFoundError
from app.speech.port import CancelToken
from app.speech.service import SpeechService


@dataclass(frozen=True)
class NarrationRead:
    """Everything one narration request resolved from the pinned session."""

    session: ClassroomSession
    plan: RuntimeSessionPlan
    scene: PinnedSceneSummary
    script: NarrationScript


class TimelineService:
    """Resolve the pinned script and produce its ordered narration events."""

    def __init__(
        self,
        classroom: ClassroomService,
        speech: SpeechService,
        *,
        telemetry: Optional[TimelineTelemetry] = None,
        max_chunk_characters: int = DEFAULT_MAX_CHUNK_CHARACTERS,
        min_chunk_characters: int = DEFAULT_MIN_CHUNK_CHARACTERS,
        streamer: Optional[NarrationStreamer] = None,
    ) -> None:
        self._classroom = classroom
        self._speech = speech
        self._telemetry = telemetry or TimelineTelemetry()
        self._max_chunk_characters = max(1, int(max_chunk_characters))
        self._min_chunk_characters = max(1, int(min_chunk_characters))
        self._streamer = streamer or NarrationStreamer(
            speech,
            telemetry=self._telemetry,
        )

    @property
    def telemetry(self) -> TimelineTelemetry:
        return self._telemetry

    @property
    def speech(self) -> SpeechService:
        return self._speech

    def read(
        self,
        institution_id: str,
        class_id: str,
        order: int,
        *,
        expected_state_version: Optional[int] = None,
    ) -> NarrationRead:
        """Resolve one scene's narration, or refuse before any synthesis.

        The session's state/version is checked first, then the pinned package is
        read through the manifest. A scene the pinned package does not have is a
        ``404``; a damaged/unlisted pinned file remains the scene source's ``502``.
        """

        if order < 0:
            from app.common.errors import ValidationError

            raise ValidationError("order must be non-negative")
        session = self._classroom.require_presenting(
            institution_id,
            class_id,
            expected_state_version=expected_state_version,
        )
        plan, scenes = self._classroom.pinned_scenes(institution_id, class_id)
        scene = next((item for item in scenes if item.order == order), None)
        if scene is None:
            raise NotFoundError(
                f"the package this session pinned has no scene {order}"
            )
        lesson_plan = self._classroom.pinned_lesson_plan(institution_id, class_id)
        script = build_narration(
            scene=scene,
            lesson_plan=lesson_plan,
            order=order,
            max_characters=self._max_chunk_characters,
            min_characters=self._min_chunk_characters,
        )
        return NarrationRead(session=session, plan=plan, scene=scene, script=script)

    def stream(
        self,
        read: NarrationRead,
        *,
        institution_id: str,
        class_id: str,
        cancel: Optional[CancelToken] = None,
    ) -> Iterator[dict[str, Any]]:
        """The ordered events for ``read``; the HTTP layer serialises them."""

        return self._streamer.iter_events(
            institution_id=institution_id,
            class_id=class_id,
            session_id=read.session.session_id,
            actor_epoch=read.session.actor_epoch,
            state_version=read.session.state_version,
            script=read.script,
            cancel=cancel,
        )


__all__ = ["NarrationRead", "TimelineService"]
