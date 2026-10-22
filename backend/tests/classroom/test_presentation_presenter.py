"""Background presentation of a started class (V0-028 development bridge).

The product property is simple: once a teacher starts a class, the **class server**
presents its pinned slides. No teacher tab has to stay open, and an enrolled
student hears the same relayed narration a student heard while the teacher's tab
was the producer. These tests drive the real FastAPI app, SQLite and local object
store; no teacher narration request is made anywhere.
"""

from __future__ import annotations

import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from tests.fixtures import build_pptx, text_shape
from tests.test_class_start import _course, _publish_version
from tests.test_teacher_assigns_and_student_joins import (
    PASSWORD,  # noqa: F401 - re-exported helper constant
    _enrol,
    _student,
    _teacher,
)


@pytest.fixture
def settings(dev_settings):
    """The suite's locked/dev settings, with the background presenter enabled."""

    return replace(dev_settings, background_presentation=True)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _deck(slides: int = 3, *, note: str = "a") -> bytes:
    """A deck whose narration is short enough for a timing-sensitive test.

    The fallback lesson plan has no authored script, so the speaker notes are the
    narration source. One short word keeps the deterministic provider's audio
    under a tenth of a second per slide; the presenter's playout grace still keeps
    the order deterministic.
    """

    return build_pptx(
        [[text_shape(2, f"S{index}", text=f"Slide {index}")] for index in range(1, slides + 1)],
        notes={index: note for index in range(1, slides + 1)},
    )


def _class_for(client: TestClient, teacher: dict, deck: bytes) -> str:
    course_id = _course(client)
    _publish_version(client, course_id, deck)
    response = client.post(
        "/classes", params={"course_id": course_id, "title": "Period 1"}, headers=teacher
    )
    assert response.status_code == 201, response.text
    return response.json()["class_id"]


def _snapshot(client: TestClient, teacher: dict, class_id: str) -> dict:
    response = client.get(f"/classes/{class_id}/snapshot", headers=teacher)
    assert response.status_code == 200, response.text
    return response.json()


def _status(client: TestClient, teacher: dict, class_id: str) -> dict:
    response = client.get(f"/classes/{class_id}/presentation", headers=teacher)
    assert response.status_code == 200, response.text
    return response.json()


