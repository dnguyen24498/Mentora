"""V0-007 review actions: Approve/reject and draft lesson-order revisions.

Covers the acceptance criteria the backend owns:

* *teacher cannot approve blocking failures* — approving a non-publishable
  projection raises ``PUBLICATION_BLOCKED`` (and the blocked document normally
  never becomes a package at all; see ``test_publication_review_flow.py``);
* *edits create draft data, not mutate published package* — a draft appends a
  revision, inherits every structural field from the package, and the stored
  package files are byte-identical afterwards;
* *authorization* — a decision or a draft is confined to the artifact's tenant.

The projection itself (render/text/notes/fidelity/lesson order) is covered by
``test_publication_review.py``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.common.errors import NotFoundError, PublicationBlockedError
from app.compiler.package_builder import read_package
from app.compiler.package_builder.service import PackageBuildService
from app.compiler.render_service import RenderingService
from app.compiler.renderers.base import RenderConfig
from app.compiler.renderers.structural import StructuralSvgRenderer
from app.courses.models import CourseVersionStatus
from app.publication.draft import (
    ISSUE_DUPLICATE_SECTION,
    ISSUE_EMPTY_DRAFT,
    ISSUE_MISSING_SECTION,
    ISSUE_REVISION_CONFLICT,
    ISSUE_UNKNOWN_SECTION,
    DraftError,
    SectionInput,
    resolve_draft_sections,
)
from app.publication.review import ReviewSection, ReviewService
from app.publication.repository import ReviewRepository
from app.publication.workflow import STATUS_FOR_DECISION, ReviewWorkflow
from tests.fixtures import build_pptx, simple_pptx, text_shape

HEADERS = {"X-Institution-Id": "inst-1"}
ALT_HEADERS = {"X-Institution-Id": "inst-2"}


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _upload(client, data: bytes | None = None, filename: str = "deck.pptx") -> str:
    course_id = client.post("/courses", params={"title": "Intro"}, headers=HEADERS).json()[
        "course_id"
    ]
    response = client.post(
        f"/courses/{course_id}/materials",
        files={"file": (filename, data or simple_pptx(), "application/octet-stream")},
        headers=HEADERS,
    )
    assert response.status_code == 202, response.text
    return response.json()["artifact_id"]


def _built(client, slides: int = 3) -> str:
    """Upload ``slides`` slides, build the package, and return the artifact id."""

    deck = build_pptx(
        [[text_shape(2, f"S{index}", text=f"Slide {index}")] for index in range(1, slides + 1)],
        notes={index: f"Notes {index}" for index in range(1, slides + 1)},
    )
    artifact_id = _upload(client, deck)
    response = client.post(f"/artifacts/{artifact_id}/review-package", headers=HEADERS)
    assert response.status_code == 200, response.text
    return artifact_id


def _state(client, artifact_id: str) -> dict:
    response = client.get(
        f"/artifacts/{artifact_id}/review-package/review-state", headers=HEADERS
    )
    assert response.status_code == 200, response.text
    return response.json()


def _decide(client, artifact_id: str, decision: str, **body):
    payload = {"decision": decision, **body}
    return client.post(
        f"/artifacts/{artifact_id}/review-package/decision", json=payload, headers=HEADERS
    )


def _save_draft(client, artifact_id: str, sections: list[dict], edited_by: str | None = None):
    payload: dict = {"sections": sections}
    if edited_by is not None:
        payload["edited_by"] = edited_by
    return client.post(
        f"/artifacts/{artifact_id}/review-package/drafts", json=payload, headers=HEADERS
    )


def _section_ids(review: dict) -> list[str]:
    return [section["section_id"] for section in review["lesson_order"]]


# -- review state -----------------------------------------------------------------
def test_review_state_of_an_unreviewed_package(client):
    artifact_id = _built(client)
    state = _state(client, artifact_id)

    assert state["decision"] is None
    assert state["draft"] is None
    assert state["draft_count"] == 0
    assert state["stale"] is False
    assert state["publishable"] is True
    assert state["blocking_scene_orders"] == []
    assert state["version_status"] == CourseVersionStatus.DRAFT.value


def test_review_state_needs_a_built_package(client):
    artifact_id = _upload(client)
    for path in ("review-state", "drafts"):
        response = client.get(f"/artifacts/{artifact_id}/review-package/{path}", headers=HEADERS)
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "NOT_FOUND"


# -- approve ----------------------------------------------------------------------
def test_approve_records_the_decision_and_approves_the_version(client):
    artifact_id = _built(client)
    response = _decide(client, artifact_id, "APPROVE", reviewer="dr-nguyen")

    assert response.status_code == 200, response.text
    state = response.json()
    assert state["decision"]["decision"] == "APPROVE"
    assert state["decision"]["reviewer"] == "dr-nguyen"
    assert state["decision"]["reason"] is None
    assert state["decision"]["content_package_version"] == state["content_package_version"]
    assert state["version_status"] == CourseVersionStatus.APPROVED.value
    assert state["stale"] is False
    # The decision is durable state, readable again on the next request.
    assert _state(client, artifact_id)["decision"]["decision_id"] == state["decision"]["decision_id"]


def test_approve_is_idempotent(client):
    artifact_id = _built(client)
    first = _decide(client, artifact_id, "APPROVE", reviewer="dr-nguyen").json()
    second = _decide(client, artifact_id, "APPROVE", reviewer="dr-nguyen").json()

    assert first["decision"]["decision_id"] == second["decision"]["decision_id"]
    workflow = client.app.state.review_workflow
    assert len(workflow._repository.list_decisions("inst-1", artifact_id)) == 1
    assert workflow.telemetry.metrics.decisions_replayed == 1


def test_approve_defaults_the_reviewer_to_the_tenant(client):
    """Identity is not implemented yet, so attribution is explicitly tenant-level."""

    artifact_id = _built(client)
    state = _decide(client, artifact_id, "APPROVE").json()

    assert state["decision"]["reviewer"] == "inst-1"


# -- reject -----------------------------------------------------------------------
def test_reject_requires_a_reason(client):
    artifact_id = _built(client)
    response = _decide(client, artifact_id, "REJECT")

    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert _state(client, artifact_id)["decision"] is None

    blank = _decide(client, artifact_id, "REJECT", reason="   ")
    assert blank.status_code == 400


def test_reject_returns_the_version_to_review_required(client):
    artifact_id = _built(client)
    response = _decide(client, artifact_id, "REJECT", reason="Slide 2 needs a worked example")

    assert response.status_code == 200, response.text
    state = response.json()
    assert state["decision"]["decision"] == "REJECT"
    assert state["decision"]["reason"] == "Slide 2 needs a worked example"
    assert state["version_status"] == CourseVersionStatus.REVIEW_REQUIRED.value


def test_an_unknown_decision_is_rejected_before_the_service(client):
    artifact_id = _built(client)
    assert _decide(client, artifact_id, "MAYBE").status_code == 422


def test_a_new_decision_supersedes_the_previous_one(client):
    artifact_id = _built(client)
    _decide(client, artifact_id, "APPROVE")
    decided = _decide(client, artifact_id, "REJECT", reason="Second look found a gap").json()

    assert decided["decision"]["decision"] == "REJECT"
    assert decided["version_status"] == CourseVersionStatus.REVIEW_REQUIRED.value
    decisions = client.app.state.review_workflow._repository.list_decisions("inst-1", artifact_id)
    assert [d.decision for d in decisions] == ["REJECT", "APPROVE"], "history is append-only"


def test_a_stale_decision_is_reported_as_stale(client):
    """A decision only covers the content version it reviewed."""

    artifact_id = _built(client)
    repository = client.app.state.review_workflow._repository
    artifact = client.app.state.repository.get_artifact("inst-1", artifact_id)
    repository.record_decision(
        institution_id="inst-1",
        artifact_id=artifact_id,
        version_id=artifact.version_id,
        package_id="pkg-from-another-build",
        content_package_version="cpv-0000000000000000",
        decision="APPROVE",
        reason=None,
        reviewer="dr-nguyen",
    )

    state = _state(client, artifact_id)
    assert state["stale"] is True
    assert state["decision"]["decision"] == "APPROVE"


# -- blocking ---------------------------------------------------------------------
def test_approving_a_non_publishable_review_is_blocked(
    repository, object_store, extractor, render_config, upload_service, course
):
    """The service refuses to approve something that failed the fidelity gate."""

    artifact = upload_service.upload(
        institution_id="inst-1",
        course_id=course.course_id,
        filename="deck.pptx",
        data=simple_pptx(),
    ).artifact
    rendering = RenderingService(
        repository,
        object_store,
        extractor,
        StructuralSvgRenderer(object_store, render_config),
        config=render_config,
    )
    review = ReviewService(
        repository, object_store, PackageBuildService(repository, object_store, rendering)
    )
    workflow = ReviewWorkflow(review, ReviewRepository(repository._conn), repository)

    # No package was built for this artifact, so there is nothing to approve.
    with pytest.raises(NotFoundError):
        workflow.decide("inst-1", artifact.artifact_id, decision="APPROVE")

    # Simulate a non-publishable projection reaching the decision path (the
    # fidelity gate normally stops it from becoming a package at all).
    class BlockedReview:
        publishable = False
        state = "BLOCKED"
        package_id = "pkg-blocked"
        content_package_version = "cpv-blocked"
        lesson_order: tuple = ()

    review.load_review = lambda *_args, **_kwargs: BlockedReview()  # type: ignore[method-assign]
    with pytest.raises(PublicationBlockedError):
        workflow.decide("inst-1", artifact.artifact_id, decision="APPROVE")
    assert workflow.telemetry.metrics.approvals_blocked == 1
    assert repository.get_version("inst-1", artifact.version_id).status == "DRAFT"


def test_status_for_each_decision_is_a_review_state_only():
    assert STATUS_FOR_DECISION["APPROVE"] is CourseVersionStatus.APPROVED
    assert STATUS_FOR_DECISION["REJECT"] is CourseVersionStatus.REVIEW_REQUIRED
    # Publication states are V0-008 and must not be reachable from a review.
    assert CourseVersionStatus.PUBLISHED not in STATUS_FOR_DECISION.values()


# -- drafts -----------------------------------------------------------------------
def test_save_draft_appends_a_revision_and_leaves_the_package_untouched(client):
    artifact_id = _built(client)
    built = client.get(f"/artifacts/{artifact_id}/review-package", headers=HEADERS).json()
    store = client.app.state.review_service._object_store
    before = read_package(store, built["prefix"])

    order = _section_ids(built)
    response = _save_draft(
        client,
        artifact_id,
        [{"section_id": order[1]}, {"section_id": order[0]}, {"section_id": order[2]}],
        edited_by="dr-nguyen",
    )

    assert response.status_code == 200, response.text
    draft = response.json()
    assert draft["revision"] == 1
    assert draft["edited_by"] == "dr-nguyen"
    assert draft["package_id"] == built["package_id"]
    assert draft["content_package_version"] == built["content_package_version"]
    assert draft["lesson_plan_version"] == built["lesson_plan_version"]
    assert [section["section_id"] for section in draft["sections"]] == [
        order[1],
        order[0],
        order[2],
    ]
    assert [section["order"] for section in draft["sections"]] == [0, 1, 2]

    # The package is byte-identical: an edit is data *about* the content.
    after = read_package(store, built["prefix"])
    assert [(f.path, f.sha256, f.data) for f in after.package.files] == [
        (f.path, f.sha256, f.data) for f in before.package.files
    ]
    # ...and the review projection still shows the package's own lesson order.
    assert _section_ids(
        client.get(f"/artifacts/{artifact_id}/review-package", headers=HEADERS).json()
    ) == order


def test_draft_inherits_structure_from_the_package(client):
    artifact_id = _built(client)
    built = client.get(f"/artifacts/{artifact_id}/review-package", headers=HEADERS).json()
    source = {section["section_id"]: section for section in built["lesson_order"]}
    reversed_order = list(reversed(_section_ids(built)))

    draft = _save_draft(
        client, artifact_id, [{"section_id": sid} for sid in reversed_order]
    ).json()

    for section in draft["sections"]:
        original = source[section["section_id"]]
        assert section["scene_id"] == original["scene_id"]
        assert section["scene_step_id"] == original["scene_step_id"]
        assert section["safe_markers"] == original["safe_markers"]
        assert section["type"] == original["type"]
        # An omitted script inherits the package's script (notes -> lesson script).
        assert section["script"] == original["script"]


def test_draft_edits_a_script_and_normalises_it(client):
    artifact_id = _built(client)
    order = _section_ids(
        client.get(f"/artifacts/{artifact_id}/review-package", headers=HEADERS).json()
    )

    draft = _save_draft(
        client,
        artifact_id,
        [
            {"section_id": order[0], "script": "  Start with the hook.  "},
            {"section_id": order[1], "script": ""},
            {"section_id": order[2]},
        ],
    ).json()

    scripts = [section["script"] for section in draft["sections"]]
    assert scripts[0] == "Start with the hook."
    assert scripts[1] is None, "an all-whitespace script means no script"
    assert scripts[2] is not None, "omitted script inherits the package's"


def test_draft_revisions_are_appended_and_listed_newest_first(client):
    artifact_id = _built(client)
    order = _section_ids(
        client.get(f"/artifacts/{artifact_id}/review-package", headers=HEADERS).json()
    )

    first = _save_draft(client, artifact_id, [{"section_id": sid} for sid in order]).json()
    second = _save_draft(
        client, artifact_id, [{"section_id": sid} for sid in reversed(order)]
    ).json()

    assert first["revision"] == 1
    assert second["revision"] == 2
    assert second["draft_id"] != first["draft_id"]

    listed = client.get(f"/artifacts/{artifact_id}/review-package/drafts", headers=HEADERS).json()
    assert [draft["revision"] for draft in listed["revisions"]] == [2, 1]
    assert listed["artifact_id"] == artifact_id
    # The state endpoint reports the newest revision and how many exist.
    state = _state(client, artifact_id)
    assert state["draft"]["revision"] == 2
    assert state["draft_count"] == 2


def test_draft_must_be_a_rearrangement_of_the_lesson_order(client):
    artifact_id = _built(client)
    order = _section_ids(
        client.get(f"/artifacts/{artifact_id}/review-package", headers=HEADERS).json()
    )

    cases = [
        ([], ISSUE_EMPTY_DRAFT),
        ([{"section_id": "ppt/slides/slide99.xml"}], ISSUE_UNKNOWN_SECTION),
        ([{"section_id": order[0]}, {"section_id": order[0]}], ISSUE_DUPLICATE_SECTION),
        ([{"section_id": order[0]}], ISSUE_MISSING_SECTION),
    ]
    for sections, issue in cases:
        response = _save_draft(client, artifact_id, sections)
        assert response.status_code == 400, (issue, response.text)
        assert response.json()["error"]["code"] == "INVALID_REQUEST"
        assert response.json()["error"]["issue_code"] == issue

    # Nothing was stored for a refused edit.
    assert _state(client, artifact_id)["draft_count"] == 0


def test_draft_requires_a_section_id(client):
    artifact_id = _built(client)
    # A blank id is a request-shape error and never reaches the workflow.
    assert _save_draft(client, artifact_id, [{"section_id": ""}]).status_code == 422


def test_a_conflicting_draft_revision_fails_loudly(client):
    """The append-only backstop: never silently branch a revision history."""

    artifact_id = _built(client)
    repository: ReviewRepository = client.app.state.review_workflow._repository
    order = _section_ids(
        client.get(f"/artifacts/{artifact_id}/review-package", headers=HEADERS).json()
    )
    artifact = client.app.state.repository.get_artifact("inst-1", artifact_id)
    built = client.get(f"/artifacts/{artifact_id}/review-package", headers=HEADERS).json()

    kwargs = dict(
        institution_id="inst-1",
        artifact_id=artifact_id,
        version_id=artifact.version_id,
        package_id=built["package_id"],
        content_package_version=built["content_package_version"],
        lesson_plan_version=built["lesson_plan_version"],
        sections=(),
        edited_by="dr-nguyen",
    )
    repository._next_revision = lambda *_args, **_kwargs: 1  # type: ignore[method-assign]
    repository.create_draft(**kwargs)  # takes revision 1
    with pytest.raises(DraftError) as conflict:
        repository.create_draft(**kwargs)  # the loser of the race
    assert conflict.value.issue_code == ISSUE_REVISION_CONFLICT
    assert conflict.value.http_status == 409
    assert order  # sanity: the fixture built a real lesson order


# -- pure draft resolution --------------------------------------------------------
def _section(section_id: str, script: str | None = None, order: int = 0) -> ReviewSection:
    return ReviewSection(
        order=order,
        section_id=section_id,
        type="EXPLANATION",
        scene_id=f"scene-{section_id}",
        scene_step_id=f"scene-{section_id}#step-0",
        safe_markers=(f"scene-{section_id}#step-0",),
        script=script,
    )


def test_resolve_draft_sections_reports_the_diff():
    lesson_order = (_section("a", order=0), _section("b", script="keep", order=1))

    resolved, diff = resolve_draft_sections(
        lesson_order, [SectionInput("b"), SectionInput("a", script="new")]
    )

    assert [s.section_id for s in resolved] == ["b", "a"]
    assert [s.order for s in resolved] == [0, 1]
    assert resolved[0].script == "keep", "omitted script inherits"
    assert resolved[1].script == "new"
    assert diff.reordered == 2
    assert diff.scripts_edited == 1
    assert diff.sections == 2
    assert not diff.is_identical


def test_resolve_draft_sections_is_identical_when_nothing_changed():
    lesson_order = (_section("a", script="one"), _section("b", script="two", order=1))

    resolved, diff = resolve_draft_sections(
        lesson_order, [SectionInput("a"), SectionInput("b")]
    )

    assert [s.script for s in resolved] == ["one", "two"]
    assert diff.is_identical


def test_resolve_draft_sections_rejects_an_empty_order():
    with pytest.raises(DraftError) as empty:
        resolve_draft_sections((_section("a"),), [])
    assert empty.value.issue_code == ISSUE_EMPTY_DRAFT


# -- authorization ----------------------------------------------------------------
def test_decisions_and_drafts_are_tenant_scoped(client, repository):
    artifact_id = _built(client)
    order = _section_ids(
        client.get(f"/artifacts/{artifact_id}/review-package", headers=HEADERS).json()
    )
    repository.ensure_institution("inst-2")

    assert (
        client.post(
            f"/artifacts/{artifact_id}/review-package/decision",
            json={"decision": "APPROVE"},
            headers=ALT_HEADERS,
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/artifacts/{artifact_id}/review-package/review-state", headers=ALT_HEADERS
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/artifacts/{artifact_id}/review-package/drafts",
            json={"sections": [{"section_id": sid} for sid in order]},
            headers=ALT_HEADERS,
        ).status_code
        == 403
    )
    assert (
        client.get(f"/artifacts/{artifact_id}/review-package/drafts", headers=ALT_HEADERS).status_code
        == 403
    )
    # Nothing was written for the foreign tenant.
    assert _state(client, artifact_id)["decision"] is None
    assert _state(client, artifact_id)["draft_count"] == 0


def test_review_actions_require_a_principal(client):
    """A review action is a teacher capability; without a principal it is a 401."""

    artifact_id = _built(client)
    assert (
        client.post(
            f"/artifacts/{artifact_id}/review-package/decision", json={"decision": "APPROVE"}
        ).status_code
        == 401
    )
    assert client.get(f"/artifacts/{artifact_id}/review-package/review-state").status_code == 401
    assert (
        client.post(
            f"/artifacts/{artifact_id}/review-package/drafts", json={"sections": []}
        ).status_code
        == 401
    )


def test_review_action_on_an_unknown_artifact_is_404(client):
    unknown = "00000000-0000-0000-0000-000000000000"
    assert (
        client.post(
            f"/artifacts/{unknown}/review-package/decision",
            json={"decision": "APPROVE"},
            headers=HEADERS,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/artifacts/{unknown}/review-package/drafts",
            json={"sections": [{"section_id": "x"}]},
            headers=HEADERS,
        ).status_code
        == 404
    )
