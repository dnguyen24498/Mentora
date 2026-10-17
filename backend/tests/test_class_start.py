"""V0-009 class start and runtime session plan: the acceptance paths (API level).

``tests/integration/`` does not exist in this repo; ``backend/tests/`` is its test
root (the same nominal-path mapping V0-004…V0-008 use). Every test drives the real
FastAPI app, the real SQLite store and the real local object store.

The three acceptance criteria and the four required tests map like this:

* **No runtime ``latest`` lookup** —
  ``test_the_pinned_tuple_does_not_follow_a_newer_publication``;
* **Pinned tuple survives restart** — ``test_the_pinned_tuple_survives_a_restart``;
* **Only authorized enrollment can join** — ``test_join_requires_enrollment``,
  ``test_booking_a_join_before_start_is_refused``;
* **draft version rejected** — ``test_a_draft_version_is_refused_and_writes_nothing``;
* **incompatible index** — ``test_an_incompatible_index_pin_is_refused``;
* **duplicate start** — ``test_a_duplicate_start_returns_the_same_session`` and
  ``test_concurrent_starts_create_one_session``;
* **cross-tenant join** — ``test_join_requires_enrollment`` and
  ``test_class_start_is_tenant_isolated``.

Plus the requirements the task names: the exact tuple (policy/region/capability),
the atomic start (nothing written on a refusal), the durable initial snapshot, and
telemetry that carries identities but not authored text.
"""

from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.classroom.catalog import RuntimeCatalog, RuntimeDefaults
from app.classroom.errors import (
    ISSUE_STALE_EPOCH,
    ISSUE_TOKEN_EXPIRED,
    ISSUE_TOKEN_REVOKED,
    ISSUE_TOKEN_UNKNOWN,
    JoinDeniedError,
)
from app.classroom.models import (
    CLASSROOM_STATE_ACTIVE,
    CLASSROOM_STATE_SCHEDULED,
    INITIAL_ACTOR_EPOCH,
    INITIAL_EVENT_SEQUENCE,
    INITIAL_STATE_VERSION,
    SNAPSHOT_SCHEMA_VERSION,
)
from app.classroom.repository import ClassRepository
from app.classroom.snapshot import snapshot_checksum
from app.compiler.package_builder import read_package
from tests.fixtures import build_pptx, text_shape

HEADERS = {"X-Institution-Id": "university-001"}
OTHER_TENANT = {"X-Institution-Id": "university-002"}


# -- fixtures / helpers ------------------------------------------------------------


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


def _upload(client, course_id: str, data: bytes, filename: str = "lecture.pptx") -> str:
    response = client.post(
        f"/courses/{course_id}/materials",
        files={"file": (filename, data, "application/octet-stream")},
        headers=HEADERS,
    )
    assert response.status_code == 202, response.text
    return response.json()["artifact_id"]


def _publish_version(client, course_id: str, data: bytes, filename: str = "lecture.pptx") -> dict:
    """upload -> build the package -> approve -> publish. The state ``start`` requires."""

    artifact_id = _upload(client, course_id, data, filename)
    built = client.post(f"/artifacts/{artifact_id}/review-package", headers=HEADERS)
    assert built.status_code == 200, built.text
    body = built.json()
    assert body["publishable"] is True, body
    decided = client.post(
        f"/artifacts/{artifact_id}/review-package/decision",
        json={"decision": "APPROVE", "reviewer": "teacher@university-001"},
        headers=HEADERS,
    )
    assert decided.status_code == 200, decided.text
    published = client.post(
        f"/course-versions/{decided.json()['version_id']}/publish", headers=HEADERS
    )
    assert published.status_code == 200, published.text
    return {
        "artifact_id": artifact_id,
        "version_id": decided.json()["version_id"],
        "package_id": body["package_id"],
        "content_package_version": body["content_package_version"],
        "prefix": body["prefix"],
        "publication": published.json(),
    }


def _schedule(client, course_id: str, **params) -> dict:
    response = client.post(
        "/classes", params={"course_id": course_id, **params}, headers=HEADERS
    )
    assert response.status_code == 201, response.text
    return response.json()


