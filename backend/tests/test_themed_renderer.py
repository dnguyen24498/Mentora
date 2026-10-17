"""V0-019: the themed renderer re-authors content in the platform theme.

These tests pin the contract that makes themed mode the default:

* the theme owns the typefaces, so an unavailable source font cannot degrade a
  scene (the failure mode V0-018 could only report);
* the *content* is complete — every paragraph, picture, and table cell is placed
  and nothing is silently dropped;
* what cannot be re-authored (a chart) or does not fit degrades the scene,
  explicitly, instead of disappearing.
"""

from __future__ import annotations

import re
import struct

import pytest

from app.compiler.extractors.pptx import PptxExtractor
from app.compiler.media import document_media_refs, read_media_parts
from app.compiler.renderers.base import (
    RenderBudget,
    RenderConfig,
    RenderRequest,
    RenderStatus,
)
from app.compiler.renderers.mentora_theme import DEFAULT_THEME
from app.compiler.renderers.themed import (
    CONTENT_DROPPED_PREFIX,
    TEXT_OVERFLOW_PREFIX,
    ThemedSvgRenderer,
    classify_scene,
    content_refs,
)
from tests.fixtures import (
    REL_CHART,
    REL_IMAGE,
    build_pptx,
    chart_shape,
    picture_shape,
    table_shape,
    text_shape,
)

THEME_FONT_MARKER = "Noto Sans, DejaVu Sans"


def _png(width: int, height: int) -> bytes:
    """A PNG header with a known size: enough for the renderer's size probe."""

    ihdr = struct.pack(">II", width, height) + b"\x08\x02\x00\x00\x00" + b"\x00\x00\x00\x00"
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr


def _render(renderer, data: bytes):
    document = PptxExtractor().extract(data)
    media = read_media_parts(data, document_media_refs(document))
    report = renderer.render(
        RenderRequest(document=document, identity=renderer.identity(), media=media),
        budget=RenderBudget(5.0, max_attempts=2),
    )
    return document, report


def _svg(object_store, scene) -> str:
    assert scene.asset_ref is not None
    return object_store.get(scene.asset_ref).decode("utf-8")


# -- identity and capability -------------------------------------------------------
def test_capability_never_claims_a_native_render(themed_renderer):
    identity = themed_renderer.identity()
    support = themed_renderer.inspect_support()

    assert identity.name == "mentora-themed-svg"
    assert identity.data_region == "local"
    assert support.supports is True
    assert support.fidelity_ceiling == "THEMED_RENDERED"
    assert "chart" not in support.supported_kinds
    assert any("DEC-TECH-005" in reason for reason in support.reasons)


def test_the_theme_is_bound_into_the_renderer_identity(object_store):
    """A theme change changes every slide, so it must change the config hash."""

    plain = ThemedSvgRenderer(object_store, RenderConfig())
    restyled = ThemedSvgRenderer(
        object_store, RenderConfig(), theme=DEFAULT_THEME.with_version("9.9.9")
    )

    assert plain.identity().config_hash != restyled.identity().config_hash
    assert plain.theme_identity() == {"name": "mentora-default", "version": "1.0.0"}


def test_a_themed_scene_never_reports_a_missing_font(themed_renderer):
    _, report = _render(
        themed_renderer,
        build_pptx([[text_shape(2, "T", text="Brand", font="Be Vietnam Pro")]]),
    )
    scene = report.scene(0)

    assert scene.status is RenderStatus.RENDERED
    assert scene.fidelity == "THEMED_RENDERED"
    assert scene.missing_fonts == ()
    assert scene.warnings == ()


# -- determinism -------------------------------------------------------------------
def test_the_same_input_renders_byte_identically(themed_renderer, object_store):
    deck = build_pptx(
        [
            [
                text_shape(2, "Title", text="Attention", placeholder="title"),
                text_shape(3, "Body", text="Query, key, value"),
                table_shape(5, "Results", [["Model", "BLEU"], ["Baseline", "24.1"]]),
            ]
        ]
    )
    _, first = _render(themed_renderer, deck)
    _, second = _render(themed_renderer, deck)

    assert _svg(object_store, first.scene(0)) == _svg(object_store, second.scene(0))


# -- the look is ours --------------------------------------------------------------
def test_the_render_draws_the_theme_palette_and_footer(themed_renderer, object_store):
    _, report = _render(
        themed_renderer, build_pptx([[text_shape(2, "T", text="Hello world")]])
    )
    svg = _svg(object_store, report.scene(0))

    assert THEME_FONT_MARKER in svg, "the theme's own font stack is used"
    assert DEFAULT_THEME.background in svg
    assert DEFAULT_THEME.primary in svg
    assert DEFAULT_THEME.accent in svg
    assert DEFAULT_THEME.footer_label in svg
    assert "Be Vietnam Pro" not in svg


