"""V0-019: the themed renderer keeps the author's layout and restyles it.

These tests pin the contract that makes themed mode the default:

* **layout is the author's** — every object is drawn inside the source box, which
  is what makes a dense, art-directed slide collision-free (this renderer began
  as a re-flow, and a re-flow cannot avoid guessing text metrics; the guesses
  collided on real decks);
* **the styling is the platform's** — one typeface stack, one palette, and
  platform chrome, with source colours mapped by role so a light-on-dark pair
  stays light-on-dark (re-colouring must not hide text);
* **the platform's chrome never paints over content** — the accent band and the
  footer are drawn only where the author left the strip empty;
* **completeness is the gate** — nothing is re-selected, so the only alarm left
  is ``TEXT_OVERFLOW:``, which degrades the scene for review instead of clipping
  in silence;
* **degradation is explicit** — a chart is a labelled placeholder plus review.
"""

from __future__ import annotations

import re

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
from app.compiler.renderers.structural import EMU_PER_PIXEL
from app.compiler.renderers.themed import TEXT_OVERFLOW_PREFIX, ThemedSvgRenderer
from tests.fixtures import (
    REL_CHART,
    REL_IMAGE,
    build_pptx,
    chart_shape,
    paragraph_xml,
    picture_shape,
    shape_xml,
    table_shape,
    text_shape,
    themed_pptx,
    xfrm,
)

THEME_FONT_MARKER = "Noto Sans, DejaVu Sans"
_THEME = DEFAULT_THEME

#: Canvas geometry used by the venue: the IR is EMU, the canvas is 1280x720 px.
CANVAS_WIDTH = 1280.0
CANVAS_HEIGHT = 720.0


# -- helpers -----------------------------------------------------------------------
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


_TEXT = re.compile(r"<text ([^>]*)>(.*?)</text>")
_ATTR = re.compile(r'([\w:-]+)="([^"]*)"')


def _texts(svg: str) -> list[dict[str, str]]:
    """Every drawn ``<text>`` with its attributes and content."""

    found = []
    for raw, content in _TEXT.findall(svg):
        attrs = dict(_ATTR.findall(raw))
        attrs["content"] = content
        found.append(attrs)
    return found


def _box_px(x: int, y: int, cx: int, cy: int) -> tuple[float, float, float, float]:
    return (
        x / EMU_PER_PIXEL,
        y / EMU_PER_PIXEL,
        (x + cx) / EMU_PER_PIXEL,
        (y + cy) / EMU_PER_PIXEL,
    )


def _assert_texts_inside_their_own_box(svg: str, boxes: dict[str, tuple[int, int, int, int]]) -> None:
    """Every labelled text is drawn inside the author's box for that text."""

    drawn = {t["content"]: t for t in _texts(svg) if t["content"] in boxes}
    assert set(drawn) == set(boxes), f"missing text: {set(boxes) - set(drawn)}"
    for content, (x, y, cx, cy) in boxes.items():
        left, top, right, bottom = _box_px(x, y, cx, cy)
        text = drawn[content]
        assert left - 1 <= float(text["x"]) <= right + 1, (content, text)
        assert top - 1 <= float(text["y"]) <= bottom + 2, (content, text)


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
        object_store, RenderConfig(), theme=_THEME.with_version("9.9.9")
    )

    assert plain.identity().config_hash != restyled.identity().config_hash
    assert plain.theme_identity() == {"name": "mentora-default", "version": "1.1.0"}


def test_a_themed_scene_never_reports_a_missing_font(themed_renderer, object_store):
    _, report = _render(
        themed_renderer,
        build_pptx([[text_shape(2, "T", text="Brand", font="Be Vietnam Pro")]]),
    )
    scene = report.scene(0)
    svg = _svg(object_store, scene)

    assert scene.status is RenderStatus.RENDERED
    assert scene.fidelity == "THEMED_RENDERED"
    assert scene.missing_fonts == ()
    assert scene.warnings == ()
    # The theme's stack is reported and drawn; the source typeface is gone.
    assert scene.fonts_used == tuple(sorted(_THEME.available_fonts))
    assert "Be Vietnam Pro" not in svg


# -- the layout is the author's (the collision fix) --------------------------------
def test_text_is_drawn_inside_its_own_source_box(themed_renderer, object_store):
    """Author geometry is authoritative: a re-flow could not promise this."""

    boxes = {
        "First": (914400, 914400, 2743200, 457200),
        "Second": (914400, 2743200, 2743200, 457200),
        "Third": (914400, 4572000, 2743200, 457200),
    }
    deck = build_pptx(
        [
            [
                text_shape(2, "A", text="First", x=boxes["First"][0], y=boxes["First"][1],
                          cx=boxes["First"][2], cy=boxes["First"][3]),
                text_shape(3, "B", text="Second", x=boxes["Second"][0], y=boxes["Second"][1],
                          cx=boxes["Second"][2], cy=boxes["Second"][3]),
                text_shape(4, "C", text="Third", x=boxes["Third"][0], y=boxes["Third"][1],
                          cx=boxes["Third"][2], cy=boxes["Third"][3]),
            ]
        ]
    )
    _, report = _render(themed_renderer, deck)
    svg = _svg(object_store, report.scene(0))

    _assert_texts_inside_their_own_box(svg, boxes)
    # The three bands stay separate, in the author's order.
    ys = {t["content"]: float(t["y"]) for t in _texts(svg) if t["content"] in boxes}
    assert ys["First"] < ys["Second"] < ys["Third"]