def _start(client, class_id: str, headers: dict = HEADERS):
    return client.post(f"/classes/{class_id}/start", headers=headers)


def _repository(client) -> ClassRepository:
    return client.app.state.classroom_service._repository


def _counts(client) -> dict:
    return _repository(client).count_rows("university-001")


class _CapturingLogger:
    def __init__(self) -> None:
        self.records: list[str] = []

    def info(self, message: str, *args) -> None:  # noqa: ANN002 - mirrors logging.Logger.info
        self.records.append(message % args if args else message)


class _FixedCatalog(RuntimeCatalog):
    """A catalog standing in for a policy/region source that does not exist yet."""

    def __init__(self, **overrides) -> None:
        base = {
            "policy_version": "runtime-policy@7",
            "region": "eu-west-9",
            "supported_ctf_schema_versions": ("1.0.0",),
        }
        base.update(overrides)
        self._defaults = RuntimeDefaults(**base)

    def defaults(self) -> RuntimeDefaults:
        return self._defaults


class _Clock:
    """A clock a test can move forward (token expiry is bounded, and provable)."""

    def __init__(self) -> None:
        self.now = datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now


# -- the happy path ---------------------------------------------------------------


def test_starting_a_class_pins_the_exact_tuple_and_goes_active(client):
    course_id = _course(client)
    published = _publish_version(client, course_id, _deck())
    scheduled = _schedule(client, course_id, title="Lecture 1")

    assert scheduled["state"] == CLASSROOM_STATE_SCHEDULED
    assert scheduled["started_at"] is None

    started = _start(client, scheduled["class_id"])
    assert started.status_code == 200, started.text
    body = started.json()

    assert body["created"] is True
    assert body["class"]["state"] == CLASSROOM_STATE_ACTIVE
    assert body["class"]["started_at"] is not None

    session = body["session"]
    assert session["state"] == CLASSROOM_STATE_ACTIVE
    assert session["actor_epoch"] == INITIAL_ACTOR_EPOCH
    assert session["state_version"] == INITIAL_STATE_VERSION
    assert session["event_sequence"] == INITIAL_EVENT_SEQUENCE
    assert session["snapshot_id"] == body["snapshot"]["snapshot_id"]

    # Every member of the canonical runtime tuple is a resolved value, not a pointer.
    versions = body["session_plan"]["versions"]
    publication = published["publication"]
    assert versions["course_id"] == course_id
    assert versions["version_id"] == published["version_id"]
    assert versions["course_version"] == publication["course_version"]
    assert versions["publication_id"] == publication["publication_id"]
    assert versions["package_id"] == published["package_id"]
    assert versions["content_package_version"] == published["content_package_version"]
    assert versions["content_digest"] == publication["content_digest"]
    assert versions["lesson_plan_version"] == publication["lesson_plan_versions"][0]
    assert versions["knowledge_index_version"] == publication["knowledge_index_version"]
    assert versions["index_version_id"] == publication["index_version_id"]
    assert versions["index_source_digest"] == publication["content_digest"]
    assert versions["teaching_graph_version"] is None
    # Named absences: V0 has neither subsystem, and the tuple says so explicitly.
    assert versions["assessment_version"] is None
    assert versions["model_routing_version"] is None
    assert versions["policy_version"] == "runtime-policy@1"
    assert versions["region"] == "local-1"
    assert versions["capability_version"], "the warmed renderer identity is pinned"

    # The pinned tuple is readable afterwards, and the tuple was resolved once.
    view = client.get(f"/classes/{scheduled['class_id']}", headers=HEADERS).json()
    assert view["session_plan"]["versions"] == versions
    assert view["class"]["state"] == CLASSROOM_STATE_ACTIVE


def test_scheduling_records_when_but_does_not_enforce_it(client):
    course_id = _course(client)
    scheduled = _schedule(client, course_id, scheduled_for="2026-11-01T09:00:00+00:00")
    assert scheduled["scheduled_for"] == "2026-11-01T09:00:00+00:00"
    assert scheduled["state"] == CLASSROOM_STATE_SCHEDULED

    bad = client.post(
        "/classes",
        params={"course_id": course_id, "scheduled_for": "tomorrow-ish"},
        headers=HEADERS,
    )
    assert bad.status_code == 400, bad.text
    assert bad.json()["error"]["code"] == "INVALID_REQUEST"


