"""V0-010 classroom aggregate, end to end (API + durable store).

``backend/tests/classroom/`` is the test home the task's allowlist names. These
tests drive the real FastAPI app and the real SQLite store: a class is scheduled,
started (V0-009), and then mutated *only* through the aggregate's command entry
points — ``navigate_scene``, ``record_checkpoint``, ``end_class`` — so "all
classroom mutations pass through the aggregate" and "a duplicate command has one
logical effect" and "restart restores the pinned tuple and scene position" are
asserted against durable rows, not just the in-memory reducer.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.classroom.errors import ISSUE_INVALID_TRANSITION, ISSUE_STALE_STATE_VERSION, SnapshotIntegrityError
from app.classroom.models import CLASSROOM_STATE_ACTIVE, CLASSROOM_STATE_COMPLETED
from app.identity.models import Role
from tests.fixtures import build_pptx, text_shape

HEADERS = {"X-Institution-Id": "university-001"}


@pytest.fixture
def settings(dev_settings):
    """This suite drives the pre-identity V0 API as a teacher, so it opts into the
    development tenant shortcut (V0-023). The shipped default requires a session on
    every route; that locked default is covered by ``tests/test_required_sign_in.py``.
    """

    return dev_settings


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _deck(slides: int = 3, *, label: str = "Slide") -> bytes:
    return build_pptx(
        [[text_shape(2, f"S{index}", text=f"{label} {index}")] for index in range(1, slides + 1)],
        notes={index: f"Notes for {label} {index}" for index in range(1, slides + 1)},
    )


def _course(client, title: str = "Neural Nets") -> str:
    return client.post("/courses", params={"title": title}, headers=HEADERS).json()["course_id"]


def _publish_version(client, course_id: str) -> None:
    artifact_id = client.post(
        f"/courses/{course_id}/materials",
        files={"file": ("lecture.pptx", _deck(), "application/octet-stream")},
        headers=HEADERS,
    ).json()["artifact_id"]
    built = client.post(f"/artifacts/{artifact_id}/review-package", headers=HEADERS).json()
    assert built["publishable"] is True, built
    decided = client.post(
        f"/artifacts/{artifact_id}/review-package/decision",
        json={"decision": "APPROVE", "reviewer": "teacher@university-001"},
        headers=HEADERS,
    ).json()
    published = client.post(
        f"/course-versions/{decided['version_id']}/publish", headers=HEADERS
    )
    assert published.status_code == 200, published.text


def _started(client) -> tuple[str, str]:
    """Schedule + start, returning ``(class_id, session_id)``."""

    course_id = _course(client)
    _publish_version(client, course_id)
    class_id = client.post(
        "/classes", params={"course_id": course_id}, headers=HEADERS
    ).json()["class_id"]
    started = client.post(f"/classes/{class_id}/start", headers=HEADERS).json()
    return class_id, started["session"]["session_id"]


def _service(client):
    return client.app.state.classroom_service


def _snapshot(client, class_id: str) -> dict:
    return client.get(f"/classes/{class_id}/snapshot", headers=HEADERS).json()


def _snapshot_count(client) -> int:
    return _service(client)._repository.count_rows("university-001")["snapshots"]


# -- the aggregate owns every mutation -----------------------------------------


def test_navigate_checkpoint_and_end_persist_through_the_aggregate(client):
    class_id, session_id = _started(client)
    service = _service(client)

    nav = service.navigate_scene(
        "university-001", class_id, section_index=1, scene_id="scene-2", section_id="section-2"
    )
    assert nav.result.accepted
    assert nav.result.state_version == 2
    assert nav.session.state == CLASSROOM_STATE_ACTIVE
    document = _snapshot(client, class_id)["document"]
    assert document["state_version"] == 2
    assert document["lesson"]["section_index"] == 1
    assert document["lesson"]["scene_id"] == "scene-2"
    assert document["timeline"]["scene_id"] == "scene-2"
    assert document["timeline"]["checkpoint"] is None

    check = service.record_checkpoint("university-001", class_id, label="before student")
    assert check.result.accepted
    assert check.result.state_version == 3
    document = _snapshot(client, class_id)["document"]
    assert document["timeline"]["checkpoint"]["label"] == "before student"
    assert document["timeline"]["checkpoint"]["final"] is False

    ended = service.end_class("university-001", class_id)
    assert ended.result.accepted
    assert ended.result.state_version == 4
    assert ended.session.state == CLASSROOM_STATE_COMPLETED
    document = _snapshot(client, class_id)["document"]
    assert document["state"] == CLASSROOM_STATE_COMPLETED
    assert document["timeline"]["checkpoint"]["final"] is True
    assert document["turn"] == {"queue": [], "floor": None, "stt_reservation": None}

    # The class mirrors the session; the snapshot is append-only per version.
    view = client.get(f"/classes/{class_id}", headers=HEADERS).json()
    assert view["class"]["state"] == CLASSROOM_STATE_COMPLETED
    assert view["session"]["session_id"] == session_id
    assert _snapshot_count(client) == 4

    # A mutation after COMPLETED is an invalid transition.
    again = service.navigate_scene(
        "university-001", class_id, section_index=0, scene_id="scene-1", section_id="section-1"
    )
    assert not again.result.accepted
    assert again.result.issue_code == ISSUE_INVALID_TRANSITION
    assert _snapshot_count(client) == 4, "a refused command writes nothing"


def test_a_duplicate_command_creates_one_logical_effect(client):
    class_id, _ = _started(client)
    service = _service(client)

    first = service.navigate_scene(
        "university-001",
        class_id,
        section_index=1,
        scene_id="scene-2",
        section_id="section-2",
        command_id="cmd-1",
    )
    second = service.navigate_scene(
        "university-001",
        class_id,
        section_index=1,
        scene_id="scene-2",
        section_id="section-2",
        command_id="cmd-1",
    )

    assert first.result.accepted
    assert second.result.duplicate is True
    assert second.result.accepted is True
    assert second.result.state_version == first.result.state_version
    assert second.snapshot is None, "a duplicate writes no new snapshot"
    assert _snapshot_count(client) == 2, "initial snapshot plus one navigate"


def test_a_stale_command_is_refused_and_writes_nothing(client):
    class_id, _ = _started(client)
    service = _service(client)
    service.navigate_scene(
        "university-001", class_id, section_index=1, scene_id="scene-2", section_id="section-2"
    )

    stale = service.navigate_scene(
        "university-001",
        class_id,
        section_index=2,
        scene_id="scene-3",
        section_id="section-3",
        expected_state_version=1,
    )
    assert not stale.result.accepted
    assert stale.result.issue_code == ISSUE_STALE_STATE_VERSION
    assert _snapshot_count(client) == 2, "the stale command advanced nothing"


def test_a_command_before_start_is_refused(client):
    course_id = _course(client)
    class_id = client.post(
        "/classes", params={"course_id": course_id}, headers=HEADERS
    ).json()["class_id"]

    from app.classroom.errors import ClassStartError

    service = _service(client)
    with pytest.raises(ClassStartError) as exc:
        service.navigate_scene(
            "university-001", class_id, section_index=0, scene_id="scene-1"
        )
    assert exc.value.issue_code == "NOT_STARTED"


def test_restart_restores_the_pinned_tuple_and_scene_position(client, settings):
    class_id, _ = _started(client)
    service = _service(client)
    service.navigate_scene(
        "university-001", class_id, section_index=2, scene_id="scene-3", section_id="section-3"
    )
    service.record_checkpoint("university-001", class_id, label="resume here")
    before = _snapshot(client, class_id)

    # A brand new app instance (fresh aggregate registry) on the same durable store.
    with TestClient(create_app(settings)) as restarted:
        restarted_service = restarted.app.state.classroom_service
        document = restarted.get(f"/classes/{class_id}/snapshot", headers=HEADERS).json()
        assert document["document"]["lesson"] == before["document"]["lesson"]
        assert document["document"]["versions"] == before["document"]["versions"]
        assert document["document"]["state_version"] == 3
        assert document["document"]["timeline"]["checkpoint"]["label"] == "resume here"

        # The restored aggregate keeps reducing: the next command is version 4.
        nav = restarted_service.navigate_scene(
            "university-001",
            class_id,
            section_index=3,
            scene_id="scene-4",
            section_id="section-4",
        )
        assert nav.result.accepted
        assert nav.result.state_version == 4
        assert (
            restarted.get(f"/classes/{class_id}/snapshot", headers=HEADERS).json()["document"][
                "lesson"
            ]["scene_id"]
            == "scene-4"
        )


def test_a_corrupted_snapshot_is_refused_on_restore(client, settings):
    class_id, _ = _started(client)
    _service(client).navigate_scene(
        "university-001", class_id, section_index=1, scene_id="scene-2", section_id="section-2"
    )
    import json

    connection = _service(client)._repository._conn
    document = _snapshot(client, class_id)["document"]
    connection.execute(
        "UPDATE session_snapshots SET document = ? WHERE class_id = ?",
        (json.dumps({**document, "state": "COMPLETED"}), class_id),
    )

    # A fresh app instance restores from the (now corrupted) snapshot and refuses.
    with TestClient(create_app(settings)) as restarted:
        with pytest.raises(SnapshotIntegrityError):
            restarted.app.state.classroom_service.navigate_scene(
                "university-001", class_id, section_index=0, scene_id="scene-1"
            )


def test_end_revokes_live_join_credentials(client):
    class_id, _ = _started(client)
    service = _service(client)
    # An administrator creates the account (V0-022); the class enrols it by id —
    # enrolment itself never creates an account.
    account = client.app.state.identity_service.create_account(
        "university-001",
        email="ana@uni.test",
        role=Role.STUDENT,
        secret="correct-horse-battery-staple",
    ).account
    enrolled = client.post(
        f"/classes/{class_id}/enrollments",
        params={"student_id": account.account_id},
        headers=HEADERS,
    ).json()
    student_id = enrolled["student"]["account_id"]
    assert student_id == account.account_id
    token = service.issue_bootstrap_token("university-001", class_id, student_id).token

    assert service.verify_bootstrap_token("university-001", class_id, token).student_id == student_id

    ended = service.end_class("university-001", class_id)
    assert ended.result.accepted

    from app.classroom.errors import JoinDeniedError

    with pytest.raises(JoinDeniedError) as exc:
        service.verify_bootstrap_token("university-001", class_id, token)
    assert exc.value.issue_code == "TOKEN_REVOKED"


def test_command_telemetry_records_identities_not_content(client):
    class_id, _ = _started(client)
    service = _service(client)
    logger = type("_L", (), {"records": []})()
    logger.info = lambda message, *a: logger.records.append(message % a if a else message)  # type: ignore[assignment]
    service.telemetry._logger = logger

    service.navigate_scene(
        "university-001", class_id, section_index=1, scene_id="scene-2", section_id="section-2"
    )
    service.end_class("university-001", class_id)

    import json as _json

    events = [_json.loads(record) for record in logger.records]
    commands = [event for event in events if event["event"] == "class.command"]
    assert {event["command_type"] for event in commands} == {"NAVIGATE_SCENE", "END"}
    assert all(event["accepted"] is True for event in commands)
    assert service.telemetry.metrics.scenes_changed == 1
    assert service.telemetry.metrics.sessions_ended == 1
