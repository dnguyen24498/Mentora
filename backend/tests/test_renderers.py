"""V0-005 renderer contract: determinism, fidelity, warnings, deadline, cancel."""

from __future__ import annotations

import pytest

from app.compiler.renderers.base import (
    CancelToken,
    RenderBudget,
    RenderConfig,
    RenderErrorCode,
    RenderRequest,
    RenderStatus,
    RendererError,
)
from app.compiler.renderers.structural import (
    MISSING_FONT_PREFIX,
    UNSUPPORTED_OBJECT_PREFIX,
    StructuralSvgRenderer,
)
from app.compiler.renderers.testing import FakeRenderer
from tests.fixtures import build_pptx, picture_shape, simple_pptx, text_shape


def _render(renderer, document, *, budget=None, cancel=None):
    return renderer.render(
        RenderRequest(document=document, identity=renderer.identity()),
        budget=budget or RenderBudget(5.0, max_attempts=2),
        cancel=cancel,
    )


def test_same_input_and_config_is_byte_identical(renderer, extractor, object_store):
    first = extractor.extract(simple_pptx(), source_sha256="a" * 64)
    second = extractor.extract(simple_pptx(), source_sha256="a" * 64)

    a = _render(renderer, first)
    b = _render(renderer, second)

    assert a.results[0].asset_ref == b.results[0].asset_ref
    assert object_store.get(a.results[0].asset_ref) == object_store.get(b.results[0].asset_ref)
    assert a.results[0].renderer.config_hash == b.results[0].renderer.config_hash


def test_every_slide_gets_exactly_one_render(renderer, extractor):
    deck = build_pptx([[text_shape(2, "A", text="one")], [text_shape(2, "B", text="two")]])
    document = extractor.extract(deck)
    report = _render(renderer, document)

    assert [r.order for r in report.results] == [0, 1]
    assert all(r.status is RenderStatus.RENDERED for r in report.results)
    assert report.usage.slides_rendered == 2


def test_rendered_svg_escapes_slide_text(renderer, extractor, object_store):
    hostile = "</text><script>alert(1)</script> & <b>bold</b>"
    document = extractor.extract(build_pptx([[text_shape(2, "T", text=hostile)]]))
    report = _render(renderer, document)

    svg = object_store.get(report.results[0].asset_ref).decode("utf-8")
    # The text is present but inert: no live element can be injected.
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg
    assert "&amp;" in svg


def test_missing_font_degrades_with_warning(renderer, extractor):
    deck = build_pptx([[text_shape(2, "T", text="hi", font="Be Vietnam Pro")]])
    report = _render(renderer, extractor.extract(deck))
    scene = report.results[0]

    assert scene.fidelity == "DEGRADED_RENDERED"
    assert scene.missing_fonts == ("Be Vietnam Pro",)
    assert f"{MISSING_FONT_PREFIX}Be Vietnam Pro" in scene.warnings
    assert any("requires review" in w for w in scene.warnings)


def test_available_font_stays_structural(renderer, extractor):
    deck = build_pptx([[text_shape(2, "T", text="hi", font="Arial")]])
    report = _render(renderer, extractor.extract(deck))
    assert report.results[0].fidelity == "STRUCTURAL_RENDERED"
    assert report.results[0].missing_fonts == ()


def test_unsupported_object_degrades(object_store, extractor):
    renderer = FakeRenderer(object_store=object_store, supported_kinds=("text",))
    deck = build_pptx([[picture_shape(4, "Figure")]])
    report = _render(renderer, extractor.extract(deck))
    scene = report.results[0]

    assert scene.fidelity == "DEGRADED_RENDERED"
    assert f"{UNSUPPORTED_OBJECT_PREFIX}picture" in scene.warnings


def test_expired_deadline_marks_scene_failed(renderer, extractor):
    document = extractor.extract(simple_pptx())
    report = _render(renderer, document, budget=RenderBudget(0.0, max_attempts=2))
    scene = report.results[0]

    assert scene.status is RenderStatus.FAILED
    assert scene.error_code is RenderErrorCode.RENDER_TIMEOUT
    assert scene.retryable is True
    assert scene.asset_ref is None
    assert report.usage.slides_failed == 1


def test_cancellation_is_distinct_from_failure(renderer, extractor):
    token = CancelToken()
    token.cancel()
    document = extractor.extract(simple_pptx())
    report = _render(renderer, document, cancel=token)

    assert report.cancelled is True
    assert report.results[0].status is RenderStatus.CANCELLED
    assert report.results[0].status is not RenderStatus.FAILED
    assert report.usage.slides_cancelled == 1
    assert report.usage.slides_failed == 0