def test_the_initial_snapshot_records_every_region(client):
    course_id = _course(client)
    _publish_version(client, course_id, _deck())
    class_id = _schedule(client, course_id)["class_id"]
    started = _start(client, class_id).json()

    snapshot = client.get(f"/classes/{class_id}/snapshot", headers=HEADERS).json()
    document = snapshot["document"]

    assert snapshot["schema_version"] == SNAPSHOT_SCHEMA_VERSION
    assert snapshot["state"] == CLASSROOM_STATE_ACTIVE
    assert snapshot["actor_epoch"] == INITIAL_ACTOR_EPOCH
    assert snapshot["state_version"] == INITIAL_STATE_VERSION
    assert snapshot["event_sequence"] == INITIAL_EVENT_SEQUENCE
    assert snapshot["checksum"] == snapshot_checksum(document)
    assert document["versions"] == started["session_plan"]["versions"]
    # Lesson/scene/step: positioned at the first step of the *pinned* plan.
    assert document["lesson"]["section_index"] == 0
    assert document["lesson"]["section_id"]
    assert document["lesson"]["scene_id"] is not None
    assert document["lesson"]["lesson_plan_version"] == document["versions"]["lesson_plan_version"]
    # Queue/floor/pending effects at their starting values: a session starts with no
    # floor, which is how "at most one floor" and "non-active states have no valid
    # floor" hold from the first moment.
    assert document["turn"] == {"queue": [], "floor": None, "stt_reservation": None}
    assert document["pending_effects"] == []
    assert document["timeline"]["checkpoint"] is None


def test_the_runtime_catalog_supplies_policy_region_and_capability(client):
    course_id = _course(client)
    _publish_version(client, course_id, _deck())
    class_id = _schedule(client, course_id)["class_id"]

    service = client.app.state.classroom_service
    service._catalog = _FixedCatalog()
    service._capability_probe = lambda: {
        "identity": {
            "name": "mentora-themed-svg",
            "version": "4.0.0",
            "engine": "svg",
            "config_hash": "abc123",
            "data_region": "eu-west-9",
        },
        "support": {"supports": True, "fidelity_ceiling": "THEMED"},
    }

    versions = _start(client, class_id).json()["session_plan"]["versions"]
    assert versions["policy_version"] == "runtime-policy@7"
    assert versions["region"] == "eu-west-9"
    assert versions["capability_version"] == "mentora-themed-svg@4.0.0"


# -- the required failures --------------------------------------------------------


def test_a_draft_version_is_refused_and_writes_nothing(client):
    """A version that was never published must not be pinned — explicitly or implicitly."""

    course_id = _course(client)
    artifact_id = _upload(client, course_id, _deck())
    built = client.post(f"/artifacts/{artifact_id}/review-package", headers=HEADERS).json()
    assert built["publishable"] is True
    draft_version = client.get(f"/artifacts/{artifact_id}", headers=HEADERS).json()["version_id"]

    # 1. A class pinned to that (draft) version.
    pinned = _schedule(client, course_id, version_id=draft_version)
    # 2. A class that would have to resolve a published version, and there is none.
    unresolved = _schedule(client, course_id)

    for class_id in (pinned["class_id"], unresolved["class_id"]):
        response = _start(client, class_id)
        assert response.status_code == 409, response.text
        error = response.json()["error"]
        assert error["code"] == "CLASS_NOT_READY"
        assert error["issue_code"] == "VERSION_NOT_PUBLISHED"

    assert _counts(client) == {
        "classes": 2,
        "enrollments": 0,
        "session_plans": 0,
        "sessions": 0,
        "snapshots": 0,
        "bootstrap_tokens": 0,
    }
    for class_id in (pinned["class_id"], unresolved["class_id"]):
        assert client.get(f"/classes/{class_id}", headers=HEADERS).json()["session"] is None
        assert (
            client.get(f"/classes/{class_id}/snapshot", headers=HEADERS).status_code == 404
        )

    # A version that is scheduled but does not belong to the course is refused too.
    other_course = _course(client, "Another course")
    foreign = client.post(
        "/classes",
        params={"course_id": other_course, "version_id": draft_version},
        headers=HEADERS,
    )
    assert foreign.status_code == 400
    assert foreign.json()["error"]["code"] == "INVALID_REQUEST"