def _wait_for(predicate, *, timeout: float = 8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("the background presenter did not reach the expected state")


def _start(client: TestClient, teacher: dict, class_id: str) -> dict:
    response = client.post(f"/classes/{class_id}/start", headers=teacher)
    assert response.status_code == 200, response.text
    return response.json()


def test_a_started_class_is_presented_without_a_teacher_tab(client):
    teacher = _teacher(client)
    class_id = _class_for(client, teacher, _deck(slides=3))

    started = _start(client, teacher, class_id)
    assert started["session"]["state"] == "ACTIVE"

    # The route starts the runner in a background task after the response. Wait
    # for it, then let it present without ever calling the teacher narration API.
    status = _wait_for(lambda: (s := _status(client, teacher, class_id))["running"] and s)
    assert status["available"] is True
    assert status["paused"] is False

    final = _wait_for(
        lambda: (s := _status(client, teacher, class_id))["at_end"] and s,
        timeout=10.0,
    )
    snapshot = _snapshot(client, teacher, class_id)
    assert snapshot["state"] == "ACTIVE"
    assert snapshot["document"]["lesson"]["scene_id"] == "ppt/slides/slide3.xml"
    assert snapshot["state_version"] >= 3
    assert final["scene_order"] == 2

    # The presenter publishes the same generation students attach to. The last
    # completed slide stays replayable for the relay's TTL, so a student who joins
    # after the fast deterministic synthesis still hears it from the start.
    relay = client.app.state.narration_relay
    institution_id = client.get("/auth/me", headers=teacher).json()["principal"][
        "institution_id"
    ]
    attachment = _wait_for(
        lambda: relay.attach(
            institution_id,
            class_id,
            actor_epoch=snapshot["actor_epoch"],
            min_state_version=snapshot["state_version"],
            expected_scene_id=snapshot["document"]["lesson"]["scene_id"],
        )
    )
    events = list(attachment.events())
    assert events[0]["type"] == "narration.started"
    assert events[-1]["type"] in {"narration.completed", "narration.cancelled"}
    assert any(event["type"] == "audio" for event in events)


def test_pause_stops_the_background_class_and_resume_continues(client):
    teacher = _teacher(client)
    class_id = _class_for(client, teacher, _deck(slides=4, note="one two three"))

    _start(client, teacher, class_id)
    _wait_for(lambda: _status(client, teacher, class_id)["running"])
    # Wait until the first scene has a reported position; pausing before that is
    # still valid, but the test wants a class that has actually begun.
    _wait_for(lambda: _status(client, teacher, class_id)["scene_order"] is not None)

    paused = client.post(f"/classes/{class_id}/presentation/pause", headers=teacher)
    assert paused.status_code == 200, paused.text
    assert paused.json()["paused"] is True
    frozen = _snapshot(client, teacher, class_id)
    time.sleep(2.5)
    still = _snapshot(client, teacher, class_id)
    assert still["state_version"] == frozen["state_version"]
    assert still["document"]["lesson"]["scene_id"] == frozen["document"]["lesson"]["scene_id"]

    resumed = client.post(f"/classes/{class_id}/presentation/resume", headers=teacher)
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["paused"] is False
    _wait_for(
        lambda: _snapshot(client, teacher, class_id)["state_version"]
        > frozen["state_version"],
        timeout=10.0,
    )


def test_ending_the_class_stops_the_background_presentation(client):
    teacher = _teacher(client)
    class_id = _class_for(client, teacher, _deck(slides=6, note="one two three"))
    _start(client, teacher, class_id)
    _wait_for(lambda: _status(client, teacher, class_id)["running"])

    ended = client.post(f"/classes/{class_id}/end", headers=teacher)
    assert ended.status_code == 200, ended.text
    status = _status(client, teacher, class_id)
    assert status["running"] is False

    stopped = _snapshot(client, teacher, class_id)
    time.sleep(1.0)
    later = _snapshot(client, teacher, class_id)
    assert later["state"] == "COMPLETED"
    assert later["state_version"] == stopped["state_version"]

    relay = client.app.state.narration_relay
    assert relay.is_live(
        client.get("/auth/me", headers=teacher).json()["principal"]["institution_id"],
        class_id,
    ) is False


def test_a_manual_navigation_restarts_the_background_narration(client):
    teacher = _teacher(client)
    # Long enough that the first slide is still in its playout window when the
    # teacher moves; the runner must notice the new authoritative position and
    # abandon the old generation rather than finish it and then advance.
    class_id = _class_for(client, teacher, _deck(slides=3, note="word " * 80))
    _start(client, teacher, class_id)
    _wait_for(lambda: _status(client, teacher, class_id)["scene_order"] == 0)

    moved = client.post(
        f"/classes/{class_id}/navigate", json={"order": 2}, headers=teacher
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["snapshot"]["document"]["lesson"]["scene_id"] == "ppt/slides/slide3.xml"

    status = _wait_for(
        lambda: (s := _status(client, teacher, class_id))["scene_order"] == 2 and s,
        timeout=8.0,
    )
    assert status["scene_id"] == "ppt/slides/slide3.xml"
    # The old generation must not advance the class back or past the teacher's
    # chosen slide.
    time.sleep(1.0)
    snapshot = _snapshot(client, teacher, class_id)
    assert snapshot["document"]["lesson"]["scene_id"] == "ppt/slides/slide3.xml"


def test_presentation_control_is_class_write_only(client):
    teacher = _teacher(client)
    class_id = _class_for(client, teacher, _deck(slides=2))

    student = _student(client)
    refused = client.get(f"/classes/{class_id}/presentation", headers=student)
    assert refused.status_code == 403, refused.text
    assert refused.json()["error"]["issue_code"] == "SCOPE_REQUIRED"

    # The teacher's own status is available before the class even starts; it is a
    # status read, not a command, and writes nothing.
    status = _status(client, teacher, class_id)
    assert status["available"] is True
    assert status["running"] is False


def test_background_presentation_can_be_disabled(dev_settings):
    settings = replace(dev_settings, background_presentation=False)
    with TestClient(create_app(settings)) as client:
        teacher = _teacher(client)
        class_id = _class_for(client, teacher, _deck(slides=2))
        _start(client, teacher, class_id)

        status = _status(client, teacher, class_id)
        assert status == {
            "class_id": class_id,
            "available": False,
            "running": False,
            "paused": False,
            "at_end": False,
            "scene_order": None,
            "scene_id": None,
            "actor_epoch": None,
            "state_version": None,
            "issue_code": None,
            "message": None,
        }
        # A control on a disabled deployment is an honest no-op, not a 404.
        paused = client.post(f"/classes/{class_id}/presentation/pause", headers=teacher)
        assert paused.status_code == 200, paused.text
        assert paused.json()["available"] is False


def test_a_reopened_class_is_presented_again_from_its_first_slide(client):
    teacher = _teacher(client)
    class_id = _class_for(client, teacher, _deck(slides=3))
    _start(client, teacher, class_id)
    _wait_for(lambda: _status(client, teacher, class_id)["at_end"])

    ended = client.post(f"/classes/{class_id}/end", headers=teacher)
    assert ended.status_code == 200, ended.text
    assert _status(client, teacher, class_id)["running"] is False

    reopened = client.post(f"/classes/{class_id}/reopen", headers=teacher)
    assert reopened.status_code == 200, reopened.text
    first = reopened.json()["snapshot"]["document"]["lesson"]["scene_id"]
    assert first == "ppt/slides/slide1.xml"
    status = _wait_for(lambda: _status(client, teacher, class_id)["running"] and _status(client, teacher, class_id))
    assert status["at_end"] is False
    _wait_for(
        lambda: _status(client, teacher, class_id)["scene_order"] not in (None, 0)
        or _status(client, teacher, class_id)["at_end"],
        timeout=8.0,
    )
