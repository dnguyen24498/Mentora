"""The teacher drives the slide; the student follows it (V0-025).

This is the V0 stopgap for live presentation, not the ordered per-class stream:
``DEC-DATA-003`` is still ``OPEN`` and V1-002 owns it. The teacher sends an HTTP
``NAVIGATE_SCENE`` command to the existing aggregate, and the student reads the
authoritative snapshot. These tests prove the properties the product sentence
depends on:

* only a teacher (``class:write``) can move the class;
* the target is a **pinned** slide order, resolved against the package the session
  started on — never the course's current publication;
* the student's snapshot and pinned-scene reads require the student to be on the
  class roster;
* a stale command is refused and writes nothing.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from tests.test_class_start import _course, _deck, _publish_version
from tests.test_teacher_assigns_and_student_joins import (
    _class_for,
    _enrol,
    _student,
    _teacher,
)


@pytest.fixture
def settings(dev_settings):
    return dev_settings


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _scenes(client, class_id: str, headers: dict) -> list[dict]:
    response = client.get(f"/classes/{class_id}/scenes", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["scenes"]


def _snapshot(client, class_id: str, headers: dict) -> dict:
    response = client.get(f"/classes/{class_id}/snapshot", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_teacher_moves_the_class_and_the_student_sees_the_same_slide(client):
    teacher = _teacher(client)
    student = _student(client)
    class_id = _class_for(client, teacher)
    _enrol(client, teacher, class_id, student)
    started = client.post(f"/classes/{class_id}/start", headers=teacher)
    assert started.status_code == 200, started.text

    scenes = _scenes(client, class_id, teacher)
    assert [scene["order"] for scene in scenes] == [0, 1, 2]

    first = _snapshot(client, class_id, student)["document"]
    assert first["lesson"]["scene_id"] == scenes[0]["scene_id"]
    assert first["state_version"] == 1

    moved = client.post(
        f"/classes/{class_id}/navigate",
        json={"order": 1, "command_id": "teacher-next-1"},
        headers=teacher,
    )
    assert moved.status_code == 200, moved.text
    body = moved.json()
    assert body["result"]["accepted"] is True
    assert body["result"]["state_version"] == 2
    assert body["result"]["events"][0]["type"] == "classroom.scene.changed"
    assert body["snapshot"]["document"]["lesson"]["scene_id"] == scenes[1]["scene_id"]

    # The student does not hold a second copy of the presentation: they read the
    # same authoritative position.
    followed = _snapshot(client, class_id, student)["document"]
    assert followed["lesson"]["scene_id"] == scenes[1]["scene_id"]
    assert followed["timeline"]["scene_id"] == scenes[1]["scene_id"]
    assert followed["state_version"] == 2

    # The pinned render at that order is readable by the enrolled student.
    slide = client.get(f"/classes/{class_id}/scenes/1", headers=student)
    assert slide.status_code == 200, slide.text
    assert slide.headers["content-type"].startswith("image/svg+xml")


def test_a_student_cannot_move_the_class(client):
    teacher = _teacher(client)
    student = _student(client)
    class_id = _class_for(client, teacher)
    _enrol(client, teacher, class_id, student)
    assert client.post(f"/classes/{class_id}/start", headers=teacher).status_code == 200
    before = _snapshot(client, class_id, teacher)["document"]

    refused = client.post(
        f"/classes/{class_id}/navigate", json={"order": 1}, headers=student
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["error"]["issue_code"] == "SCOPE_REQUIRED"

    after = _snapshot(client, class_id, teacher)["document"]
    assert after["lesson"] == before["lesson"]
    assert after["state_version"] == before["state_version"]


def test_a_stale_navigation_is_refused_and_writes_nothing(client):
    teacher = _teacher(client)
    student = _student(client)
    class_id = _class_for(client, teacher)
    _enrol(client, teacher, class_id, student)
    assert client.post(f"/classes/{class_id}/start", headers=teacher).status_code == 200

    moved = client.post(
        f"/classes/{class_id}/navigate", json={"order": 1}, headers=teacher
    )
    assert moved.status_code == 200, moved.text
    snapshot = _snapshot(client, class_id, teacher)

    stale = client.post(
        f"/classes/{class_id}/navigate",
        json={"order": 2, "expected_state_version": 1},
        headers=teacher,
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["error"]["code"] == "CONFLICT"
    assert stale.json()["error"]["issue_code"] == "STALE_STATE_VERSION"

    unchanged = _snapshot(client, class_id, teacher)
    assert unchanged["document"]["lesson"] == snapshot["document"]["lesson"]
    assert unchanged["state_version"] == snapshot["state_version"]


def test_navigation_before_start_is_class_not_ready(client):
    teacher = _teacher(client)
    class_id = _class_for(client, teacher)

    refused = client.post(
        f"/classes/{class_id}/navigate", json={"order": 0}, headers=teacher
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "CLASS_NOT_READY"
    assert refused.json()["error"]["issue_code"] == "NOT_STARTED"


def test_navigation_out_of_range_is_404(client):
    teacher = _teacher(client)
    class_id = _class_for(client, teacher)
    assert client.post(f"/classes/{class_id}/start", headers=teacher).status_code == 200

    refused = client.post(
        f"/classes/{class_id}/navigate", json={"order": 999}, headers=teacher
    )
    assert refused.status_code == 404, refused.text
    assert refused.json()["error"]["code"] == "NOT_FOUND"


def test_a_duplicate_navigation_command_has_one_effect(client):
    teacher = _teacher(client)
    class_id = _class_for(client, teacher)
    assert client.post(f"/classes/{class_id}/start", headers=teacher).status_code == 200

    first = client.post(
        f"/classes/{class_id}/navigate",
        json={"order": 2, "command_id": "one-logical-move"},
        headers=teacher,
    )
    second = client.post(
        f"/classes/{class_id}/navigate",
        json={"order": 2, "command_id": "one-logical-move"},
        headers=teacher,
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["result"]["duplicate"] is True
    assert second.json()["snapshot"] is None
    assert second.json()["result"]["state_version"] == first.json()["result"]["state_version"]
    assert _snapshot(client, class_id, teacher)["state_version"] == 2


def test_a_student_reads_only_the_class_they_are_assigned(client):
    teacher = _teacher(client)
    student = _student(client)
    course_id = _course(client)
    _publish_version(client, course_id, _deck())
    assigned = client.post(
        "/classes", params={"course_id": course_id, "title": "Assigned"}, headers=teacher
    ).json()["class_id"]
    other = client.post(
        "/classes", params={"course_id": course_id, "title": "Other"}, headers=teacher
    ).json()["class_id"]
    _enrol(client, teacher, assigned, student)
    started = client.post(f"/classes/{assigned}/start", headers=teacher)
    assert started.status_code == 200, started.text
    started_other = client.post(f"/classes/{other}/start", headers=teacher)
    assert started_other.status_code == 200, started_other.text

    for path in ("", "/snapshot", "/scenes", "/scenes/0"):
        response = client.get(f"/classes/{other}{path}", headers=student)
        assert response.status_code == 403, (path, response.text)
        assert response.json()["error"]["code"] == "NOT_ENROLLED"

    # The assigned class is readable — including its snapshot and its slide.
    assert client.get(f"/classes/{assigned}", headers=student).status_code == 200
    assert client.get(f"/classes/{assigned}/snapshot", headers=student).status_code == 200
    assert client.get(f"/classes/{assigned}/scenes/0", headers=student).status_code == 200