def test_an_incompatible_index_pin_is_refused(client):
    """``DEC-DATA-005``: a pin that is not *about* this content must not be used."""

    course_id = _course(client)
    published = _publish_version(client, course_id, _deck())
    class_id = _schedule(client, course_id)["class_id"]
    repository = _repository(client)
    version_id = published["version_id"]
    content_version = published["content_package_version"]

    repository._conn.execute(
        "UPDATE knowledge_index_versions SET source_digest = ? "
        "WHERE institution_id = ? AND version_id = ? AND content_package_version = ?",
        ("0" * 64, "university-001", version_id, content_version),
    )
    response = _start(client, class_id)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["issue_code"] == "INCOMPATIBLE_INDEX"

    repository._conn.execute(
        "UPDATE knowledge_index_versions SET source_digest = ?, index_version = ? "
        "WHERE institution_id = ? AND version_id = ? AND content_package_version = ?",
        (published["publication"]["content_digest"], "index@9", "university-001", version_id,
         content_version),
    )
    response = _start(client, class_id)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["issue_code"] == "INCOMPATIBLE_INDEX"

    assert _counts(client)["sessions"] == 0


def test_a_damaged_package_is_refused(client):
    """A session never starts on bytes that do not match their seal."""

    course_id = _course(client)
    published = _publish_version(client, course_id, _deck())
    class_id = _schedule(client, course_id)["class_id"]

    store = client.app.state.classroom_service._object_store
    loaded = read_package(store, published["prefix"])
    assert loaded is not None
    victim = next(path for path in loaded.package.paths() if path.startswith("assets/"))
    store.put(f"{published['prefix']}/{victim}", b"<svg>overwritten</svg>")

    response = _start(client, class_id)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["issue_code"] == "CONTENT_DIGEST_MISMATCH"

    # A package whose envelope this runtime does not support is refused as well.
    service = client.app.state.classroom_service
    service._catalog = _FixedCatalog(supported_ctf_schema_versions=("9.9.9",))
    store.put(f"{published['prefix']}/{victim}", loaded.data(victim))
    response = _start(client, class_id)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["issue_code"] == "INCOMPATIBLE_CONTENT"

    assert _counts(client)["sessions"] == 0


def test_a_failed_start_writes_nothing_and_a_retry_succeeds(client):
    """``PREPARING`` is in-flight only: a refusal leaves the class exactly as it was."""

    course_id = _course(client)
    artifact_id = _upload(client, course_id, _deck())
    client.post(f"/artifacts/{artifact_id}/review-package", headers=HEADERS)
    version_id = client.get(f"/artifacts/{artifact_id}", headers=HEADERS).json()["version_id"]
    class_id = _schedule(client, course_id)["class_id"]

    assert _start(client, class_id).status_code == 409
    assert _counts(client) == {
        "classes": 1,
        "enrollments": 0,
        "session_plans": 0,
        "sessions": 0,
        "snapshots": 0,
        "bootstrap_tokens": 0,
    }
    stored = client.get(f"/classes/{class_id}", headers=HEADERS).json()
    assert stored["class"]["state"] == CLASSROOM_STATE_SCHEDULED
    assert stored["class"]["started_at"] is None

    # Fix the precondition (approve + publish) and retry: one clean session.
    client.post(
        f"/artifacts/{artifact_id}/review-package/decision",
        json={"decision": "APPROVE", "reviewer": "teacher"},
        headers=HEADERS,
    )
    assert client.post(f"/course-versions/{version_id}/publish", headers=HEADERS).status_code == 200
    retried = _start(client, class_id)
    assert retried.status_code == 200, retried.text
    assert retried.json()["created"] is True
    assert _counts(client)["sessions"] == 1


