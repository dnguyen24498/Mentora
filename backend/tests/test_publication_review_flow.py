"""V0-007 end-to-end review flow, including the blocking-warning path.

This is the API-level E2E for the task's "blocking-warning E2E" requirement: it
drives the exact browser flow (upload -> build the package -> review -> edit the
lesson order -> decide) against the real FastAPI app, the real SQLite store and
the real local object store, and it asserts the two acceptance criteria that
matter end to end:

* a document whose render failed can never be offered for review, so a teacher
  cannot approve it;
* an edit is draft data — the published-package bytes do not change.

``tests/e2e/`` does not exist in this repo; ``backend/tests/`` is its test root
(same nominal-path mapping as V0-004…V0-006).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.compiler.package_builder import read_package
from app.compiler.renderers.base import RenderConfig
from app.compiler.renderers.testing import FakeRenderer
from app.courses.models import CourseVersionStatus
from tests.fixtures import REL_CHART, build_pptx, chart_shape, simple_pptx, text_shape

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


@pytest.fixture
def blocked_client(settings):
    """An app whose renderer fails the first slide (the fidelity gate blocks it)."""

    def factory(object_store, config: RenderConfig):
        return FakeRenderer(object_store=object_store, config=config, fail_orders=(0,))

    with TestClient(create_app(settings, renderer_factory=factory)) as test_client:
        yield test_client


@pytest.fixture
def degraded_client(settings):
    """An app whose renderer cannot represent every object kind, so a scene degrades.

    V0-019 v5 makes the default renderer draw what it cannot reproduce in the
    platform look, so a *degradation* has to be configured explicitly to exercise
    the human-review path.
    """

    def factory(object_store, config: RenderConfig):
        return FakeRenderer(object_store=object_store, config=config, supported_kinds=("text",))

    with TestClient(create_app(settings, renderer_factory=factory)) as test_client:
        yield test_client


def _deck(slides: int = 3) -> bytes:
    return build_pptx(
        [[text_shape(2, f"S{index}", text=f"Slide {index}")] for index in range(1, slides + 1)],
        notes={index: f"Notes for slide {index}" for index in range(1, slides + 1)},
    )


def _upload(client, data: bytes, filename: str = "lecture.pptx") -> str:
    course_id = client.post("/courses", params={"title": "Neural Nets"}, headers=HEADERS).json()[
        "course_id"
    ]
    response = client.post(
        f"/courses/{course_id}/materials",
        files={"file": (filename, data, "application/octet-stream")},
        headers=HEADERS,
    )
    assert response.status_code == 202, response.text
    return response.json()["artifact_id"]


class _CapturingLogger:
    """Collects emitted telemetry records so redaction can be asserted."""

    def __init__(self) -> None:
        self.records: list[str] = []

    def info(self, message: str, *args) -> None:  # noqa: ANN002 - mirrors logging.Logger.info
        self.records.append(message % args if args else message)


def test_teacher_reviews_edits_and_approves_a_deck(client):
    artifact_id = _upload(client, _deck())

    # 1. Build the package (the expensive path) and read the review projection.
    built = client.post(f"/artifacts/{artifact_id}/review-package", headers=HEADERS).json()
    assert built["state"] == "READY"
    assert built["publishable"] is True
    order = [section["section_id"] for section in built["lesson_order"]]
    assert len(order) == 3

    # 2. The teacher starts from the package, with nothing decided yet.
    state = client.get(
        f"/artifacts/{artifact_id}/review-package/review-state", headers=HEADERS
    ).json()
    assert state["decision"] is None
    assert state["draft"] is None
    assert state["version_status"] == CourseVersionStatus.DRAFT.value

    # 3. They reorder two sections and rewrite one script (a draft revision).
    draft = client.post(
        f"/artifacts/{artifact_id}/review-package/drafts",
        json={
            "sections": [
                {"section_id": order[1]},
                {"section_id": order[0], "script": "Open with the intuition first."},
                {"section_id": order[2], "script": ""},
            ],
            "edited_by": "teacher@university-001",
        },
        headers=HEADERS,
    ).json()
    assert draft["revision"] == 1
    assert [section["section_id"] for section in draft["sections"]] == [
        order[1],
        order[0],
        order[2],
    ]

    # 4. The package under review is untouched by that edit.
    store = client.app.state.review_service._object_store
    loaded = read_package(store, built["prefix"])
    assert loaded is not None
    assert loaded.lesson_plan()["sections"][0]["section_id"] == order[0]
    assert "publish_state" not in loaded.manifest

    # 5. The teacher approves what they reviewed.
    decided = client.post(
        f"/artifacts/{artifact_id}/review-package/decision",
        json={"decision": "APPROVE", "reviewer": "teacher@university-001"},
        headers=HEADERS,
    )
    assert decided.status_code == 200, decided.text
    state = decided.json()
    assert state["decision"]["decision"] == "APPROVE"
    assert state["version_status"] == CourseVersionStatus.APPROVED.value
    assert state["stale"] is False
    assert state["draft"]["revision"] == 1, "the draft survives the decision"

    # 6. Approval is a *review* state: publication (SEALING -> … -> PUBLISHED) is V0-008.
    version = client.app.state.repository.get_version(
        "university-001", state["version_id"]
    )
    assert version.status == CourseVersionStatus.APPROVED.value
    assert version.status != CourseVersionStatus.PUBLISHED.value

    # 7. Re-reading the package is still cheap and still shows the package's order.
    reread = client.get(f"/artifacts/{artifact_id}/review-package", headers=HEADERS).json()
    assert [section["section_id"] for section in reread["lesson_order"]] == order


def test_a_blocking_render_failure_never_becomes_approvable(blocked_client):
    artifact_id = _upload(blocked_client, _deck())

    # The fidelity gate refuses to build a package at all.
    build = blocked_client.post(f"/artifacts/{artifact_id}/review-package", headers=HEADERS)
    assert build.status_code == 409, build.text
    assert build.json()["error"]["code"] == "PUBLICATION_BLOCKED"

    # So there is nothing to read, decide on, or edit — the teacher cannot approve it.
    for path in ("review-package", "review-package/review-state", "review-package/drafts"):
        assert blocked_client.get(f"/artifacts/{artifact_id}/{path}", headers=HEADERS).status_code == 404
    assert (
        blocked_client.post(
            f"/artifacts/{artifact_id}/review-package/decision",
            json={"decision": "APPROVE"},
            headers=HEADERS,
        ).status_code
        == 404
    )

    # Nothing was written: no package bytes and no review rows.
    assert not (blocked_client.app.state.settings.object_root / "packages").exists()
    repository = blocked_client.app.state.review_workflow._repository
    assert repository.list_decisions("university-001", artifact_id) == []
    assert repository.draft_count("university-001", artifact_id) == 0


def test_a_degraded_render_is_reviewable_and_the_decision_is_auditable(degraded_client):
    """DEGRADED_RENDERED is human-required, not blocked (DEC-CONTENT-006/008).

    V0-019 v5: the default renderer draws an object it cannot reproduce in the
    platform look instead of degrading, so this app is configured with a renderer
    that cannot represent a chart at all.
    """

    client = degraded_client
    deck = build_pptx(
        [[chart_shape(6, "Scores")]],
        extra_slide_rels={1: [("rIdChart", REL_CHART, "../charts/chart1.xml")]},
        extra_entries={"ppt/charts/chart1.xml": b"<c:chartSpace/>"},
    )
    artifact_id = _upload(client, deck, "chart.pptx")
    built = client.post(f"/artifacts/{artifact_id}/review-package", headers=HEADERS).json()

    assert built["state"] == "REVIEW_REQUIRED"
    assert built["requires_review"] is True
    assert built["publishable"] is True
    assert built["scenes"][0]["fidelity"] == "DEGRADED_RENDERED"

    decision = client.post(
        f"/artifacts/{artifact_id}/review-package/decision",
        json={"decision": "APPROVE", "reason": "Chart image to follow", "reviewer": "t"},
        headers=HEADERS,
    )
    assert decision.status_code == 200, decision.text
    assert decision.json()["decision"]["reason"] == "Chart image to follow"


def test_review_telemetry_redacts_authored_text(client):
    """A review reason and an edited script are text: record their shape, not them."""

    secret_reason = "Do not leak this sentence about a student."
    secret_script = "Also do not leak this script line."
    artifact_id = _upload(client, _deck(slides=2))
    built = client.post(f"/artifacts/{artifact_id}/review-package", headers=HEADERS).json()
    order = [section["section_id"] for section in built["lesson_order"]]

    workflow = client.app.state.review_workflow
    capture = _CapturingLogger()
    workflow.telemetry._logger = capture

    client.post(
        f"/artifacts/{artifact_id}/review-package/drafts",
        json={"sections": [{"section_id": sid} for sid in order]},
        headers=HEADERS,
    )
    client.post(
        f"/artifacts/{artifact_id}/review-package/drafts",
        json={
            "sections": [
                {"section_id": order[0], "script": secret_script},
                {"section_id": order[1]},
            ]
        },
        headers=HEADERS,
    )
    client.post(
        f"/artifacts/{artifact_id}/review-package/decision",
        json={"decision": "REJECT", "reason": secret_reason, "reviewer": "t"},
        headers=HEADERS,
    )

    assert capture.records, "the review write path must emit telemetry"
    events = {json.loads(record)["event"] for record in capture.records}
    assert {"publication.review.draft_saved", "publication.review.decided"} <= events
    for record in capture.records:
        assert secret_reason not in record
        assert secret_script not in record
    decided = json.loads(
        next(r for r in capture.records if "review.decided" in r)
    )
    assert decided["reason_present"] is True
    assert decided["reason_chars"] == len(secret_reason)
    assert decided["decision"] == "REJECT"
    saved = json.loads(
        [record for record in capture.records if "draft_saved" in record][-1]
    )
    assert saved["scripts_edited"] == 1
    assert saved["sections"] == 2
    assert saved["revision"] == 2


def test_the_whole_flow_is_tenant_isolated(client):
    artifact_id = _upload(client, simple_pptx())
    client.post(f"/artifacts/{artifact_id}/review-package", headers=HEADERS)
    client.app.state.repository.ensure_institution("university-002")

    other = {"X-Institution-Id": "university-002"}
    assert (
        client.get(
            f"/artifacts/{artifact_id}/review-package/review-state", headers=other
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/artifacts/{artifact_id}/review-package/decision",
            json={"decision": "APPROVE"},
            headers=other,
        ).status_code
        == 403
    )
