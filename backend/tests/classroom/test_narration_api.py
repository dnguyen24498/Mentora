"""The teacher's narration stream over HTTP (V0-013)."""

from __future__ import annotations

import asyncio
import json

import httpx

from tests.test_teacher_assigns_and_student_joins import (  # noqa: F401 - fixtures
    _class_for,
    _enrol,
    _student,
    _teacher,
    client,
    settings,
)


def _lines(response):
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def test_teacher_streams_narration_and_student_is_refused(client):
    teacher = _teacher(client)
    student = _student(client)
    class_id = _class_for(client, teacher)

    before = client.get(f"/classes/{class_id}/narration/0", headers=teacher)
    assert before.status_code == 409
    assert before.json()["error"]["issue_code"] == "NOT_STARTED"

    started = client.post(f"/classes/{class_id}/start", headers=teacher)
    assert started.status_code == 200, started.text
    version = started.json()["session"]["state_version"]

    response = client.get(
        f"/classes/{class_id}/narration/0",
        params={"expected_state_version": version},
        headers=teacher,
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert response.headers["cache-control"] == "no-store"
    events = _lines(response)
    assert events[0]["type"] == "narration.started"
    assert events[0]["provider"]["name"] == "neutral-deterministic"
    assert events[-1]["type"] == "narration.completed"
    assert events[-1]["status"] in {"COMPLETED", "EMPTY"}

    stale = client.get(
        f"/classes/{class_id}/narration/0",
        params={"expected_state_version": version + 7},
        headers=teacher,
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["issue_code"] == "STALE_STATE_VERSION"

    assert client.get(f"/classes/{class_id}/narration/999", headers=teacher).status_code == 404

    # The student's relay is a different surface: it starts no synthesis. Before
    # enrolment it is refused.
    not_enrolled = client.get(f"/classes/{class_id}/narration", headers=student)
    assert not_enrolled.status_code == 403
    assert not_enrolled.json()["error"]["issue_code"] == "NOT_ENROLLED"

    _enrol(client, teacher, class_id, student)
    refused = client.get(f"/classes/{class_id}/narration/0", headers=student)
    assert refused.status_code == 403

    # The teacher's fast local mock has already completed the slide. A student who
    # attaches now still receives that current generation from its start, rather
    # than silence while the teacher is still playing it.
    replay = client.get(f"/classes/{class_id}/narration", headers=student)
    assert replay.status_code == 200
    replay_events = _lines(replay)
    assert replay_events[0]["type"] == "narration.started"
    assert replay_events[-1]["type"] == "narration.completed"

    # Once the page says it consumed that exact generation, the relay answers
    # "nothing live" instead of replaying the slide in a wait loop.
    generation = replay_events[0]["generation"]
    idle = client.get(
        f"/classes/{class_id}/narration",
        params={"after_generation": generation},
        headers=student,
    )
    assert idle.status_code == 204
    teacher_idle = client.get(
        f"/classes/{class_id}/narration",
        params={"after_generation": generation},
        headers=teacher,
    )
    assert teacher_idle.status_code == 204

    assert client.post(f"/classes/{class_id}/end", headers=teacher).status_code == 200
    ended = client.get(f"/classes/{class_id}/narration/0", headers=teacher)
    assert ended.status_code == 409
    assert ended.json()["error"]["issue_code"] == "CLASS_ENDED"
    ended_listener = client.get(f"/classes/{class_id}/narration", headers=student)
    assert ended_listener.status_code == 409
    assert ended_listener.json()["error"]["issue_code"] == "CLASS_ENDED"


def _event(base: dict, **overrides) -> dict:
    event = {
        **base,
        "type": "narration.started",
        "source": "slide-text",
        "chunk_count": 1,
        "word_count": 1,
        "voice_id": "neutral",
        "provider": {"name": "neutral-deterministic", "version": "1.0.0"},
        "empty": False,
        "sequence": 1,
    }
    event.update(overrides)
    return event


async def test_an_enrolled_student_receives_the_teacher_live_chunks(client):
    teacher = _teacher(client)
    student = _student(client)
    class_id = _class_for(client, teacher)
    _enrol(client, teacher, class_id, student)
    started = client.post(f"/classes/{class_id}/start", headers=teacher)
    assert started.status_code == 200, started.text
    session = started.json()["session"]
    institution_id = client.get("/auth/me", headers=teacher).json()["principal"][
        "institution_id"
    ]
    relay = client.app.state.narration_relay

    base = {
        "class_id": class_id,
        "session_id": session["session_id"],
        "scene_id": "ppt/slides/slide1.xml",
        "actor_epoch": session["actor_epoch"],
        "state_version": session["state_version"],
        "generation": 4242,
    }
    # The teacher's stream has started (the relay holds the generation) and is
    # waiting between chunks. A student attaches and receives the live remainder.
    relay.publish(institution_id, class_id, _event(base))

    transport = httpx.ASGITransport(app=client.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        request = asyncio.create_task(
            ac.get(f"/classes/{class_id}/narration", headers=student)
        )
        for _ in range(500):
            if relay.listener_count(institution_id, class_id) > 0:
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("the student listener did not attach")

        relay.publish(
            institution_id,
            class_id,
            _event(
                base,
                type="audio",
                sequence=2,
                chunk_index=0,
                content_type="audio/wav",
                duration_ms=100,
                data="UklGRg==",
            ),
        )
        relay.publish(
            institution_id,
            class_id,
            _event(
                base,
                type="narration.completed",
                sequence=3,
                status="COMPLETED",
                duration_ms=100,
                fallback=False,
            ),
        )
        response = await asyncio.wait_for(request, timeout=5.0)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert [event["type"] for event in events] == [
        "narration.started",
        "audio",
        "narration.completed",
    ]
    assert events[1]["data"] == "UklGRg=="
