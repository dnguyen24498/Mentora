"""V0-008 atomic publication: the acceptance paths, end to end (API level).

``tests/integration/`` does not exist in this repo; ``backend/tests/`` is its test
root (same nominal-path mapping as V0-004…V0-007). Every test drives the real
FastAPI app, the real SQLite store and the real local object store.

The three acceptance criteria and the five required tests map like this:

* **Partial failure never exposes published version** —
  ``test_crash_between_stages_leaves_nothing_published`` (per stage),
  ``test_a_checksum_failure_is_refused_and_writes_nothing``,
  ``test_an_index_failure_blocks_publication``;
* **Published bytes cannot be overwritten** — ``test_publishing_writes_no_package_bytes``,
  ``test_publishing_a_correction_leaves_the_old_bytes_readable``,
  ``test_a_tampered_published_package_is_detected``;
* **Correction creates new version** — ``test_publishing_a_correction_leaves_the_old_bytes_readable``;
* **duplicate publish** — ``test_a_duplicate_publish_is_idempotent`` and
  ``test_concurrent_duplicate_publishes_create_one_publication``;
* **index failure**, **checksum failure**, **crash between stages**, **read old version**
  — as above.

Plus the requirements the task names: approval precondition, tenant isolation,
the knowledge-index pin (``DEC-DATA-005``), the transactional outbox, and
telemetry that carries identities but not authored text.
"""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.compiler.package_builder import read_package
from app.courses.models import CourseVersionStatus
from app.publication.index import IndexBuilder
from app.publication.models import (
    INDEX_STATUS_UNINDEXED,
    PUBLICATION_STATE_PUBLISHED,
    PUBLICATION_STATE_SUPERSEDED,
    Publication,
)
from app.publication.repository import PublicationRepository
from app.publication.seal import INTEGRITY_MISMATCH, INTEGRITY_VERIFIED
from tests.fixtures import build_pptx, text_shape

HEADERS = {"X-Institution-Id": "university-001"}


# -- fixtures / helpers ------------------------------------------------------------


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


def _upload(client, course_id: str, data: bytes, filename: str = "lecture.pptx") -> str:
    response = client.post(
        f"/courses/{course_id}/materials",
        files={"file": (filename, data, "application/octet-stream")},
        headers=HEADERS,
    )
    assert response.status_code == 202, response.text
    return response.json()["artifact_id"]


def _prepare(client, course_id: str, data: bytes, filename: str = "lecture.pptx") -> dict:
    """upload -> build the package -> approve. The state ``publish`` requires."""

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
    return {
        "artifact_id": artifact_id,
        "version_id": decided.json()["version_id"],
        "package_id": body["package_id"],
        "content_package_version": body["content_package_version"],
        "prefix": body["prefix"],
    }


def _publish(client, version_id: str, **kwargs):
    return client.post(f"/course-versions/{version_id}/publish", headers=HEADERS, **kwargs)


def _repository(client) -> PublicationRepository:
    service = client.app.state.publication_service
    assert isinstance(service._publications, PublicationRepository)
    return service._publications


def _version_status(client, version_id: str) -> str:
    return client.app.state.repository.get_version("university-001", version_id).status


def _tamper(client, prefix: str, data: bytes = b"<svg>overwritten</svg>") -> None:
    """Overwrite a package asset the way a stray writer would."""

    store = client.app.state.publication_service._object_store
    loaded = read_package(store, prefix)
    assert loaded is not None
    victim = next(path for path in loaded.package.paths() if path.startswith("assets/"))
    store.put(f"{prefix}/{victim}", data)