# -- idempotency ------------------------------------------------------------------


def test_a_duplicate_start_returns_the_same_session(client):
    """``DEC-RUNTIME-003``: a repeated start is one logical effect, not a second session."""

    course_id = _course(client)
    _publish_version(client, course_id, _deck())
    class_id = _schedule(client, course_id)["class_id"]

    first = _start(client, class_id).json()
    second = _start(client, class_id)
    assert second.status_code == 200, second.text
    replay = second.json()

    assert replay["created"] is False
    assert replay["session"]["session_id"] == first["session"]["session_id"]
    assert replay["session_plan"] == first["session_plan"]
    assert replay["snapshot"] == first["snapshot"]
    assert _counts(client) == {
        "classes": 1,
        "enrollments": 0,
        "session_plans": 1,
        "sessions": 1,
        "snapshots": 1,
        "bootstrap_tokens": 0,
    }


def test_concurrent_starts_create_one_session(settings):
    """Two requests race: one commits, one replays the winner."""

    app = create_app(settings)
    with TestClient(app) as client:
        course_id = _course(client)
        _publish_version(client, course_id, _deck())
        class_id = _schedule(client, course_id)["class_id"]
        service = app.state.classroom_service

        barrier = threading.Barrier(2)

        def attempt():
            barrier.wait()
            return service.start_class("university-001", class_id)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [future.result() for future in [pool.submit(attempt), pool.submit(attempt)]]

    session_ids = {result.session.session_id for result in results}
    assert len(session_ids) == 1, "one class, one session"
    assert sum(1 for result in results if result.created) == 1
    assert _counts(client)["sessions"] == 1
    assert _counts(client)["snapshots"] == 1


# -- no runtime "latest" lookup ---------------------------------------------------


def test_the_pinned_tuple_does_not_follow_a_newer_publication(client):
    """Publishing a correction after a start must not move the running session."""

    course_id = _course(client)
    first = _publish_version(client, course_id, _deck(label="First"))
    class_a = _schedule(client, course_id)["class_id"]
    started = _start(client, class_a).json()
    pinned = started["session_plan"]["versions"]
    snapshot_before = client.get(f"/classes/{class_a}/snapshot", headers=HEADERS).json()

    assert pinned["version_id"] == first["version_id"]
    assert pinned["course_version"] == 1

    # A correction: new bytes, new course version, new publication (V0-008).
    second = _publish_version(client, course_id, _deck(label="Corrected"))
    assert second["version_id"] != first["version_id"]
    assert second["publication"]["state"] == "PUBLISHED"
    superseded = client.get(
        f"/publications/{first['publication']['publication_id']}", headers=HEADERS
    ).json()
    assert superseded["state"] == "SUPERSEDED"

    # The running session is untouched — tuple *and* snapshot, byte for byte.
    after = client.get(f"/classes/{class_a}", headers=HEADERS).json()
    assert after["session_plan"]["versions"] == pinned
    assert after["session_plan"]["versions"]["version_id"] == first["version_id"]
    assert after["session_plan"]["capabilities"] == started["session_plan"]["capabilities"]
    assert client.get(f"/classes/{class_a}/snapshot", headers=HEADERS).json() == snapshot_before

    # A class started afterwards pins the new version: resolution happens once, at
    # start, and never again for a session that already ran.
    class_b = _schedule(client, course_id)["class_id"]
    newer = _start(client, class_b).json()["session_plan"]["versions"]
    assert newer["version_id"] == second["version_id"]
    assert newer["course_version"] == 2
    assert newer["publication_id"] == second["publication"]["publication_id"]


def test_a_class_may_pin_a_named_older_version(client):
    """An explicit pin is honoured, superseded or not (``DEC-CONTENT-005``)."""

    course_id = _course(client)
    first = _publish_version(client, course_id, _deck(label="First"))
    second = _publish_version(client, course_id, _deck(label="Corrected"))
    assert second["publication"]["state"] == "PUBLISHED"

    class_id = _schedule(client, course_id, version_id=first["version_id"])["class_id"]
    versions = _start(client, class_id).json()["session_plan"]["versions"]
    assert versions["version_id"] == first["version_id"]
    assert versions["content_package_version"] == first["content_package_version"]