def test_a_designed_slide_is_not_re_flowed(themed_renderer, object_store):
    """A real title slide: kicker, title, subtitle, rule and date, each in place."""

    boxes = {
        "KHOA QUẢN TRỊ": (812800, 1783755, 8110220, 274307),
        "BÁO CÁO TỔNG KẾT": (716279, 2261262, 9267613, 1785541),
        "Hải Phòng": (1600200, 4825273, 4067334, 274307),
    }
    deck = themed_pptx(
        [
            text_shape(2, "Kicker", text="KHOA QUẢN TRỊ", x=boxes["KHOA QUẢN TRỊ"][0],
                       y=boxes["KHOA QUẢN TRỊ"][1], cx=boxes["KHOA QUẢN TRỊ"][2],
                       cy=boxes["KHOA QUẢN TRỊ"][3]),
            text_shape(3, "Title", text="BÁO CÁO TỔNG KẾT", x=boxes["BÁO CÁO TỔNG KẾT"][0],
                       y=boxes["BÁO CÁO TỔNG KẾT"][1], cx=boxes["BÁO CÁO TỔNG KẾT"][2],
                       cy=boxes["BÁO CÁO TỔNG KẾT"][3]),
            text_shape(4, "Date", text="Hải Phòng", x=boxes["Hải Phòng"][0],
                       y=boxes["Hải Phòng"][1], cx=boxes["Hải Phòng"][2],
                       cy=boxes["Hải Phòng"][3]),
        ]
    )
    _, report = _render(themed_renderer, deck)
    scene = report.scene(0)
    svg = _svg(object_store, scene)

    assert scene.fidelity == "THEMED_RENDERED"
    _assert_texts_inside_their_own_box(svg, boxes)


def test_a_picture_keeps_its_source_frame(themed_renderer, object_store):
    """No re-framing: the picture is drawn in the author's box, unstretched."""

    deck = themed_pptx([picture_shape(4, "Figure", rel_id="rIdImg")], image=b"\x89PNG\r\n\x1a\n")
    _, report = _render(themed_renderer, deck)
    svg = _svg(object_store, report.scene(0))

    # picture_shape is (0, 0, 914400, 914400) EMU -> 96 x 96 px at the origin.
    assert '<image x="0" y="0" width="96" height="96"' in svg


def test_the_authors_type_sizes_and_emphasis_are_kept(themed_renderer, object_store):
    """The theme owns the typeface, not the type scale: the author's fit stands."""

    deck = themed_pptx(
        [
            shape_xml(
                2,
                "Heading",
                placeholder="title",
                tx_body=paragraph_xml("Big heading", r_pr='<a:latin typeface="Be Vietnam Pro"/>'),
            )
        ]
    )
    _, report = _render(themed_renderer, deck)
    svg = _svg(object_store, report.scene(0))
    text = next(t for t in _texts(svg) if t["content"] == "Big heading")

    # The master's title style is 40 pt: 40 * 96/72 = 53.33 px, kept as-is.
    assert float(text["font-size"]) == pytest.approx(40.0 * 96.0 / 72.0, abs=0.01)
    assert text.get("font-weight") == "bold"
    assert THEME_FONT_MARKER in text["font-family"]
    assert "Be Vietnam Pro" not in svg


# -- the look is the platform's ----------------------------------------------------
def test_the_render_draws_the_theme_palette_and_footer(themed_renderer, object_store):
    _, report = _render(
        themed_renderer, build_pptx([[text_shape(2, "T", text="Hello world")]])
    )
    svg = _svg(object_store, report.scene(0))

    assert THEME_FONT_MARKER in svg, "the theme's own font stack is used"
    assert f'fill="{_THEME.background}"' in svg, "the theme background is the base fill"
    assert f'fill="{_THEME.ink}"' in svg, "dark source text maps to theme ink"
    assert _THEME.footer_label in svg, "the footer is drawn when the strip is free"
    assert 'text-anchor="end"' in svg, "the slide number is drawn on the right"


def test_a_source_background_colour_is_mapped_into_the_theme(themed_renderer, object_store):
    """A dark band stays dark, so white text on it stays readable."""

    background = (
        '<p:bg><p:bgPr><a:solidFill><a:srgbClr val="0B1F3A"/></a:solidFill>'
        "</p:bgPr></p:bg>"
    )
    _, report = _render(themed_renderer, themed_pptx([], background=background))
    svg = _svg(object_store, report.scene(0))

    assert "0B1F3A" not in svg, "the author's colour is not reproduced"
    assert (
        f'<rect x="0" y="0" width="{CANVAS_WIDTH:g}" height="{CANVAS_HEIGHT:g}" '
        f'fill="{_THEME.primary}"' in svg
    )
    # The footer sits on that dark band, so it takes the on-primary ink.
    assert f'fill="{_THEME.primary_ink}"' in svg


