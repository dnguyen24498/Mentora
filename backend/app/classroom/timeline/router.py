"""HTTP surface for a scene's narrated timeline (V0-013).

``GET /classes/{classId}/narration/{order}`` is a **teacher presentation read**.
It requires ``class:write`` and is the only endpoint that starts synthesis; a
student never calls it, and instead attaches to the already-generated chunks via
the relay below. It resolves the scene from the package the session pinned and
streams newline-delimited JSON events: script metadata, captions, one WAV per
semantic chunk, semantic markers, and the terminal verdict.

The call is fenced by ``expected_state_version`` when supplied. A stale teacher
view is refused **before** any provider reservation or audio synthesis, so a late
request for the previous slide cannot speak over the current one. The stream itself
carries the pinned ``actor_epoch``/``state_version``/``generation`` so the client
can discard anything from a superseded presentation.

An ended class is refused exactly as a student's scene read is
(``409 CLASS_NOT_READY``/``CLASS_ENDED``); a class that never started is
``NOT_STARTED``. A refusal writes nothing and starts no speech.

``GET /classes/{classId}/narration`` is the **student live relay** (V1-005 bridge).
It starts no synthesis and reads no source document. It attaches to the generation
the teacher's tab is currently producing and copies the same WAV chunks, so an
enrolled student hears the lecture without a second provider call. ``204`` means
"the teacher is not speaking right now"; the page retries. This is an in-process
development relay, not the SFU media plane (`DEC-TECH-004` is `OPEN`).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import Response, StreamingResponse

from app.api.security import ApiSecurity
from app.classroom.timeline.service import TimelineService
from app.classroom.timeline.stream import json_line
from app.identity.models import Principal, Role, Scope
from app.speech.port import CancelToken


def _student_id(principal: Principal) -> Optional[str]:
    """The roster id a student's read is checked against; staff pass ``None``."""

    return principal.account_id if principal.role is Role.STUDENT else None


def build_timeline_router(
    service: TimelineService,
    security: ApiSecurity,
) -> APIRouter:
    router = APIRouter()
    require = security.require

    @router.get("/classes/{class_id}/narration")
    def listen(
        class_id: str,
        after_generation: Optional[int] = Query(default=None, ge=0),
        expected_scene_id: Optional[str] = Query(default=None),
        principal: Principal = Depends(require(Scope.SCENE_READ)),
    ) -> Response:
        """Attach to the teacher's current live narration (student relay).

        The response is the same newline-delimited event vocabulary as the
        teacher's stream. It begins with the generation's ``narration.started``
        event, then carries the buffered chunks already produced for the current
        slide followed by the chunks published while the student is attached, and
        ends at the generation's terminal verdict. A student attaching mid-slide
        therefore hears that slide from its start; a new slide's generation
        supersedes the old one, so the audio never runs under a different slide's
        image. ``204`` means the teacher is paused, not speaking yet, or has moved to
        a scene whose narration has not started; the client retries.

        ``after_generation`` is the generation the page already consumed: passing it
        suppresses a replay of that same slide while waiting for the teacher's next
        one. ``expected_scene_id`` ties the attachment to the slide the student's
        snapshot is showing, so a completed previous slide cannot be replayed after
        the teacher has advanced.

        A student must be on the roster and the class must be running. An ended
        class is ``409 CLASS_ENDED`` until a teacher reopens it, exactly as the
        snapshot and scene reads. This route starts no speech and writes nothing.
        """

        session = service.authorize_listener(
            principal.institution_id,
            class_id,
            student_id=_student_id(principal),
        )
        attachment = service.relay.attach(
            principal.institution_id,
            class_id,
            actor_epoch=session.actor_epoch,
            min_state_version=session.state_version,
            after_generation=after_generation,
            expected_scene_id=expected_scene_id,
        )
        if attachment is None:
            return Response(status_code=204, headers={"Cache-Control": "no-store"})

        start = attachment.start_event
        provider = start.get("provider") or {}
        headers = {
            "Cache-Control": "no-store",
            "X-Mentora-Voice": str(start.get("voice_id", "")),
            "X-Mentora-Provider": str(provider.get("name", "")),
            "X-Mentora-Scene": str(start.get("scene_id", "")),
            "X-Mentora-Source": str(start.get("source", "")),
            "X-Mentora-Actor-Epoch": str(start.get("actor_epoch", "")),
            "X-Mentora-State-Version": str(start.get("state_version", "")),
        }

        def lines():
            try:
                for event in attachment.events():
                    # ``{}`` is the relay's heartbeat: a blank line is valid NDJSON
                    # framing and the client ignores it, while the periodic yield
                    # lets Starlette notice a student that has gone away.
                    yield json_line(event) if event else "\n"
            finally:
                attachment.close()

        return StreamingResponse(
            lines(),
            media_type="application/x-ndjson; charset=utf-8",
            headers=headers,
        )

    @router.get("/classes/{class_id}/narration/{order}")
    def narration(
        class_id: str,
        order: int = Path(ge=0),
        expected_state_version: Optional[int] = Query(default=None, ge=0),
        principal: Principal = Depends(require(Scope.CLASS_WRITE)),
    ) -> StreamingResponse:
        """Stream one pinned scene's narration as ordered NDJSON events.

        Each line is a complete JSON object. ``audio`` events carry a base64 WAV
        segment; ``caption`` events carry authored text (hidden by default in the
        classroom UI, available for accessibility and the text fallback); ``marker``
        events are the provider-neutral semantic anchors. The stream terminates with
        ``narration.completed`` (status ``COMPLETED``, ``FALLBACK`` or ``EMPTY``),
        ``narration.cancelled``, or a classified ``error`` event.
        """

        read = service.read(
            principal.institution_id,
            class_id,
            order,
            expected_state_version=expected_state_version,
        )
        cancel = CancelToken()
        events = service.stream(
            read,
            institution_id=principal.institution_id,
            class_id=class_id,
            cancel=cancel,
        )
        provider = service.speech.provider.identity().to_dict()
        headers = {
            "Cache-Control": "no-store",
            "X-Mentora-Voice": read.script.voice_id,
            "X-Mentora-Provider": str(provider.get("name", "")),
            "X-Mentora-Scene": read.script.scene_id,
            "X-Mentora-Source": read.script.source.value,
            "X-Mentora-Actor-Epoch": str(read.session.actor_epoch),
            "X-Mentora-State-Version": str(read.session.state_version),
        }

        def lines():
            try:
                for event in events:
                    yield json_line(event)
            finally:
                # Starlette closes the generator on client disconnect; the
                # streamer's own finally is the authoritative cancellation, and
                # this token makes the intent explicit to any provider wrapper.
                # Closing the service iterator also reaches the relay's finally,
                # so attached students receive the cancellation now rather than
                # waiting for this generator to be garbage-collected.
                cancel.cancel()
                close = getattr(events, "close", None)
                if close is not None:
                    close()

        return StreamingResponse(
            lines(),
            media_type="application/x-ndjson; charset=utf-8",
            headers=headers,
        )

    return router


__all__ = ["build_timeline_router"]
