"""A teacher assigns students, starts the class, and only then a student joins (V0-024).

The property under test is the one the product states in one sentence:

* a **teacher** assigns an existing student to a class and starts it;
* a **student** cannot start anything, and cannot join before the teacher starts;
* once the class is ``ACTIVE`` the same student can join;
* a student's class list is their roster, not the institution's whole schedule.

Every step drives the real FastAPI app, the real SQLite store and the real local
object store, with real sessions: the development tenant shortcut resolves a
*teacher* and cannot stand in for the student, so the administrator bootstraps,
creates a teacher and a student, and each signs in with their own password.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from tests.test_class_start import (
    PASSWORD,
    _admin_headers,
    _course,
    _deck,
    _provision,
    _publish_version,
    _sign_in,
)

TEACHER_EMAIL = "teacher@uni.test"
STUDENT_EMAIL = "student@uni.test"


@pytest.fixture
def settings(dev_settings):
    # Only the course/publish *setup* uses the shortcut (``tests.test_class_start``);
    # every assertion about assigning, starting and joining uses a real session.
    return dev_settings


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _teacher(client) -> dict:
    _provision(client, TEACHER_EMAIL, role="teacher")
    return _sign_in(client, TEACHER_EMAIL, PASSWORD)


def _student(client) -> dict:
    _provision(client, STUDENT_EMAIL, role="student")
    return _sign_in(client, STUDENT_EMAIL, PASSWORD)


def _class_for(client, teacher: dict) -> str:
    """A published course with one class scheduled against it."""

    course_id = _course(client)
    _publish_version(client, course_id, _deck())
    response = client.post(
        "/classes", params={"course_id": course_id, "title": "Period 1"}, headers=teacher
    )
    assert response.status_code == 201, response.text
    return response.json()["class_id"]


def _enrol(client, teacher: dict, class_id: str, student: dict) -> dict:
    me = client.get("/auth/me", headers=student).json()["principal"]
    response = client.post(
        f"/classes/{class_id}/enrollments",
        params={"student_id": me["account_id"]},
        headers=teacher,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_teacher_assigns_and_only_a_started_class_can_be_joined(client):
    teacher = _teacher(client)
    student = _student(client)
    class_id = _class_for(client, teacher)

    # The teacher assigns the student from the roster — an existing account, not a
    # free-text address, and nothing is created by enrolling.
    enrolled = _enrol(client, teacher, class_id, student)
    assert enrolled["created"] is True
    assert enrolled["student"]["email"] == STUDENT_EMAIL

    roster = client.get(f"/classes/{class_id}/enrollments", headers=teacher)
    assert roster.status_code == 200
    assert [entry["student"]["email"] for entry in roster.json()["enrollments"]] == [
        STUDENT_EMAIL
    ]

    # Before the teacher starts, the student cannot join: the class is not running.
    early = client.post(f"/classes/{class_id}/bootstrap-token", headers=student)
    assert early.status_code == 409, early.text
    assert early.json()["error"]["issue_code"] == "NOT_STARTED"

    # Starting is the teacher's verb. A student is refused before touching the class.
    refused = client.post(f"/classes/{class_id}/start", headers=student)
    assert refused.status_code == 403, refused.text
    assert refused.json()["error"]["issue_code"] == "SCOPE_REQUIRED"

    # The teacher starts it.
    started = client.post(f"/classes/{class_id}/start", headers=teacher)
    assert started.status_code == 200, started.text
    assert started.json()["class"]["state"] == "ACTIVE"
    assert started.json()["session"]["state"] == "ACTIVE"

    # Now the same student can join, and the credential is their own and
    # subscribe-only.
    issued = client.post(f"/classes/{class_id}/bootstrap-token", headers=student)
    assert issued.status_code == 200, issued.text
    body = issued.json()
    assert body["class_id"] == class_id
    assert body["student_id"] == client.get("/auth/me", headers=student).json()[
        "principal"
    ]["account_id"]
    assert body["scopes"] == ["subscribe"]


def test_a_student_sees_only_the_classes_they_are_enrolled_in(client):
    teacher = _teacher(client)
    student = _student(client)
    course_id = _course(client)
    _publish_version(client, course_id, _deck())

    enrolled_class = client.post(
        "/classes", params={"course_id": course_id, "title": "Mine"}, headers=teacher
    ).json()["class_id"]
    other_class = client.post(
        "/classes", params={"course_id": course_id, "title": "Someone else's"}, headers=teacher
    ).json()["class_id"]
    _enrol(client, teacher, enrolled_class, student)

    student_view = client.get("/classes", headers=student)
    assert student_view.status_code == 200
    assert [item["class_id"] for item in student_view.json()] == [enrolled_class]

    # A teacher still sees the tenant's schedule — the scoping is for participants.
    teacher_view = client.get("/classes", headers=teacher)
    assert teacher_view.status_code == 200
    assert {item["class_id"] for item in teacher_view.json()} == {
        enrolled_class,
        other_class,
    }


def test_a_student_cannot_assign_students(client):
    """The roster is a teacher capability; a student cannot add or remove anyone."""

    teacher = _teacher(client)
    student = _student(client)
    class_id = _class_for(client, teacher)
    me = client.get("/auth/me", headers=student).json()["principal"]

    response = client.post(
        f"/classes/{class_id}/enrollments",
        params={"student_id": me["account_id"]},
        headers=student,
    )
    assert response.status_code == 403, response.text
    assert response.json()["error"]["issue_code"] == "SCOPE_REQUIRED"

    roster = client.get(f"/classes/{class_id}/enrollments", headers=student)
    assert roster.status_code == 403


def test_ending_locks_the_student_and_reopening_runs_the_same_class_again(client):
    """End is a lock, not a deletion; reopen keeps the roster and pinned content.

    The student may still see *that* the class ended in the class metadata, but
    the lesson's content (snapshot and slides) is refused until the teacher
    reopens it. Reopening is the same class occurrence — same roster, same pinned
    package — reset to its first slide in a new actor epoch, so credentials from
    before the end cannot be replayed.
    """

    teacher = _teacher(client)
    student = _student(client)
    class_id = _class_for(client, teacher)
    _enrol(client, teacher, class_id, student)
    started = client.post(f"/classes/{class_id}/start", headers=teacher)
    assert started.status_code == 200, started.text
    first_epoch = started.json()["session"]["actor_epoch"]

    # While running, the student reads the lesson normally.
    assert client.get(f"/classes/{class_id}/snapshot", headers=student).status_code == 200
    assert client.get(f"/classes/{class_id}/scenes", headers=student).status_code == 200
    assert client.get(f"/classes/{class_id}/scenes/0", headers=student).status_code == 200
    old_token = client.post(f"/classes/{class_id}/bootstrap-token", headers=student)
    assert old_token.status_code == 200

    # The teacher ends the class. The class mirrors COMPLETED and the final
    # checkpoint is durable.
    ended = client.post(f"/classes/{class_id}/end", headers=teacher)
    assert ended.status_code == 200, ended.text
    assert ended.json()["session"]["state"] == "COMPLETED"
    snapshot = client.get(f"/classes/{class_id}/snapshot", headers=teacher).json()
    assert snapshot["state"] == "COMPLETED"
    assert snapshot["document"]["timeline"]["checkpoint"]["final"] is True

    # A student still sees the ended class in the class metadata (so the hub can
    # show "Ended"), but may not read or join the lesson.
    metadata = client.get(f"/classes/{class_id}", headers=student)
    assert metadata.status_code == 200
    assert metadata.json()["class"]["state"] == "COMPLETED"
    locked_reads = [
        client.get(f"/classes/{class_id}/snapshot", headers=student),
        client.get(f"/classes/{class_id}/scenes", headers=student),
        client.get(f"/classes/{class_id}/scenes/0", headers=student),
        client.post(f"/classes/{class_id}/bootstrap-token", headers=student),
    ]
    for response in locked_reads:
        assert response.status_code == 409, response.text
        assert response.json()["error"]["issue_code"] == "CLASS_ENDED"

    # Staff retain review access, and START is refused rather than silently
    # returning the completed session.
    assert client.get(f"/classes/{class_id}/snapshot", headers=teacher).status_code == 200
    restarted = client.post(f"/classes/{class_id}/start", headers=teacher)
    assert restarted.status_code == 409, restarted.text
    assert restarted.json()["error"]["issue_code"] == "WRONG_STATE"
    invalid_end = client.post(f"/classes/{class_id}/end", headers=teacher)
    assert invalid_end.status_code == 409
    assert invalid_end.json()["error"]["issue_code"] == "INVALID_TRANSITION"

    # Reopen: ACTIVE again, a new epoch, and the lesson back at its first section.
    reopened = client.post(f"/classes/{class_id}/reopen", headers=teacher)
    assert reopened.status_code == 200, reopened.text
    body = reopened.json()
    assert body["session"]["state"] == "ACTIVE"
    assert body["session"]["actor_epoch"] == first_epoch + 1
    assert body["snapshot"]["document"]["lesson"]["section_index"] == 0
    assert body["snapshot"]["document"]["timeline"]["checkpoint"] is None
    assert client.get(f"/classes/{class_id}", headers=teacher).json()["class"]["state"] == "ACTIVE"

    # The student can rejoin in the new epoch and read the lesson again; the
    # credential issued before the end is no longer usable.
    issued = client.post(f"/classes/{class_id}/bootstrap-token", headers=student)
    assert issued.status_code == 200, issued.text
    assert issued.json()["actor_epoch"] == first_epoch + 1
    assert client.get(f"/classes/{class_id}/snapshot", headers=student).status_code == 200
    assert client.get(f"/classes/{class_id}/scenes/0", headers=student).status_code == 200

    # A second reopen is not a transition: the class is running again.
    second = client.post(f"/classes/{class_id}/reopen", headers=teacher)
    assert second.status_code == 409
    assert second.json()["error"]["issue_code"] == "INVALID_TRANSITION"
