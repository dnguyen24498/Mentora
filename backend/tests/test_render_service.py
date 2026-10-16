"""V0-005 render stage end-to-end: service orchestration, gate, API surface."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.common.errors import (
    AppError,
    PublicationBlockedError,
    RendererUnavailableError,
    TenantAccessError,
)
from app.compiler.render_service import RenderingService
from app.compiler.renderers.base import (
    RenderConfig,
    RenderErrorCode,
    RenderStatus,
    RendererError,
)
from app.compiler.renderers.structural import StructuralSvgRenderer
from app.compiler.renderers.testing import FakeRenderer
from app.compiler.validators.fidelity import assert_publishable
from tests.fixtures import build_pptx, simple_pptx, text_shape

HEADERS = {"X-Institution-Id": "inst-1"}
ALT_HEADERS = {"X-Institution-Id": "inst-2"}


# -- service ---------------------------------------------------------------------
def test_compile_projects_render_onto_every_scene(stored_artifact, rendering_service):
    artifact, _course = stored_artifact
    result = rendering_service.compile("inst-1", artifact.artifact_id)

    assert result.document.slide_count == 1
    for scene in result.document.slides:
        assert scene.fallback_asset, "every scene needs a fallback asset"
        assert scene.fidelity == "STRUCTURAL_RENDERED"
        assert scene.renderer and scene.renderer["name"] == "local-structural-svg"
    assert result.report.usage.slides_rendered == 1
    assert result.validation.publishable is True
    assert result.validation.requires_review is False


def test_compile_reports_job_status(stored_artifact, rendering_service):
    artifact, _course = stored_artifact
    payload = rendering_service.compile("inst-1", artifact.artifact_id).to_dict()

    assert payload["job_status"] == "EXTRACTED"
    assert set(payload) == {"content_ir", "render", "validation", "job_status"}
    assert payload["render"]["scenes"][0]["status"] == "RENDERED"


def test_compile_is_tenant_scoped(stored_artifact, rendering_service, repository):
    artifact, _course = stored_artifact
    repository.ensure_institution("inst-2")

    with pytest.raises(TenantAccessError):
        rendering_service.compile("inst-2", artifact.artifact_id)


def test_failed_render_blocks_publication_and_fails_the_job(
    stored_artifact, repository, object_store, extractor, render_config
):
    artifact, _course = stored_artifact
    service = RenderingService(
        repository,
        object_store,
        extractor,
        FakeRenderer(object_store=object_store, fail_orders=(0,)),
        config=render_config,
    )
    result = service.compile("inst-1", artifact.artifact_id)

    assert result.report.results[0].status is RenderStatus.FAILED
    assert result.validation.publishable is False
    with pytest.raises(PublicationBlockedError):
        assert_publishable(result.validation)
    job = repository.get_job_for_artifact("inst-1", artifact.artifact_id)
    assert job.status == "FAILED"


def test_unavailable_renderer_raises_stable_code_and_fails_the_job(
    stored_artifact, repository, object_store, extractor
):
    artifact, _course = stored_artifact
    service = RenderingService(
        repository,
        object_store,
        extractor,
        FakeRenderer(object_store=object_store, raise_code=RenderErrorCode.RENDERER_UNAVAILABLE),
    )
    with pytest.raises(RendererUnavailableError) as exc:
        service.compile("inst-1", artifact.artifact_id)
    assert exc.value.http_status == 503
    assert repository.get_job_for_artifact("inst-1", artifact.artifact_id).status == "FAILED"


def test_render_scene_svg_returns_deterministic_bytes(stored_artifact, rendering_service):
    artifact, _course = stored_artifact
    payload, scene = rendering_service.render_scene_svg("inst-1", artifact.artifact_id, 0)
    again, _ = rendering_service.render_scene_svg("inst-1", artifact.artifact_id, 0)

    assert payload.startswith(b"<svg")
    assert payload == again
    assert scene.status is RenderStatus.RENDERED


def test_render_scene_svg_unknown_order_raises(stored_artifact, rendering_service):
    artifact, _course = stored_artifact
    with pytest.raises(RendererUnavailableError):
        rendering_service.render_scene_svg("inst-1", artifact.artifact_id, 99)


def test_compile_emits_structured_telemetry(stored_artifact, rendering_service):
    artifact, _course = stored_artifact
    rendering_service.compile("inst-1", artifact.artifact_id)
    metrics = rendering_service.telemetry.metrics

    assert metrics.renders_started == 1
    assert metrics.scenes_rendered == 1
    assert metrics.scenes_failed == 0
    assert metrics.publish_blocked == 0


def test_telemetry_counts_blocked_publication(stored_artifact, repository, object_store, extractor):
    artifact, _course = stored_artifact
    service = RenderingService(
        repository,
        object_store,
        extractor,
        FakeRenderer(object_store=object_store, fail_orders=(0,)),
    )
    service.compile("inst-1", artifact.artifact_id)
    assert service.telemetry.metrics.publish_blocked == 1


def test_compile_marks_missing_fonts_for_review(
    repository, object_store, extractor, upload_service, course, render_config
):
    deck = build_pptx([[text_shape(2, "T", text="hi", font="Be Vietnam Pro")]])
    artifact = upload_service.upload(
        institution_id="inst-1",
        course_id=course.course_id,
        filename="brand.pptx",
        data=deck,
    ).artifact
    service = RenderingService(
        repository, object_store, extractor, StructuralSvgRenderer(object_store, render_config),
        config=render_config,
    )
    result = service.compile("inst-1", artifact.artifact_id)

    assert result.document.slides[0].fidelity == "DEGRADED_RENDERED"
    assert result.validation.publishable is True
    assert result.validation.requires_review is True
    assert any(w.startswith("MISSING_FONT:") for w in result.document.slides[0].warnings)


def test_recompile_is_idempotent(stored_artifact, rendering_service, settings):
    artifact, _course = stored_artifact
    first = rendering_service.compile("inst-1", artifact.artifact_id)
    second = rendering_service.compile("inst-1", artifact.artifact_id)

    assert first.document.slides[0].fallback_asset == second.document.slides[0].fallback_asset
    # content-addressed: recompiling does not duplicate assets
    assert len(list((settings.object_root / "renders").iterdir())) == 1


def test_renderer_error_without_code_is_capability_failure(
    stored_artifact, repository, object_store, extractor
):
    artifact, _course = stored_artifact

    class ExplodingRenderer(FakeRenderer):
        def _attempt_scene(self, request, scene, token, budget):
            raise RendererError(RenderErrorCode.RENDER_FAILED, "boom")

    service = RenderingService(
        repository, object_store, extractor, ExplodingRenderer(object_store=object_store)
    )
    with pytest.raises(AppError) as exc:
        service.compile("inst-1", artifact.artifact_id)
    assert exc.value.http_status == 503


# -- API -------------------------------------------------------------------------
@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _upload_simple(client) -> str:
    course_id = client.post("/courses", params={"title": "Intro"}, headers=HEADERS).json()["course_id"]
    response = client.post(
        f"/courses/{course_id}/materials",
        files={"file": ("deck.pptx", simple_pptx(), "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
        headers=HEADERS,
    )
    assert response.status_code == 202, response.text
    return response.json()["artifact_id"]


def test_compile_endpoint_returns_reports(client):
    artifact_id = _upload_simple(client)
    response = client.post(f"/artifacts/{artifact_id}/compile", headers=HEADERS)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["job_status"] == "EXTRACTED"
    assert body["validation"]["publishable"] is True
    assert body["render"]["scenes"][0]["asset_ref"]
    assert body["render"]["scenes"][0]["renderer"]["engine"] == "stdlib-svg"
    assert body["content_ir"]["slides"][0]["fallback_asset"]


def test_render_endpoint_serves_svg(client):
    artifact_id = _upload_simple(client)
    response = client.get(f"/artifacts/{artifact_id}/renders/0", headers=HEADERS)

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.content.startswith(b"<svg")


def test_render_endpoint_unknown_slide_is_503(client):
    artifact_id = _upload_simple(client)
    assert client.get(f"/artifacts/{artifact_id}/renders/99", headers=HEADERS).status_code == 503


def test_renderer_endpoint_reports_capability_and_health(client):
    body = client.get("/renderer", headers=HEADERS).json()

    assert body["identity"]["name"] == "local-structural-svg"
    assert body["identity"]["data_region"] == "local"
    assert body["support"]["fidelity_ceiling"] == "STRUCTURAL_RENDERED"
    assert body["health"]["state"] == "closed"


def test_compile_requires_the_owning_tenant(client):
    artifact_id = _upload_simple(client)
    response = client.post(f"/artifacts/{artifact_id}/compile", headers=ALT_HEADERS)
    assert response.status_code in (403, 404)
    assert response.json()["error"]["code"] in {"TENANT_ACCESS_DENIED", "NOT_FOUND"}


def test_compile_rejects_a_legacy_upload_with_stable_code(client):
    course_id = client.post("/courses", params={"title": "Intro"}, headers=HEADERS).json()["course_id"]
    response = client.post(
        f"/courses/{course_id}/materials",
        files={"file": ("old.ppt", b"MZ\x90\x00", "application/vnd.ms-powerpoint")},
        headers=HEADERS,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_LEGACY_FORMAT"


def test_renderer_factory_injection_is_honoured(settings):
    """The renderer is replaceable infrastructure, not a hard-wired dependency."""

    seen = {}

    def factory(object_store, config: RenderConfig):
        seen["config"] = config
        return FakeRenderer(object_store=object_store, config=config)

    with TestClient(create_app(settings, renderer_factory=factory)) as test_client:
        artifact_id = _upload_simple(test_client)
        body = test_client.post(f"/artifacts/{artifact_id}/compile", headers=HEADERS).json()

    assert seen["config"].data_region == "local"
    assert body["render"]["scenes"][0]["renderer"]["name"] == "fake-renderer"
