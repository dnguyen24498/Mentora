"""V0-007 teacher review preview: read-only review of a built package.

Covers the acceptance criteria that can be verified without a browser harness:
the review view is projected from the package, it is tenant-scoped, a blocked
document is never offered for review, and nothing here mutates the package.

The remaining V0-007 criteria (UI component tests, blocking-warning E2E, a full
keyboard/screen-reader audit) need a browser test harness; adding one is a new
dependency and was explicitly out of scope for this slice.
"""

from __future__ import annotations


import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.common.errors import PublicationBlockedError
from app.compiler.package_builder import read_package
from app.compiler.package_builder.service import PackageBuildService
from app.compiler.renderers.base import RenderConfig
from app.compiler.renderers.testing import FakeRenderer
from app.publication.review import (
    RENDER_PLACEHOLDER_NOTICE,
    STATE_READY,
    ReviewService,
)
from tests.fixtures import (
    REL_CHART,
    build_pptx,
    chart_shape,
    simple_pptx,
    text_shape,
)

HEADERS = {"X-Institution-Id": "inst-1"}
ALT_HEADERS = {"X-Institution-Id": "inst-2"}


def _chart_deck() -> bytes:
    """A deck whose only object is one the themed renderer cannot redraw."""

    return build_pptx(
        [[chart_shape(6, "Scores")]],
        extra_slide_rels={1: [("rIdChart", REL_CHART, "../charts/chart1.xml")]},
        extra_entries={"ppt/charts/chart1.xml": b"<c:chartSpace/>"},
    )


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