class _RecordingStore:
    """An object store that records every write, to prove publish writes nothing."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.puts: list[str] = []

    def put(self, key: str, data: bytes) -> str:
        self.puts.append(key)
        return self._inner.put(key, data)

    def get(self, key: str) -> bytes:
        return self._inner.get(key)

    def exists(self, key: str) -> bool:
        return self._inner.exists(key)


class _FailingIndex(IndexBuilder):
    """An index builder that cannot establish an identity (a V0-014-style failure)."""

    def build(self, **kwargs):  # noqa: ANN003 - matches the interface
        raise RuntimeError("index store unavailable")


class _ExplodingPublicationRepository(PublicationRepository):
    """A repository whose commit dies: the process crashed at COMMITTING."""

    def commit(self, **kwargs):  # noqa: ANN003 - matches the signature
        raise RuntimeError("process died before the publication commit point")


class _CapturingLogger:
    def __init__(self) -> None:
        self.records: list[str] = []

    def info(self, message: str, *args) -> None:  # noqa: ANN002 - mirrors logging.Logger.info
        self.records.append(message % args if args else message)


# -- the happy path ---------------------------------------------------------------


def test_publishing_an_approved_version_commits_once_and_is_readable(client):
    prepared = _prepare(client, _course(client), _deck())

    published = _publish(client, prepared["version_id"])
    assert published.status_code == 200, published.text
    body = published.json()

    assert body["created"] is True
    assert body["state"] == PUBLICATION_STATE_PUBLISHED
    assert body["version_id"] == prepared["version_id"]
    assert body["package_id"] == prepared["package_id"]
    assert body["content_package_version"] == prepared["content_package_version"]
    assert body["course_version"] == 1
    assert body["superseded_by"] is None
    assert body["published_by"] == "university-001"
    assert body["knowledge_index_version"] == "unindexed"
    assert body["teaching_graph_version"] is None
    assert body["lesson_plan_versions"], "the pinned tuple carries the lesson plan version"
    assert body["file_count"] > 0 and body["total_bytes"] > 0
    assert len(body["content_digest"]) == 64
    assert body["package_prefix"] == f"packages/{prepared['package_id']}"

    # The version is published, and only now.
    assert _version_status(client, prepared["version_id"]) == CourseVersionStatus.PUBLISHED.value

    # Retrievable three ways, all the same publication.
    by_version = client.get(
        f"/course-versions/{prepared['version_id']}/publication", headers=HEADERS
    ).json()
    by_id = client.get(f"/publications/{body['publication_id']}", headers=HEADERS).json()
    history = client.get(
        f"/courses/{body['course_id']}/publications", headers=HEADERS
    ).json()
    assert by_version["publication_id"] == body["publication_id"]
    assert by_id["publication_id"] == body["publication_id"]
    assert [item["publication_id"] for item in history["publications"]] == [
        body["publication_id"]
    ]


def test_the_knowledge_index_pin_is_recorded_with_its_provenance(client):
    prepared = _prepare(client, _course(client), _deck())
    body = _publish(client, prepared["version_id"]).json()

    record = _repository(client).get_index_version(
        "university-001", prepared["version_id"], prepared["content_package_version"]
    )
    assert record is not None, "DEC-DATA-005: a published version pins an index version"
    assert record.index_version_id == body["index_version_id"]
    assert record.index_version == "unindexed"
    assert record.status == INDEX_STATUS_UNINDEXED
    assert record.package_id == prepared["package_id"]
    # The pin records what it is compatible *with*, so a mismatched content digest
    # cannot silently use it.
    assert record.source_digest == body["content_digest"]


def test_the_outbox_row_commits_with_the_publication(client):
    prepared = _prepare(client, _course(client), _deck())
    body = _publish(client, prepared["version_id"]).json()

    events = _repository(client).list_outbox("university-001", body["publication_id"])
    assert len(events) == 1
    event = events[0]
    assert event.event_type == "course.version.published"
    assert event.aggregate_id == body["publication_id"]
    assert event.dispatched is False, "delivery is not part of V0 (DEC-TECH-001 is OPEN)"
    assert event.payload["publication_id"] == body["publication_id"]
    assert event.payload["content_package_version"] == prepared["content_package_version"]
    assert event.payload["knowledge_index_version"] == "unindexed"
    assert event.payload["lesson_plan_versions"] == body["lesson_plan_versions"]
    assert event.event_id in json.dumps(event.payload)


# -- duplicate publish (DEC-RUNTIME-003) ------------------------------------------


def test_a_duplicate_publish_is_idempotent(client):
    prepared = _prepare(client, _course(client), _deck())

    first = _publish(client, prepared["version_id"])
    second = _publish(client, prepared["version_id"], json={"published_by": "someone else"})

    assert first.json()["created"] is True
    assert second.status_code == 200, second.text
    assert second.json()["created"] is False
    assert second.json()["publication_id"] == first.json()["publication_id"]

    repository = _repository(client)
    history = client.get(
        f"/courses/{first.json()['course_id']}/publications", headers=HEADERS
    ).json()["publications"]
    assert len(history) == 1
    assert repository.count_outbox("university-001") == 1
    # The replay did not fork the index pin either: one record for the version,
    # still pointing at the content that was published.
    record = repository.get_index_version(
        "university-001", prepared["version_id"], prepared["content_package_version"]
    )
    assert record is not None
    assert record.status == INDEX_STATUS_UNINDEXED
    assert record.index_version_id == first.json()["index_version_id"]


def test_concurrent_duplicate_publishes_create_one_publication(settings):
    """Two requests for the same version race: one commit, one replay."""

    app = create_app(settings)
    with TestClient(app) as client:
        prepared = _prepare(client, _course(client), _deck())
        service = app.state.publication_service

        barrier = threading.Barrier(2)

        def attempt():
            barrier.wait()
            return service.publish("university-001", prepared["version_id"])

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [future.result() for future in [pool.submit(attempt), pool.submit(attempt)]]

    ids = {publication.publication_id for publication, _ in results}
    assert len(ids) == 1, "the identity is content, so a race cannot create two publications"
    assert sum(1 for _, created in results if created) == 1
    assert app.state.publication_service._publications.count_outbox("university-001") == 1


# -- partial failure is invisible (crash between stages) --------------------------


def test_a_checksum_failure_is_refused_and_writes_nothing(client):
    """SEALING: the stored package no longer matches its manifest."""

    prepared = _prepare(client, _course(client), _deck())
    _tamper(client, prepared["prefix"])

    response = _publish(client, prepared["version_id"])
    assert response.status_code == 409, response.text
    error = response.json()["error"]
    assert error["code"] == "PUBLICATION_BLOCKED"
    assert error["issue_code"] == "CHECKSUM_MISMATCH"


def test_an_index_failure_blocks_publication(client):
    """INDEXING: the pin cannot be established, so the version must not go out."""

    prepared = _prepare(client, _course(client), _deck())
    service = client.app.state.publication_service
    service._index = _FailingIndex()

    response = _publish(client, prepared["version_id"])
    assert response.status_code == 409, response.text
    error = response.json()["error"]
    assert error["code"] == "PUBLICATION_BLOCKED"
    assert error["issue_code"] == "INDEX_FAILED"


def test_crash_between_stages_leaves_nothing_published(client):
    """Every stage failure leaves the same clean state, and a retry then succeeds.

    This is the acceptance criterion "Partial failure never exposes published
    version", asserted positively (nothing is readable) *and* negatively (nothing
    was written): no publication, no index record, no outbox row, and the version
    is still APPROVED — not PUBLISHED and not stuck.
    """

    prepared = _prepare(client, _course(client), _deck())
    version_id = prepared["version_id"]
    service = client.app.state.publication_service
    repository = _repository(client)
    real_index = service._index
    real_publications = service._publications

    def assert_nothing_published() -> None:
        assert _version_status(client, version_id) == CourseVersionStatus.APPROVED.value
        assert (
            client.get(f"/course-versions/{version_id}/publication", headers=HEADERS).status_code
            == 404
        )
        assert repository.find_publication(
            "university-001", version_id, prepared["content_package_version"]
        ) is None
        assert repository.get_index_version(
            "university-001", version_id, prepared["content_package_version"]
        ) is None
        assert repository.count_outbox("university-001") == 0

    # 1. A crash before the commit point: the stage ran, the commit never started.
    service._publications = _ExplodingPublicationRepository(repository._conn)
    with pytest.raises(RuntimeError):
        _publish(client, version_id)
    assert_nothing_published()
    service._publications = real_publications

    # 2. A failure inside INDEXING (a builder that cannot establish an identity).
    service._index = _FailingIndex()
    assert _publish(client, version_id).status_code == 409
    assert_nothing_published()
    service._index = real_index

    # 3. A failure inside SEALING (the package was damaged).
    _tamper(client, prepared["prefix"])
    assert _publish(client, version_id).status_code == 409
    assert_nothing_published()

    # 4. The retry after the damage is repaired publishes exactly once.
    service._packages.build("university-001", prepared["artifact_id"])
    recovered = _publish(client, version_id)
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["created"] is True
    assert _version_status(client, version_id) == CourseVersionStatus.PUBLISHED.value
    assert repository.count_outbox("university-001") == 1


# -- the approval precondition ----------------------------------------------------


def test_publish_requires_a_current_approval(client):
    course_id = _course(client)
    artifact_id = _upload(client, course_id, _deck())
    client.post(f"/artifacts/{artifact_id}/review-package", headers=HEADERS)
    version_id = client.app.state.repository.get_artifact(
        "university-001", artifact_id
    ).version_id

    # Never reviewed -> nothing to publish.
    unapproved = _publish(client, version_id)
    assert unapproved.status_code == 409, unapproved.text
    assert unapproved.json()["error"]["issue_code"] == "NOT_APPROVED"
    assert _version_status(client, version_id) == CourseVersionStatus.DRAFT.value

    # Rejected -> still nothing to publish.
    client.post(
        f"/artifacts/{artifact_id}/review-package/decision",
        json={"decision": "REJECT", "reason": "wrong deck", "reviewer": "t"},
        headers=HEADERS,
    )
    assert _publish(client, version_id).json()["error"]["issue_code"] == "NOT_APPROVED"

    # Approved for *other* content (a rebuild under a new renderer/extractor):
    # the acceptance does not cover what would be published.
    client.post(
        f"/artifacts/{artifact_id}/review-package/decision",
        json={"decision": "APPROVE", "reviewer": "t"},
        headers=HEADERS,
    )
    client.app.state.review_repository.record_decision(
        institution_id="university-001",
        artifact_id=artifact_id,
        version_id=version_id,
        package_id="pkg-rebuilt",
        content_package_version="cpv-rebuilt",
        decision="APPROVE",
        reason=None,
        reviewer="t",
    )
    stale = _publish(client, version_id)
    assert stale.status_code == 409, stale.text
    assert stale.json()["error"]["issue_code"] == "STALE_APPROVAL"
    assert _version_status(client, version_id) == CourseVersionStatus.APPROVED.value
    assert _repository(client).count_outbox("university-001") == 0


def test_publishing_without_a_built_package_is_not_found(client):
    course_id = _course(client)
    artifact_id = _upload(client, course_id, _deck())
    version_id = client.app.state.repository.get_artifact(
        "university-001", artifact_id
    ).version_id

    response = _publish(client, version_id)
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "NOT_FOUND"


# -- published bytes are pinned ---------------------------------------------------


def test_publishing_writes_no_package_bytes(client):
    """The transition reads and pins; it never writes the object store at all."""

    prepared = _prepare(client, _course(client), _deck())
    service = client.app.state.publication_service
    real_store = service._object_store
    recorder = _RecordingStore(real_store)
    service._object_store = recorder

    before = read_package(real_store, prepared["prefix"])
    assert before is not None
    assert _publish(client, prepared["version_id"]).status_code == 200
    service._object_store = real_store

    assert recorder.puts == [], "publication must not write object storage"
    after = read_package(real_store, prepared["prefix"])
    assert after is not None
    assert after.manifest == before.manifest
    assert after.package.paths() == before.package.paths()
    assert all(
        after.data(path) == before.data(path) for path in before.package.paths()
    )


def test_publishing_a_correction_leaves_the_old_bytes_readable(client):
    """A correction is a *new version*: new package, new publication, old one linked."""

    course_id = _course(client)
    first = _prepare(client, course_id, _deck(label="Old"))
    published_first = _publish(client, first["version_id"]).json()

    # The teacher uploads a corrected deck: a new course version with its own package.
    second = _prepare(client, course_id, _deck(label="New"), filename="lecture-fixed.pptx")
    assert second["version_id"] != first["version_id"]
    assert second["package_id"] != first["package_id"]
    published_second = _publish(client, second["version_id"]).json()

    assert published_second["course_version"] == 2
    assert published_second["superseded_by"] is None

    # The old publication is superseded, not deleted, and still readable.
    old = client.get(f"/publications/{published_first['publication_id']}", headers=HEADERS).json()
    assert old["state"] == PUBLICATION_STATE_SUPERSEDED
    assert old["superseded_by"] == published_second["publication_id"]
    assert old["content_digest"] == published_first["content_digest"]
    by_version = client.get(
        f"/course-versions/{first['version_id']}/publication", headers=HEADERS
    ).json()
    assert by_version["publication_id"] == published_first["publication_id"]

    history = client.get(f"/courses/{course_id}/publications", headers=HEADERS).json()
    assert [item["publication_id"] for item in history["publications"]] == [
        published_second["publication_id"],
        published_first["publication_id"],
    ]
    assert {item["state"] for item in history["publications"]} == {
        PUBLICATION_STATE_PUBLISHED,
        PUBLICATION_STATE_SUPERSEDED,
    }
    # The supersede is a visible effect of the publishing transaction, and it is
    # counted as one.
    assert client.app.state.publication_service.telemetry.metrics.supersessions == 1

    # Both pinned packages are still exactly what was published.
    store = client.app.state.publication_service._object_store
    for publication in (published_first, published_second):
        loaded = read_package(store, f"packages/{publication['package_id']}")
        assert loaded is not None
        verified = client.get(
            f"/publications/{publication['publication_id']}"
            "?verify=true",
            headers=HEADERS,
        ).json()
        assert verified["integrity"]["state"] == INTEGRITY_VERIFIED, verified["integrity"]


def test_a_tampered_published_package_is_detected(client):
    """The seal cannot prevent an overwrite; it makes one observable."""

    prepared = _prepare(client, _course(client), _deck())
    body = _publish(client, prepared["version_id"]).json()

    intact = client.get(
        f"/publications/{body['publication_id']}?verify=true", headers=HEADERS
    ).json()
    assert intact["integrity"]["state"] == INTEGRITY_VERIFIED
    assert intact["integrity"]["observed_digest"] == body["content_digest"]

    _tamper(client, prepared["prefix"])

    tampered = client.get(
        f"/publications/{body['publication_id']}?verify=true", headers=HEADERS
    ).json()
    assert tampered["integrity"]["state"] == INTEGRITY_MISMATCH
    assert tampered["integrity"]["expected_digest"] == body["content_digest"]
    assert tampered["integrity"]["observed_digest"] != body["content_digest"]
    assert "CHECKSUM_MISMATCH" in tampered["integrity"]["issues"]
    # The publication's own record is untouched: the pin still says what was sealed.
    assert tampered["content_digest"] == body["content_digest"]


def test_verification_is_opt_in_for_a_read(client):
    prepared = _prepare(client, _course(client), _deck())
    body = _publish(client, prepared["version_id"]).json()

    plain = client.get(f"/publications/{body['publication_id']}", headers=HEADERS).json()
    assert "integrity" not in plain


# -- tenant isolation -------------------------------------------------------------


def test_publication_is_tenant_isolated(client):
    course_id = _course(client)
    prepared = _prepare(client, course_id, _deck())
    body = _publish(client, prepared["version_id"]).json()
    client.app.state.repository.ensure_institution("university-002")
    other = {"X-Institution-Id": "university-002"}

    # Publishing another institution's version is denied like any other version read.
    assert _publish(client, prepared["version_id"]).status_code == 200  # own tenant
    other_publish = client.post(
        f"/course-versions/{prepared['version_id']}/publish", headers=other
    )
    assert other_publish.status_code == 403
    assert other_publish.json()["error"]["code"] == "TENANT_ACCESS_DENIED"

    # A publication of another institution is simply not found (no existence leak).
    assert (
        client.get(f"/publications/{body['publication_id']}", headers=other).status_code == 404
    )
    assert (
        client.get(
            f"/course-versions/{prepared['version_id']}/publication", headers=other
        ).status_code
        == 403
    )
    assert (
        client.get(f"/courses/{course_id}/publications", headers=other).status_code == 403
    )


# -- telemetry --------------------------------------------------------------------


def test_publication_telemetry_carries_identities_not_content(client):
    secret = "This sentence must never reach telemetry."
    prepared = _prepare(client, _course(client), _deck())
    service = client.app.state.publication_service
    capture = _CapturingLogger()
    service.telemetry._logger = capture

    assert _publish(client, prepared["version_id"]).status_code == 200

    events = [json.loads(record) for record in capture.records]
    names = {event["event"] for event in events}
    assert {"publication.stage", "publication.published"} <= names
    stages = [event["stage"] for event in events if event["event"] == "publication.stage"]
    assert stages == ["SEALING", "INDEXING", "COMMITTING"]

    published = next(event for event in events if event["event"] == "publication.published")
    assert published["created"] is True
    assert published["package_id"] == prepared["package_id"]
    assert published["content_package_version"] == prepared["content_package_version"]
    assert published["knowledge_index_version"] == "unindexed"

    for record in capture.records:
        assert secret not in record
        assert "Notes for" not in record, "slide notes are not the transition's business"

    metrics = service.telemetry.metrics
    assert metrics.stages_sealed == 1
    assert metrics.stages_indexed == 1
    assert metrics.stages_committed == 1
    assert metrics.publications_created == 1
    assert metrics.publications_replayed == 0
    assert metrics.publications_blocked == 0


def test_blocked_publication_telemetry_counts_the_stage(client):
    prepared = _prepare(client, _course(client), _deck())
    service = client.app.state.publication_service
    capture = _CapturingLogger()
    service.telemetry._logger = capture
    service._index = _FailingIndex()

    assert _publish(client, prepared["version_id"]).status_code == 409

    blocked = [
        json.loads(record)
        for record in capture.records
        if json.loads(record)["event"] == "publication.blocked"
    ]
    assert blocked and blocked[0]["stage"] == "INDEXING"
    assert blocked[0]["issue_code"] == "INDEX_FAILED"
    assert service.telemetry.metrics.publications_blocked == 1
    assert service.telemetry.metrics.index_failures == 1


def test_the_outbox_event_matches_its_contract(client):
    """The event is a client-facing contract, so check the payload against it.

    ``contracts/events/course-version-published.schema.json`` is evaluated with the
    subset of JSON-Schema it uses (``jsonschema`` is not installed and no
    production dependency may be added), the same approach as V0-006's package
    contract tests.
    """

    prepared = _prepare(client, _course(client), _deck())
    body = _publish(client, prepared["version_id"]).json()
    event = _repository(client).list_outbox("university-001", body["publication_id"])[0]

    schema = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "contracts"
            / "events"
            / "course-version-published.schema.json"
        ).read_text(encoding="utf-8")
    )
    payload = event.payload

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) <= set(payload), "every required field must be present"
    assert set(payload) <= set(schema["properties"]), "no undeclared field may leak into the event"
    assert payload["event_type"] == schema["properties"]["event_type"]["const"]
    assert payload["event_id"] == event.event_id
    assert isinstance(payload["course_version"], int)
    assert isinstance(payload["lesson_plan_versions"], list) and payload["lesson_plan_versions"]
    assert payload["teaching_graph_version"] is None


# -- the publication record is the commit point -----------------------------------


def test_publications_are_append_only_rows(client):
    """A publication is a fact: the row's identity and seal fields never change."""

    prepared = _prepare(client, _course(client), _deck())
    body = _publish(client, prepared["version_id"]).json()
    repository = _repository(client)
    row = repository.get_publication("university-001", body["publication_id"])
    assert row is not None and isinstance(row, Publication)

    # A replay must not rewrite it (not even the attribution).
    client.post(
        f"/course-versions/{prepared['version_id']}/publish",
        json={"published_by": "someone-else"},
        headers=HEADERS,
    )
    again = repository.get_publication("university-001", body["publication_id"])
    assert again == row
