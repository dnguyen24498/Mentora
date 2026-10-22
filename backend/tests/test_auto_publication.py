"""The Library upload shortcut: auto-publish only what the policy allows.

``POST /artifacts/{artifactId}/auto-publish`` composes the V0-007 review and the
V0-008 publication for a freshly uploaded deck. These tests pin the properties
that make the shortcut safe:

* an auto-allowed (``READY``) package is approved as the uploading teacher and
  published atomically, and a replay returns the same publication;
* a human-required (``REVIEW_REQUIRED``) package is stored and left unpublished
  with no decision written — automation never approves it;
* a blocking render failure is refused before anything is decided or published;
* the composed action needs all three capabilities, so an administrator cannot
  use it, and the tenant boundary still holds.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.compiler.renderers.base import RenderConfig
from app.compiler.renderers.testing import FakeRenderer
from app.courses.models import CourseVersionStatus
from tests.fixtures import REL_CHART, build_pptx, chart_shape, text_shape

HEADERS = {"X-Institution-Id": "university-001"}
OTHER_TENANT = {"X-Institution-Id": "university-002"}
PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def settings(dev_settings):
    """The browser suites drive the pre-identity API as a teacher (V0-023)."""

    return dev_settings


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def blocked_client(settings):
    """A renderer whose first slide fails, so the fidelity gate refuses to build."""

    def factory(object_store, config: RenderConfig):
        return FakeRenderer(object_store=object_store, config=config, fail_orders=(0,))

    with TestClient(create_app(settings, renderer_factory=factory)) as test_client:
        yield test_client


@pytest.fixture
def degraded_client(settings):
    """A renderer that cannot represent a chart, so the scene is human-required.

    V0-019 v5's default renderer draws unsupported components in the platform
    look, so the human-required path has to be configured explicitly.
    """

    def factory(object_store, config: RenderConfig):
        return FakeRenderer(object_store=object_store, config=config, supported_kinds=("text",))

    with TestClient(create_app(settings, renderer_factory=factory)) as test_client:
        yield test_client


def _course(client, headers=HEADERS, title: str = "Neural Nets") -> str:
    response = client.post("/courses", params={"title": title}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["course_id"]


def _upload(client, course_id: str, data: bytes, headers=HEADERS, filename: str = "lecture.pptx") -> str:
    response = client.post(
        f"/courses/{course_id}/materials",
        files={"file": (filename, data, "application/octet-stream")},
        headers=headers,
    )
    assert response.status_code == 202, response.text
    return response.json()["artifact_id"]


def _auto(client, artifact_id: str, headers=HEADERS):
    return client.post(f"/artifacts/{artifact_id}/auto-publish", headers=headers)


def _deck(slides: int = 3) -> bytes:
    return build_pptx(
        [[text_shape(2, f"S{index}", text=f"Slide {index}")] for index in range(1, slides + 1)],
        notes={index: f"Notes for slide {index}" for index in range(1, slides + 1)},
    )


def _chart_deck() -> bytes:
    return build_pptx(
        [[chart_shape(6, "Scores")]],
        extra_slide_rels={1: [("rIdChart", REL_CHART, "../charts/chart1.xml")]},
        extra_entries={"ppt/charts/chart1.xml": b"<c:chartSpace/>"},
    )


def _sign_in(client, email: str, password: str = PASSWORD, institution: str = "university-001"):
    response = client.post(
        "/auth/login",
        json={"institution_id": institution, "email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _admin_headers(client) -> dict:
    boot = client.post(
        "/auth/bootstrap-admin",
        json={"institution_id": "university-001", "email": "root@uni.test", "password": PASSWORD},
    )
    assert boot.status_code == 201, boot.text
    return _sign_in(client, "root@uni.test")


def _teacher_headers(client) -> dict:
    admin = _admin_headers(client)
    created = client.post(
        "/accounts",
        json={"email": "teacher@uni.test", "role": "teacher", "password": PASSWORD},
        headers=admin,
    )
    assert created.status_code == 201, created.text
    return _sign_in(client, "teacher@uni.test")


# -- auto-allowed ------------------------------------------------------------------


def test_an_uploaded_deck_is_published_as_the_teacher(client):
    artifact_id = _upload(client, _course(client), _deck())

    response = _auto(client, artifact_id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["published"] is True
    assert body["created"] is True
    assert body["state"] == "READY"
    assert body["requires_review"] is False
    assert body["publication"]["state"] == "PUBLISHED"
    assert body["publication"]["published_by"] == "university-001"
    assert body["publication"]["artifact_id"] == artifact_id
    assert body["publication"]["content_package_version"] == body["content_package_version"]

    # The approval is real and auditable, not only a publication row.
    state = client.get(
        f"/artifacts/{artifact_id}/review-package/review-state", headers=HEADERS
    ).json()
    assert state["decision"]["decision"] == "APPROVE"
    assert state["decision"]["reviewer"] == "university-001"
    assert "Auto-approved on upload" in state["decision"]["reason"]
    assert state["version_status"] == CourseVersionStatus.PUBLISHED.value

    version = client.app.state.repository.get_version("university-001", body["version_id"])
    assert version.status == CourseVersionStatus.PUBLISHED.value


def test_a_replayed_upload_returns_the_same_publication_and_one_decision(client):
    artifact_id = _upload(client, _course(client), _deck())

    first = _auto(client, artifact_id).json()
    replay = _auto(client, artifact_id)

    assert replay.status_code == 200, replay.text
    assert replay.json()["created"] is False
    assert replay.json()["publication"]["publication_id"] == first["publication"]["publication_id"]

    repository = client.app.state.review_workflow._repository
    assert len(repository.list_decisions("university-001", artifact_id)) == 1


# -- policy boundaries -------------------------------------------------------------


def test_a_human_required_package_is_not_auto_approved_or_published(degraded_client):
    client = degraded_client
    course_id = _course(client)
    artifact_id = _upload(client, course_id, _chart_deck(), filename="chart.pptx")

    response = _auto(client, artifact_id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["published"] is False
    assert body["created"] is False
    assert body["state"] == "REVIEW_REQUIRED"
    assert body["requires_review"] is True
    assert body["publication"] is None
    assert body["review_state"]["decision"] is None
    assert body["review_state"]["version_status"] == CourseVersionStatus.DRAFT.value

    # Nothing was approved and nothing was published.
    repository = client.app.state.review_workflow._repository
    assert repository.list_decisions("university-001", artifact_id) == []
    assert (
        client.app.state.publication_service._publications.list_publications(
            "university-001", course_id
        )
        == []
    )


def test_a_blocking_failure_is_refused_before_any_decision(blocked_client):
    client = blocked_client
    artifact_id = _upload(client, _course(client), _deck())

    response = _auto(client, artifact_id)

    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "PUBLICATION_BLOCKED"
    repository = client.app.state.review_workflow._repository
    assert repository.list_decisions("university-001", artifact_id) == []
    assert repository.draft_count("university-001", artifact_id) == 0
    assert not (client.app.state.settings.object_root / "packages").exists()


# -- who may compose the action ----------------------------------------------------


def test_the_approval_and_publication_belong_to_the_signed_in_teacher(client):
    teacher = _teacher_headers(client)
    course_id = _course(client, teacher)
    artifact_id = _upload(client, course_id, _deck(), headers=teacher)

    response = _auto(client, artifact_id, headers=teacher)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["publication"]["published_by"] == "teacher@uni.test"
    assert body["review_state"]["decision"]["reviewer"] == "teacher@uni.test"


def test_an_administrator_cannot_auto_publish(client):
    teacher = _teacher_headers(client)
    course_id = _course(client, teacher)
    artifact_id = _upload(client, course_id, _deck(), headers=teacher)
    admin = _sign_in(client, "root@uni.test")

    response = _auto(client, artifact_id, headers=admin)

    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "INSUFFICIENT_SCOPE"
    assert response.json()["error"]["issue_code"] == "SCOPE_REQUIRED"
    assert client.app.state.repository.get_artifact(
        "university-001", artifact_id
    ).artifact_id == artifact_id


def test_auto_publish_is_tenant_scoped(client):
    artifact_id = _upload(client, _course(client), _deck())

    response = _auto(client, artifact_id, headers=OTHER_TENANT)

    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "TENANT_ACCESS_DENIED"