def test_the_pinned_tuple_survives_a_restart(client, settings):
    """A restart reads the pinned tuple from the store; nothing is re-resolved."""

    course_id = _course(client)
    _publish_version(client, course_id, _deck())
    class_id = _schedule(client, course_id)["class_id"]
    started = _start(client, class_id).json()
    snapshot = client.get(f"/classes/{class_id}/snapshot", headers=HEADERS).json()

    # A brand new app instance (fresh connections) on the same durable store.
    with TestClient(create_app(settings)) as restarted:
        view = restarted.get(f"/classes/{class_id}", headers=HEADERS).json()
        assert view["class"]["state"] == CLASSROOM_STATE_ACTIVE
        assert view["session"]["session_id"] == started["session"]["session_id"]
        assert view["session_plan"]["versions"] == started["session_plan"]["versions"]
        assert view["session_plan"]["created_at"] == started["session_plan"]["created_at"]
        assert (
            restarted.get(f"/classes/{class_id}/snapshot", headers=HEADERS).json() == snapshot
        )
        # The idempotent replay still returns the *original* session.
        replay = restarted.post(f"/classes/{class_id}/start", headers=HEADERS).json()
        assert replay["created"] is False
        assert replay["session_plan"]["versions"] == started["session_plan"]["versions"]


def test_a_tampered_snapshot_is_refused(client):
    """Snapshot/checksum/schema validated before replay (``DEC-DATA-004``)."""

    course_id = _course(client)
    _publish_version(client, course_id, _deck())
    class_id = _schedule(client, course_id)["class_id"]
    _start(client, class_id)
    connection = _repository(client)._conn

    document = client.get(f"/classes/{class_id}/snapshot", headers=HEADERS).json()["document"]
    tampered = {**document, "state": "COMPLETED"}
    connection.execute(
        "UPDATE session_snapshots SET document = ? WHERE class_id = ?",
        (json.dumps(tampered), class_id),
    )
    response = client.get(f"/classes/{class_id}/snapshot", headers=HEADERS)
    assert response.status_code == 502, response.text
    assert response.json()["error"]["code"] == "STORAGE_FAILURE"
    assert response.json()["error"]["issue_code"] == "SNAPSHOT_INVALID"

    connection.execute(
        "UPDATE session_snapshots SET schema_version = ? WHERE class_id = ?",
        ("runtime-snapshot@99", class_id),
    )
    response = client.get(f"/classes/{class_id}/snapshot", headers=HEADERS)
    assert response.status_code == 502, response.text
    assert response.json()["error"]["issue_code"] == "SNAPSHOT_INVALID"


# -- enrollment and join ----------------------------------------------------------