def test_cancelling_mid_render_covers_remaining_scenes(object_store, extractor):
    """A cancel between slides still yields a result for every slide."""

    class CancellingRenderer(FakeRenderer):
        def _attempt_scene(self, request, scene, token, budget):
            result = super()._attempt_scene(request, scene, token, budget)
            if scene.order == 0:
                token.cancel()
            return result

    renderer = CancellingRenderer(object_store=object_store)
    deck = build_pptx([[text_shape(2, "A", text="one")], [text_shape(3, "B", text="two")]])
    report = _render(renderer, extractor.extract(deck))

    assert [r.order for r in report.results] == [0, 1]
    assert report.results[0].status is RenderStatus.RENDERED
    assert report.results[1].status is RenderStatus.CANCELLED
    assert report.cancelled is True


def test_transient_failure_is_retried_within_budget(object_store, extractor):
    renderer = FakeRenderer(object_store=object_store, transient_failures=1)
    report = _render(
        renderer, extractor.extract(simple_pptx()), budget=RenderBudget(5.0, max_attempts=2)
    )
    assert report.results[0].status is RenderStatus.RENDERED
    assert report.results[0].attempts == 2


def test_permanent_failure_is_not_retried(object_store, extractor):
    renderer = FakeRenderer(
        object_store=object_store,
        fail_orders=(0,),
        fail_code=RenderErrorCode.CORRUPT_INPUT,
    )
    report = _render(
        renderer, extractor.extract(simple_pptx()), budget=RenderBudget(5.0, max_attempts=3)
    )
    scene = report.results[0]

    assert scene.status is RenderStatus.FAILED
    assert scene.attempts == 1, "a permanent error must not loop"
    assert scene.retryable is False


def test_retry_stops_at_the_deadline(object_store, extractor):
    renderer = FakeRenderer(object_store=object_store, fail_orders=(0,))
    report = _render(
        renderer, extractor.extract(simple_pptx()), budget=RenderBudget(0.0, max_attempts=5)
    )
    assert report.results[0].attempts == 1


def test_open_circuit_refuses_new_work(object_store, extractor):
    config = RenderConfig(circuit_failure_threshold=1)
    renderer = FakeRenderer(
        object_store=object_store, config=config, fail_orders=(0,)
    )
    document = extractor.extract(simple_pptx())

    first = _render(renderer, document)
    assert first.results[0].status is RenderStatus.FAILED
    assert renderer.health().state == "open"

    with pytest.raises(RendererError) as exc:
        _render(renderer, document)
    assert exc.value.code is RenderErrorCode.RENDERER_UNAVAILABLE


def test_raising_renderer_propagates_as_capability_error(object_store, extractor):
    renderer = FakeRenderer(
        object_store=object_store, raise_code=RenderErrorCode.RENDERER_UNAVAILABLE
    )
    with pytest.raises(RendererError) as exc:
        _render(renderer, extractor.extract(simple_pptx()))
    assert exc.value.code is RenderErrorCode.RENDERER_UNAVAILABLE


def test_assets_are_content_addressed_and_reused(renderer, extractor, settings):
    document = extractor.extract(simple_pptx())
    first = _render(renderer, document)
    second = _render(renderer, document)

    assert first.results[0].asset_ref == second.results[0].asset_ref
    render_dir = settings.object_root / "renders"
    assert len(list(render_dir.iterdir())) == 1


def test_health_reports_counters_and_queue_metrics(renderer, extractor):
    _render(renderer, extractor.extract(simple_pptx()))
    health = renderer.health()

    assert health.state == "closed"
    assert health.total_rendered == 1
    assert health.total_failed == 0
    assert health.in_flight == 0


def test_inspect_support_declares_the_structural_ceiling(renderer):
    support = renderer.inspect_support()

    assert support.supports is True
    assert support.fidelity_ceiling == "STRUCTURAL_RENDERED"
    assert "Arial" in support.available_fonts
    assert any("DEC-TECH-005" in reason for reason in support.reasons)


def test_renderer_identity_is_stable_and_config_sensitive(object_store):
    a = StructuralSvgRenderer(object_store, RenderConfig())
    b = StructuralSvgRenderer(object_store, RenderConfig())
    c = StructuralSvgRenderer(object_store, RenderConfig(width_px=640))

    assert a.identity() == b.identity()
    assert a.identity().config_hash != c.identity().config_hash
    assert a.identity().data_region == "local"


def test_renderer_cannot_be_constructed_without_a_store(object_store):
    # The structural renderer must always be able to persist its asset.
    renderer = StructuralSvgRenderer(None, RenderConfig())
    report = _render(renderer, _doc())
    assert report.results[0].status is RenderStatus.FAILED
    assert report.results[0].error_code is RenderErrorCode.STORAGE_FAILURE


def _doc():
    from app.compiler.extractors.pptx import PptxExtractor

    return PptxExtractor().extract(simple_pptx())