def test_a_title_only_slide_is_a_hero_slide(themed_renderer, object_store):
    """The archetype is load-bearing: a title slide is larger and centred."""

    _, title_only = _render(
        themed_renderer, build_pptx([[text_shape(2, "T", text="Hello world")]])
    )
    _, content = _render(
        themed_renderer,
        build_pptx(
            [
                [
                    text_shape(2, "Title", text="Hello world", placeholder="title"),
                    text_shape(3, "Body", text="A body paragraph"),
                ]
            ]
        ),
    )
    hero_svg = _svg(object_store, title_only.scene(0))
    content_svg = _svg(object_store, content.scene(0))

    def first_text_y(svg: str) -> float:
        match = re.search(r"<text x=\"[\d.]+\" y=\"([\d.]+)\"", svg)
        assert match, svg[:200]
        return float(match.group(1))

    def first_font_size(svg: str) -> float:
        match = re.search(r"font-size=\"([\d.]+)\"", svg)
        assert match
        return float(match.group(1))

    assert first_font_size(hero_svg) > first_font_size(content_svg)
    assert first_text_y(hero_svg) > first_text_y(content_svg)


# -- completeness ------------------------------------------------------------------
def test_every_paragraph_picture_and_cell_is_placed(themed_renderer, object_store):
    deck = build_pptx(
        [
            [
                text_shape(2, "Title", text="Agenda", placeholder="title"),
                text_shape(
                    3,
                    "Body",
                    paragraphs=[(0, "First point"), (1, "Nested point"), (0, "Last point")],
                ),
                picture_shape(4, "Figure", rel_id="rIdImg"),
                table_shape(5, "Results", [["Model", "BLEU"], ["Baseline", "24.1"]]),
            ]
        ],
        extra_slide_rels={1: [("rIdImg", REL_IMAGE, "../media/image1.png")]},
        extra_entries={"ppt/media/image1.png": _png(320, 200)},
    )
    _, report = _render(themed_renderer, deck)
    scene = report.scene(0)
    svg = _svg(object_store, scene)

    assert scene.fidelity == "THEMED_RENDERED"
    assert not [w for w in scene.warnings if w.startswith(CONTENT_DROPPED_PREFIX)]
    for text in ("Agenda", "First point", "Nested point", "Last point", "Model", "BLEU", "24.1"):
        assert text in svg, text
    assert "<image" in svg


def test_content_refs_are_text_pictures_and_table_cells(extractor):
    deck = build_pptx(
        [
            [
                text_shape(2, "Title", text="T", placeholder="title"),
                picture_shape(4, "Figure", rel_id="rIdImg"),
                table_shape(5, "Row", [["a", "b"]]),
            ]
        ],
        extra_slide_rels={1: [("rIdImg", REL_IMAGE, "../media/image1.png")]},
        extra_entries={"ppt/media/image1.png": _png(2, 2)},
    )
    scene = extractor.extract(deck).slides[0]
    refs = content_refs(scene)

    assert any(ref.endswith("#p0") for ref in refs), "text paragraph"
    assert any(ref.endswith("#img") for ref in refs), "picture"
    assert any(ref.endswith("#tc0,0") for ref in refs), "table cell"


def test_a_long_deck_reports_overflow_rather_than_dropping_content(themed_renderer, object_store):
    long_text = " ".join(f"word{index}" for index in range(900))
    deck = build_pptx([[text_shape(2, "T", text=long_text)]])
    _, report = _render(themed_renderer, deck)
    scene = report.scene(0)
    svg = _svg(object_store, scene)

    assert scene.fidelity == "DEGRADED_RENDERED"
    assert any(w.startswith(TEXT_OVERFLOW_PREFIX) for w in scene.warnings)
    # Never silently dropped: the first and last words are still in the document.
    assert "word0" in svg
    assert "word899" in svg
    assert not [w for w in scene.warnings if w.startswith(CONTENT_DROPPED_PREFIX)]