def test_join_requires_enrollment(client):
    """Only authorized enrollment can join; another tenant cannot even ask."""

    course_id = _course(client)
    _publish_version(client, course_id, _deck())
    class_id = _schedule(client, course_id)["class_id"]
    _start(client, class_id)
    students = "students/ana"

    refused = client.post(
        f"/classes/{class_id}/bootstrap-token",
        json={"student_id": students},
        headers=HEADERS,
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["error"]["code"] == "NOT_ENROLLED"

    # Cross-tenant: the class is not visible at all.
    cross_tenant = client.post(
        f"/classes/{class_id}/bootstrap-token",
        json={"student_id": students},
        headers=OTHER_TENANT,
    )
    assert cross_tenant.status_code == 403, cross_tenant.text
    assert cross_tenant.json()["error"]["code"] == "TENANT_ACCESS_DENIED"

    enrolled = client.post(
        f"/classes/{class_id}/enrollments", params={"student_id": students}, headers=HEADERS
    )
    assert enrolled.status_code == 200, enrolled.text
    assert enrolled.json()["created"] is True

    issued = client.post(
        f"/classes/{class_id}/bootstrap-token",
        json={"student_id": students},
        headers=HEADERS,
    )
    assert issued.status_code == 200, issued.text
    token = issued.json()
    assert token["class_id"] == class_id
    assert token["student_id"] == students
    assert token["scopes"] == ["subscribe"], "student media permission is subscribe-only"
    assert token["actor_epoch"] == INITIAL_ACTOR_EPOCH
    assert token["expires_at"] > token["issued_at"]
    assert len(token["token"]) >= 32

    # A different student is still refused.
    other = client.post(
        f"/classes/{class_id}/bootstrap-token",
        json={"student_id": "students/bob"},
        headers=HEADERS,
    )
    assert other.status_code == 403
    assert other.json()["error"]["code"] == "NOT_ENROLLED"


def test_enrollment_is_idempotent_and_tenant_scoped(client):
    course_id = _course(client)
    class_id = _schedule(client, course_id)["class_id"]

    first = client.post(
        f"/classes/{class_id}/enrollments", params={"student_id": "students/ana"}, headers=HEADERS
    )
    second = client.post(
        f"/classes/{class_id}/enrollments", params={"student_id": "students/ana"}, headers=HEADERS
    )
    assert first.json()["created"] is True
    assert second.json()["created"] is False
    assert first.json()["enrollment_id"] == second.json()["enrollment_id"]

    roster = client.get(f"/classes/{class_id}/enrollments", headers=HEADERS).json()
    assert [item["student_id"] for item in roster["enrollments"]] == ["students/ana"]

    assert (
        client.get(f"/classes/{class_id}/enrollments", headers=OTHER_TENANT).status_code == 403
    )


def test_joining_before_start_is_refused(client):
    course_id = _course(client)
    _publish_version(client, course_id, _deck())
    class_id = _schedule(client, course_id)["class_id"]
    client.post(
        f"/classes/{class_id}/enrollments", params={"student_id": "students/ana"}, headers=HEADERS
    )

    response = client.post(
        f"/classes/{class_id}/bootstrap-token",
        json={"student_id": "students/ana"},
        headers=HEADERS,
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"]["issue_code"] == "NOT_STARTED"


def test_the_bootstrap_token_is_not_stored_in_the_clear(client):
    course_id = _course(client)
    _publish_version(client, course_id, _deck())
    class_id = _schedule(client, course_id)["class_id"]
    _start(client, class_id)
    client.post(
        f"/classes/{class_id}/enrollments", params={"student_id": "students/ana"}, headers=HEADERS
    )
    token = client.post(
        f"/classes/{class_id}/bootstrap-token",
        json={"student_id": "students/ana"},
        headers=HEADERS,
    ).json()["token"]

    rows = _repository(client)._conn.execute("SELECT * FROM bootstrap_tokens").fetchall()
    assert len(rows) == 1
    row = rows[0]
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert row["token_sha256"] == digest
    assert token not in json.dumps(dict(row)), "a stored row must not yield a usable credential"
    assert json.loads(row["scopes"]) == ["subscribe"]
    assert row["revoked_at"] is None
    assert row["nonce"]


def test_a_token_is_bound_to_its_epoch_and_lifetime(client):
    """``DEC-RUNTIME-007``: a stale epoch cannot authorize; tokens expire or revoke."""

    course_id = _course(client)
    _publish_version(client, course_id, _deck())
    class_id = _schedule(client, course_id)["class_id"]
    _start(client, class_id)
    client.post(
        f"/classes/{class_id}/enrollments", params={"student_id": "students/ana"}, headers=HEADERS
    )
    service = client.app.state.classroom_service
    clock = _Clock()
    service._clock = clock
    token = service.issue_bootstrap_token("university-001", class_id, "students/ana").token

    assert service.verify_bootstrap_token("university-001", class_id, token).student_id == "students/ana"

    # An unknown token and another tenant's token are indistinguishable by design.
    with pytest.raises(JoinDeniedError) as unknown:
        service.verify_bootstrap_token("university-001", class_id, "not-a-token")
    assert unknown.value.issue_code == ISSUE_TOKEN_UNKNOWN
    with pytest.raises(JoinDeniedError) as foreign:
        service.verify_bootstrap_token("university-002", class_id, token)
    assert foreign.value.issue_code == ISSUE_TOKEN_UNKNOWN

    # Expiry is the terminal path for a token nobody revoked.
    clock.now = clock.now + timedelta(seconds=301)
    with pytest.raises(JoinDeniedError) as expired:
        service.verify_bootstrap_token("university-001", class_id, token)
    assert expired.value.issue_code == ISSUE_TOKEN_EXPIRED

    # Revocation is the other terminal path, and it is idempotent-safe.
    clock.now = datetime(2026, 10, 17, 9, 1, tzinfo=timezone.utc)
    fresh = service.issue_bootstrap_token("university-001", class_id, "students/ana").token
    assert service.revoke_bootstrap_token("university-001", fresh) is True
    assert service.revoke_bootstrap_token("university-001", fresh) is False
    with pytest.raises(JoinDeniedError) as revoked:
        service.verify_bootstrap_token("university-001", class_id, fresh)
    assert revoked.value.issue_code == ISSUE_TOKEN_REVOKED

    # A token issued in an epoch the session has left cannot authorize.
    clock.now = datetime(2026, 10, 17, 9, 2, tzinfo=timezone.utc)
    epoch_bound = service.issue_bootstrap_token("university-001", class_id, "students/ana").token
    _repository(client)._conn.execute(
        "UPDATE classroom_sessions SET actor_epoch = 2 WHERE class_id = ?", (class_id,)
    )
    with pytest.raises(JoinDeniedError) as stale:
        service.verify_bootstrap_token("university-001", class_id, epoch_bound)
    assert stale.value.issue_code == ISSUE_STALE_EPOCH


# -- tenancy and telemetry --------------------------------------------------------


def test_class_start_is_tenant_isolated(client):
    course_id = _course(client)
    _publish_version(client, course_id, _deck())
    class_id = _schedule(client, course_id)["class_id"]
    _start(client, class_id)

    for path in (
        f"/classes/{class_id}",
        f"/classes/{class_id}/snapshot",
        f"/classes/{class_id}/enrollments",
    ):
        response = client.get(path, headers=OTHER_TENANT)
        assert response.status_code == 403, (path, response.text)
        assert response.json()["error"]["code"] == "TENANT_ACCESS_DENIED"

    assert _start(client, class_id, headers=OTHER_TENANT).status_code == 403
    assert client.get("/classes", headers=OTHER_TENANT).json() == []
    assert client.get("/classes/does-not-exist", headers=HEADERS).status_code == 404


def test_class_telemetry_carries_identities_not_content(client):
    course_id = _course(client)
    _publish_version(client, course_id, _deck())
    class_id = _schedule(client, course_id, title="Lecture 1")["class_id"]
    service = client.app.state.classroom_service
    logger = _CapturingLogger()
    service.telemetry._logger = logger

    _start(client, class_id)
    client.post(
        f"/classes/{class_id}/enrollments", params={"student_id": "students/ana"}, headers=HEADERS
    )
    service.issue_bootstrap_token("university-001", class_id, "students/ana")

    events = [json.loads(record) for record in logger.records]
    started = next(event for event in events if event["event"] == "class.started")
    assert started["class_id"] == class_id
    assert started["institution_id"] == "university-001"
    assert started["content_package_version"]
    assert started["policy_version"] == "runtime-policy@1"
    assert started["region"] == "local-1"
    assert started["created"] is True
    # The class title is authored text: presence only, never the text.
    assert "Lecture 1" not in json.dumps(events)
    assert service.telemetry.metrics.sessions_started == 1
    assert service.telemetry.metrics.joins_authorized == 1


def test_a_blocked_start_emits_its_issue_code(client):
    course_id = _course(client)
    class_id = _schedule(client, course_id)["class_id"]
    service = client.app.state.classroom_service
    logger = _CapturingLogger()
    service.telemetry._logger = logger

    assert _start(client, class_id).status_code == 409
    events = [json.loads(record) for record in logger.records]
    blocked = next(event for event in events if event["event"] == "class.start_blocked")
    assert blocked["issue_code"] == "VERSION_NOT_PUBLISHED"
    assert blocked["stage"] == "RESOLVING"
    assert service.telemetry.metrics.starts_blocked == 1
    assert service.telemetry.metrics.sessions_started == 0
