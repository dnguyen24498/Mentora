"""V0-005 fidelity gate: every slide has a render or explicit FAILED; FAILED blocks publication."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.common.errors import PublicationBlockedError
from app.compiler.renderers.base import (
    RenderBudget,
    RenderConfig,
    RenderErrorCode,
    RenderReport,
    RenderRequest,
    RenderStatus,
    RendererIdentity,
    RenderUsage,
    SceneRender,
)
from app.compiler.renderers.testing import FakeRenderer
from app.compiler.validators.fidelity import assert_publishable, validate_render
from tests.fixtures import build_pptx, text_shape

IDENTITY = RendererIdentity(
    name="fake-renderer",
    version="1.0.0",
    engine="fake",
    config_hash="deadbeef",
    data_region="local",
)


def _document(extractor, slides: int = 1):
    deck = build_pptx(
        [[text_shape(2 + index, f"S{index}", text=f"slide {index}")] for index in range(slides)]
    )
    return extractor.extract(deck)


def _render(document, *, object_store=None, **kwargs):
    renderer = FakeRenderer(object_store=object_store, **kwargs)
    return renderer.render(
        RenderRequest(document=document, identity=renderer.identity()),
        budget=RenderBudget(5.0, max_attempts=2),
    )


def _report(*results: SceneRender, cancelled: bool = False) -> RenderReport:
    return RenderReport(
        results=tuple(results),
        usage=RenderUsage(),
        renderer=IDENTITY,
        cancelled=cancelled,
    )


def _rendered(order: int, **overrides) -> SceneRender:
    base = SceneRender(
        order=order,
        scene_id=f"ppt/slides/slide{order + 1}.xml",
        status=RenderStatus.RENDERED,
        fidelity="STRUCTURAL_RENDERED",
        asset_ref="renders/abc.svg",
        renderer=IDENTITY,
    )
    return replace(base, **overrides)


# -- happy path ------------------------------------------------------------------
def test_fully_rendered_document_is_publishable(extractor):
    document = _document(extractor, slides=2)
    report = _render(document)
    validation = validate_render(document, report)

    assert validation.ok is True
    assert validation.publishable is True
    assert validation.requires_review is False
    assert validation.scene_count == 2
    assert validation.issues == ()


# -- the two acceptance criteria -------------------------------------------------
def test_a_scene_without_a_render_is_a_hard_error(extractor):
    document = _document(extractor, slides=2)
    report = _report(_rendered(0))  # scene 1 has no render at all
    validation = validate_render(document, report)

    assert validation.publishable is False
    codes = [i.code for i in validation.errors]
    assert "MISSING_RENDER" in codes
    assert any(i.scene_order == 1 for i in validation.errors)


def test_no_report_at_all_is_a_hard_error(extractor):
    validation = validate_render(_document(extractor), None)

    assert validation.publishable is False
    assert {i.code for i in validation.errors} == {"MISSING_RENDER"}


def test_failed_render_blocks_publication(extractor):
    document = _document(extractor)
    report = _report(
        SceneRender(
            order=0,
            scene_id="ppt/slides/slide1.xml",
            status=RenderStatus.FAILED,
            renderer=IDENTITY,
            error_code=RenderErrorCode.RENDER_TIMEOUT,
            error_message="render deadline exceeded",
        )
    )
    validation = validate_render(document, report)

    assert validation.publishable is False
    assert [i.code for i in validation.errors] == ["RENDER_FAILED"]
    assert "RENDER_TIMEOUT" in validation.errors[0].message


def test_cancelled_render_blocks_publication(extractor):
    document = _document(extractor)
    report = _report(
        SceneRender(
            order=0,
            scene_id="ppt/slides/slide1.xml",
            status=RenderStatus.CANCELLED,
            renderer=IDENTITY,
            error_code=RenderErrorCode.CANCELLED,
        ),
        cancelled=True,
    )
    validation = validate_render(document, report)

    assert validation.publishable is False
    assert "RENDER_CANCELLED" in {i.code for i in validation.errors}
    assert "RENDER_INCOMPLETE" in {i.code for i in validation.errors}


def test_degraded_is_publishable_but_requires_review(extractor):
    document = extractor.extract(
        build_pptx([[text_shape(2, "T", text="hi", font="Be Vietnam Pro")]])
    )
    report = _render(document)
    validation = validate_render(document, report)

    assert validation.publishable is True
    assert validation.requires_review is True
    review = [i for i in validation.issues if i.severity == "review"]
    assert [i.code for i in review] == ["DEGRADED_REQUIRES_REVIEW"]


# -- DEC-CONTENT-006 provenance ---------------------------------------------------
def test_rendered_scene_without_asset_fails(extractor):
    document = _document(extractor)
    validation = validate_render(document, _report(_rendered(0, asset_ref=None)))
    assert "MISSING_FALLBACK_ASSET" in {i.code for i in validation.errors}


def test_rendered_scene_without_renderer_identity_fails(extractor):
    document = _document(extractor)
    validation = validate_render(document, _report(_rendered(0, renderer=None)))
    assert "MISSING_RENDERER_IDENTITY" in {i.code for i in validation.errors}


def test_fidelity_outside_the_schema_enum_fails(extractor):
    document = _document(extractor)
    validation = validate_render(document, _report(_rendered(0, fidelity="MAGIC")))
    assert "INVALID_FIDELITY" in {i.code for i in validation.errors}


def test_scene_id_mismatch_fails(extractor):
    document = _document(extractor)
    validation = validate_render(
        document, _report(_rendered(0, scene_id="ppt/slides/slide99.xml"))
    )
    assert "SCENE_ID_MISMATCH" in {i.code for i in validation.errors}


def test_duplicate_render_fails(extractor):
    document = _document(extractor)
    validation = validate_render(document, _report(_rendered(0), _rendered(0)))
    assert "DUPLICATE_RENDER" in {i.code for i in validation.errors}


def test_empty_document_is_never_publishable(extractor):
    document = extractor.extract(
        build_pptx([]),  # no slides
    )
    validation = validate_render(document, _report())
    assert validation.publishable is False
    assert "NO_SLIDES" in {i.code for i in validation.errors}


def test_zero_dimensions_fail_the_shape_check(extractor):
    document = _document(extractor)
    broken = replace(document, slides=[replace(document.slides[0], width=0, height=0)])
    validation = validate_render(broken, _render(broken))
    assert "INVALID_SCENE_DIMENSIONS" in {i.code for i in validation.errors}


# -- the gate ---------------------------------------------------------------------
def test_assert_publishable_is_silent_when_publishable(extractor):
    document = _document(extractor)
    assert_publishable(validate_render(document, _render(document)))


def test_assert_publishable_raises_publication_blocked(extractor):
    document = _document(extractor)
    report = _report(
        SceneRender(
            order=0,
            scene_id="ppt/slides/slide1.xml",
            status=RenderStatus.FAILED,
            renderer=IDENTITY,
            error_code=RenderErrorCode.RENDER_FAILED,
        )
    )
    with pytest.raises(PublicationBlockedError) as exc:
        assert_publishable(validate_render(document, report))
    assert exc.value.code.value == "PUBLICATION_BLOCKED"
    assert exc.value.http_status == 409


def test_validation_report_is_serialisable(extractor):
    document = _document(extractor)
    payload = validate_render(document, _render(document)).to_dict()
    assert set(payload) == {"ok", "publishable", "requires_review", "scene_count", "issues"}


def test_config_defaults_are_deterministic():
    assert RenderConfig().config_hash() == RenderConfig().config_hash()