def _review(client, artifact_id: str) -> dict:
    response = client.post(f"/artifacts/{artifact_id}/review-package", headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


# -- the review view ---------------------------------------------------------------
def test_build_review_package_returns_the_projected_view(client):
    artifact_id = _upload(client)
    body = _review(client, artifact_id)

    assert body["artifact_id"] == artifact_id
    assert body["state"] == STATE_READY
    assert body["publishable"] is True
    assert body["requires_review"] is False
    assert body["scene_count"] == 1
    assert body["file_count"] == 3  # 1 scene + lesson plan + 1 asset
    assert body["package_id"] == body["prefix"].rsplit("/", 1)[-1]
    assert body["package_id"].startswith("pkg-")


def test_review_scene_carries_render_text_notes_and_fidelity(client):
    artifact_id = _upload(
        client, build_pptx([[text_shape(2, "T", text="Hello world")]], notes={1: "Say hi."})
    )
    scene = _review(client, artifact_id)["scenes"][0]

    assert scene["order"] == 0
    assert scene["scene_id"] == "ppt/slides/slide1.xml"
    assert scene["fidelity"] == "STRUCTURAL_RENDERED"
    assert scene["render_status"] == "RENDERED"
    assert scene["text"] == ["Hello world"]
    assert scene["notes"] == "Say hi."
    assert scene["warnings"] == []
    assert scene["missing_fonts"] == []
    assert scene["object_count"] == 1
    assert scene["step_count"] == 1
    assert scene["renderer"]["name"] == "local-structural-svg"
    assert scene["render_url"] == f"/artifacts/{artifact_id}/review-package/renders/0"


def test_review_lesson_order_matches_the_scenes(client):
    artifact_id = _upload(
        client,
        build_pptx(
            [[text_shape(2, "A", text="one")], [text_shape(2, "B", text="two")]],
            notes={2: "Explain two."},
        ),
    )
    body = _review(client, artifact_id)

    assert [scene["order"] for scene in body["scenes"]] == [0, 1]
    assert [section["order"] for section in body["lesson_order"]] == [0, 1]
    assert [section["scene_id"] for section in body["lesson_order"]] == [
        "ppt/slides/slide1.xml",
        "ppt/slides/slide2.xml",
    ]
    steps = {scene["scene_id"]: f"{scene['scene_id']}#step-0" for scene in body["scenes"]}
    for section in body["lesson_order"]:
        assert section["safe_markers"] == [steps[section["scene_id"]]]
        assert section["scene_step_id"] == steps[section["scene_id"]]
    assert body["lesson_order"][1]["script"] == "Explain two."
    assert body["lesson_order"][0]["script"] is None


def test_review_reports_no_teaching_graph_and_no_index(client):
    body = _review(client, _upload(client))

    assert body["teaching_graph_version"] is None
    assert body["knowledge_index_version"] == "unindexed"
    assert body["lesson_plan_version"].startswith("lp-")
    assert body["content_package_version"].startswith("cpv-")


def test_review_declares_how_the_slides_were_rendered(client):
    body = _review(client, _upload(client))

    # DEC-TECH-005 is OPEN: the UI must never imply a native render.
    assert body["placeholder_notice"] == RENDER_PLACEHOLDER_NOTICE
    assert "DEC-TECH-005" in body["placeholder_notice"]
    assert "keeps the deck's own layout" in body["placeholder_notice"]
    assert body["renderer"]["engine"] == "stdlib-svg"


def test_review_is_deterministic_apart_from_the_build_timestamp(client):
    artifact_id = _upload(client)
    first = _review(client, artifact_id)
    second = _review(client, artifact_id)

    first.pop("created_at")
    second.pop("created_at")
    assert first == second


# -- unavailable components are drawn in place, not blocked -------------------------
def test_an_unavailable_font_is_substituted_not_degraded(client):
    """V0-019 v5: the run keeps its box and is drawn in the platform's type stack."""

    artifact_id = _upload(
        client,
        build_pptx([[text_shape(2, "T", text="hi", font="Be Vietnam Pro")]]),
        "brand.pptx",
    )
    body = _review(client, artifact_id)

    assert body["state"] == STATE_READY
    assert body["requires_review"] is False
    scene = body["scenes"][0]
    assert scene["fidelity"] == "STRUCTURAL_RENDERED"
    assert scene["missing_fonts"] == ["Be Vietnam Pro"]
    assert "FONT_SUBSTITUTED:Be Vietnam Pro" in scene["warnings"]


def test_an_unmappable_object_is_drawn_in_the_platform_look(client):
    """A chart cannot be reproduced, so the app's own panel draws it, in place."""

    artifact_id = _upload(client, _chart_deck(), "chart.pptx")
    body = _review(client, artifact_id)

    assert body["state"] == STATE_READY
    assert body["requires_review"] is False
    assert body["publishable"] is True
    scene = body["scenes"][0]
    assert scene["requires_review"] is False
    assert scene["fidelity"] == "STRUCTURAL_RENDERED"
    assert scene["missing_fonts"] == []
    # The object is still named, so the substitution is never silent.
    assert "UNSUPPORTED_OBJECT:chart" in scene["warnings"]
    assert body["lesson_order"][0]["requires_review"] is False


# -- the cheap read path -----------------------------------------------------------
def test_get_review_before_a_build_is_404(client):
    artifact_id = _upload(client)
    response = client.get(f"/artifacts/{artifact_id}/review-package", headers=HEADERS)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_get_review_never_renders_again(client, settings):
    artifact_id = _upload(client)
    built = _review(client, artifact_id)

    # Make the render path unusable: the stored review must not touch it.
    def explode(*_args, **_kwargs):
        raise AssertionError("the review read path must not re-render")

    client.app.state.rendering_service.compile = explode  # type: ignore[method-assign]
    response = client.get(f"/artifacts/{artifact_id}/review-package", headers=HEADERS)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["package_id"] == built["package_id"]
    assert body["scenes"] == built["scenes"]


def test_review_render_is_served_from_the_package(client, settings):
    artifact_id = _upload(client)
    body = _review(client, artifact_id)

    response = client.get(
        f"/artifacts/{artifact_id}/review-package/renders/0", headers=HEADERS
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.content.startswith(b"<svg")

    store = client.app.state.review_service._object_store
    loaded = read_package(store, body["prefix"])
    assert loaded is not None
    assert response.content == loaded.data(body["scenes"][0]["fallback_asset"])


def test_review_render_unknown_order_is_404(client):
    artifact_id = _upload(client)
    _review(client, artifact_id)
    response = client.get(
        f"/artifacts/{artifact_id}/review-package/renders/99", headers=HEADERS
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


# -- isolation and blocking --------------------------------------------------------
def test_review_is_tenant_scoped(client, repository):
    artifact_id = _upload(client)
    repository.ensure_institution("inst-2")

    assert (
        client.post(f"/artifacts/{artifact_id}/review-package", headers=ALT_HEADERS).status_code
        == 403
    )
    assert (
        client.get(f"/artifacts/{artifact_id}/review-package", headers=ALT_HEADERS).status_code
        == 403
    )
    assert (
        client.get(
            f"/artifacts/{artifact_id}/review-package/renders/0", headers=ALT_HEADERS
        ).status_code
        == 403
    )


def test_review_requires_the_institution_header(client):
    artifact_id = _upload(client)
    assert client.post(f"/artifacts/{artifact_id}/review-package").status_code == 422
    assert client.get(f"/artifacts/{artifact_id}/review-package").status_code == 422


def test_review_of_an_unknown_artifact_is_404(client):
    assert (
        client.get("/artifacts/00000000-0000-0000-0000-000000000000/review-package", headers=HEADERS).status_code
        == 404
    )


def test_blocked_render_is_never_offered_for_review(settings, repository):
    """V0-007 acceptance: a teacher cannot approve a blocking failure."""

    def factory(object_store, config: RenderConfig):
        return FakeRenderer(object_store=object_store, config=config, fail_orders=(0,))

    with TestClient(create_app(settings, renderer_factory=factory)) as test_client:
        artifact_id = _upload(test_client)
        response = test_client.post(
            f"/artifacts/{artifact_id}/review-package", headers=HEADERS
        )

        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "PUBLICATION_BLOCKED"
        # Nothing was built, so there is nothing to review and nothing to approve.
        assert test_client.get(
            f"/artifacts/{artifact_id}/review-package", headers=HEADERS
        ).status_code == 404
        assert not (settings.object_root / "packages").exists()


def test_publication_blocked_error_reaches_the_service(
    repository, object_store, extractor, render_config, upload_service, course
):
    """The service, not just the route, refuses a failed render."""

    from app.compiler.render_service import RenderingService

    deck = simple_pptx()
    artifact = upload_service.upload(
        institution_id="inst-1", course_id=course.course_id, filename="deck.pptx", data=deck
    ).artifact
    rendering = RenderingService(
        repository,
        object_store,
        extractor,
        FakeRenderer(object_store=object_store, fail_orders=(0,)),
        config=render_config,
    )
    service = ReviewService(repository, object_store, PackageBuildService(repository, object_store, rendering))

    with pytest.raises(PublicationBlockedError):
        service.build_review("inst-1", artifact.artifact_id)


# -- immutability ------------------------------------------------------------------
def test_review_does_not_mutate_the_stored_package(client, settings):
    artifact_id = _upload(client)
    built = _review(client, artifact_id)
    store = client.app.state.review_service._object_store
    before = read_package(store, built["prefix"])
    assert before is not None

    client.get(f"/artifacts/{artifact_id}/review-package", headers=HEADERS)
    client.get(f"/artifacts/{artifact_id}/review-package/renders/0", headers=HEADERS)

    after = read_package(store, built["prefix"])
    assert after is not None
    assert [(f.path, f.sha256) for f in after.package.files] == [
        (f.path, f.sha256) for f in before.package.files
    ]


def test_the_package_id_is_the_content_identity(client):
    """Identical content resolves to one package, so review never duplicates storage."""

    artifact_id = _upload(client)
    first = _review(client, artifact_id)
    second = _review(client, artifact_id)

    assert first["package_id"] == second["package_id"]
    assert first["content_package_version"] == second["content_package_version"]
    packages = [path for path in (client.app.state.settings.object_root / "packages").iterdir()]
    assert len(packages) == 1
