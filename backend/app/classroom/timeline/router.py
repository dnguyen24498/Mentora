"""HTTP surface for a scene's narrated timeline (V0-013).

``GET /classes/{classId}/narration/{order}`` is a **teacher presentation read**.
It requires ``class:write`` (a student cannot open it: students hear the teacher
through the SFU in V1-005; a per-student HTTP audio path is not this API), resolves
the scene from the package the session pinned, and streams newline-delimited JSON
events: script metadata, captions, one WAV per semantic chunk, semantic markers,
and the terminal verdict.

The call is fenced by ``expected_state_version`` when supplied. A stale teacher
view is refused **before** any provider reservation or audio synthesis, so a late
request for the previous slide cannot speak over the current one. The stream itself
carries the pinned ``actor_epoch``/``state_version``/``generation`` so the client
can discard anything from a superseded presentation.

An ended class is refused exactly as a student's scene read is
(``409 CLASS_NOT_READY``/``CLASS_ENDED``); a class that never started is
``NOT_STARTED``. A refusal writes nothing and starts no speech.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import StreamingResponse

from app.api.security import ApiSecurity
from app.classroom.timeline.service import TimelineService
from app.classroom.timeline.stream import json_line
from app.identity.models import Principal, Scope
from app.speech.port import CancelToken


def build_timeline_router(
    service: TimelineService,
    security: ApiSecurity,
) -> APIRouter:
    router = APIRouter()
    require = security.require

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
                cancel.cancel()

        return StreamingResponse(
            lines(),
            media_type="application/x-ndjson; charset=utf-8",
            headers=headers,
        )

    return router


__all__ = ["build_timeline_router"]