# -- degradation is explicit -------------------------------------------------------
def test_a_chart_degrades_the_scene_for_review(themed_renderer, object_store):
    deck = build_pptx(
        [[chart_shape(6, "Scores")]],
        extra_slide_rels={1: [("rIdChart", REL_CHART, "../charts/chart1.xml")]},
        extra_entries={"ppt/charts/chart1.xml": b"<c:chartSpace/>"},
    )
    _, report = _render(themed_renderer, deck)
    scene = report.scene(0)
    svg = _svg(object_store, scene)

    assert scene.fidelity == "DEGRADED_RENDERED"
    assert "UNSUPPORTED_OBJECT:chart" in scene.warnings
    assert "not re-authored" in svg, "the teacher can see where the object was"
    assert scene.missing_fonts == ()


def test_a_picture_keeps_its_aspect_ratio(themed_renderer, object_store):
    deck = build_pptx(
        [[picture_shape(4, "Figure", rel_id="rIdImg")]],
        extra_slide_rels={1: [("rIdImg", REL_IMAGE, "../media/image1.png")]},
        extra_entries={"ppt/media/image1.png": _png(400, 100)},
    )
    _, report = _render(themed_renderer, deck)
    svg = _svg(object_store, report.scene(0))

    match = re.search(r'<image [^>]*width="([\d.]+)" height="([\d.]+)"', svg)
    assert match, svg[:300]
    width, height = float(match.group(1)), float(match.group(2))
    assert abs(width / height - 4.0) < 0.05, (width, height)


def test_an_unresolved_picture_is_a_labelled_placeholder_not_a_failure(
    themed_renderer, object_store
):
    # The slide declares no relationship for the picture: the extractor cannot
    # resolve it, so the renderer shows where it was instead of failing.
    deck = build_pptx([[picture_shape(4, "Figure", rel_id="rIdMissing")]])
    _, report = _render(themed_renderer, deck)
    scene = report.scene(0)
    svg = _svg(object_store, scene)

    assert scene.status is RenderStatus.RENDERED
    assert scene.fidelity == "THEMED_RENDERED"
    assert "<image" not in svg
    assert "Figure" in svg


def test_a_picture_whose_bytes_are_absent_warns_but_does_not_degrade(
    themed_renderer, object_store
):
    # The relationship resolves but the part is missing: a labelled placeholder
    # and a warning, not a failed slide (V0-018 media semantics, retained).
    deck = build_pptx(
        [[picture_shape(4, "Figure", rel_id="rIdImg")]],
        extra_slide_rels={1: [("rIdImg", REL_IMAGE, "../media/image1.png")]},
    )
    _, report = _render(themed_renderer, deck)
    scene = report.scene(0)

    assert scene.status is RenderStatus.RENDERED
    assert scene.fidelity == "THEMED_RENDERED"
    assert any(warning.startswith("MEDIA_UNAVAILABLE:") for warning in scene.warnings)


# -- classification ----------------------------------------------------------------
@pytest.mark.parametrize(
    "builder,expected",
    [
        (lambda: build_pptx([[text_shape(2, "T", text="Hello")]]), "title"),
        (
            lambda: build_pptx(
                [
                    [
                        text_shape(2, "T", text="Title", placeholder="title"),
                        text_shape(3, "B", paragraphs=[(0, "one"), (1, "two")]),
                    ]
                ]
            ),
            "bullets",
        ),
        (
            lambda: build_pptx(
                [
                    [
                        text_shape(2, "T", text="Title", placeholder="title"),
                        text_shape(3, "B", paragraphs=[(0, "plain prose")]),
                    ]
                ]
            ),
            "content",
        ),
        (
            lambda: build_pptx([[table_shape(5, "T", [["a", "b"]])]]),
            "table",
        ),
        (
            lambda: build_pptx(
                [[picture_shape(4, "P", rel_id="rIdImg")]],
                extra_slide_rels={1: [("rIdImg", REL_IMAGE, "../media/image1.png")]},
                extra_entries={"ppt/media/image1.png": _png(2, 2)},
            ),
            "media",
        ),
        (
            lambda: build_pptx(
                [
                    [
                        text_shape(2, "T", text="Title", placeholder="title"),
                        text_shape(3, "B", text="A caption"),
                        picture_shape(4, "P", rel_id="rIdImg"),
                    ]
                ],
                extra_slide_rels={1: [("rIdImg", REL_IMAGE, "../media/image1.png")]},
                extra_entries={"ppt/media/image1.png": _png(2, 2)},
            ),
            "mixed",
        ),
        (lambda: build_pptx([[text_shape(2, "T", text="")]]), "empty"),
    ],
)
def test_classification_is_deterministic(extractor, builder, expected):
    scene = extractor.extract(builder()).slides[0]

    assert classify_scene(scene) == expected
    assert classify_scene(scene) == expected, "pure: same IR, same archetype"