def test_light_text_on_a_dark_fill_stays_light(themed_renderer, object_store):
    deck = themed_pptx(
        [
            shape_xml(
                2,
                "Banner",
                sp_pr=xfrm(914400, 914400, 4572000, 914400)
                + '<a:solidFill><a:srgbClr val="0B1F3A"/></a:solidFill>',
                tx_body=paragraph_xml(
                    "Hello", r_pr='<a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill>'
                ),
            )
        ]
    )
    _, report = _render(themed_renderer, deck)
    svg = _svg(object_store, report.scene(0))
    text = next(t for t in _texts(svg) if t["content"] == "Hello")

    assert "0B1F3A" not in svg
    assert f'fill="{_THEME.primary}"' in svg, "the dark fill becomes the theme's dark band"
    assert text["fill"] == _THEME.primary_ink, "the light text stays light"


def test_a_source_highlight_is_retinted(themed_renderer, object_store):
    deck = themed_pptx(
        [
            shape_xml(
                2,
                "Note",
                tx_body=paragraph_xml(
                    "Marked", r_pr='<a:highlight><a:srgbClr val="FFFF00"/></a:highlight>'
                ),
            )
        ]
    )
    _, report = _render(themed_renderer, deck)
    svg = _svg(object_store, report.scene(0))

    assert "FFFF00" not in svg
    assert f'fill="{_THEME.highlight}"' in svg


# -- chrome never paints over content ---------------------------------------------
def test_the_accent_bar_is_drawn_when_the_top_strip_is_free(themed_renderer, object_store):
    deck = build_pptx([[text_shape(2, "T", text="Lower", x=0, y=914400, cx=4572000, cy=457200)]])
    _, report = _render(themed_renderer, deck)
    svg = _svg(object_store, report.scene(0))

    assert (
        f'<rect x="0" y="0" width="{CANVAS_WIDTH:g}" height="{_THEME.accent_bar_px:g}" '
        f'fill="{_THEME.primary}"' in svg
    )


def test_the_accent_bar_is_skipped_when_an_object_occupies_it(themed_renderer, object_store):
    deck = build_pptx([[text_shape(2, "T", text="Top", x=0, y=0, cx=4572000, cy=457200)]])
    _, report = _render(themed_renderer, deck)
    svg = _svg(object_store, report.scene(0))

    assert f'height="{_THEME.accent_bar_px:g}"' not in svg


def test_the_footer_is_skipped_when_the_author_uses_the_bottom_strip(
    themed_renderer, object_store
):
    # 640 px down, 40 px tall: the box reaches into the footer strip.
    deck = build_pptx([[text_shape(2, "T", text="Footerless", y=6096000, cx=4572000, cy=381000)]])
    _, report = _render(themed_renderer, deck)
    svg = _svg(object_store, report.scene(0))

    assert "Footerless" in svg
    assert _THEME.footer_label not in svg


# -- completeness and degradation --------------------------------------------------
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
    assert "chart: Scores" in svg, "the teacher can see where the object was"
    assert scene.missing_fonts == ()


def test_overflow_degrades_the_scene_and_is_never_truncated(themed_renderer, object_store):
    """A ``noAutofit`` frame that cannot hold its text spills, it does not clip."""

    long_text = " ".join(f"word{index}" for index in range(20))  # ~3 lines in the frame
    deck = themed_pptx(
        [
            shape_xml(
                2,
                "Tight",
                sp_pr=xfrm(0, 0, 4572000, 457200),
                tx_body=(
                    '<a:bodyPr wrap="square" lIns="0" tIns="0" rIns="0" bIns="0" anchor="t">'
                    "<a:noAutofit/></a:bodyPr>" + paragraph_xml(long_text)
                ),
            )
        ]
    )
    _, report = _render(themed_renderer, deck)
    scene = report.scene(0)
    svg = _svg(object_store, scene)

    assert scene.fidelity == "DEGRADED_RENDERED"
    assert f"{TEXT_OVERFLOW_PREFIX}ppt/slides/slide1.xml#2" in scene.warnings
    # Every paragraph is placed: the last word of the text is on the slide.
    assert "word19" in svg
    assert len(_texts(svg)) >= 3, "all the lines are drawn past the frame"


def test_a_table_keeps_its_frame_and_is_themed(themed_renderer, object_store):
    deck = build_pptx(
        [
            [
                text_shape(2, "Title", text="Results", placeholder="title"),
                table_shape(5, "Results table", [["Model", "BLEU"], ["Baseline", "24.1"]],
                            x=838200, y=1825625, cx=10515600, cy=914400),
            ]
        ]
    )
    _, report = _render(themed_renderer, deck)
    scene = report.scene(0)
    svg = _svg(object_store, scene)

    assert scene.fidelity == "THEMED_RENDERED"
    for cell in ("Model", "BLEU", "Baseline", "24.1"):
        assert cell in svg, cell


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
