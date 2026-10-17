"""V0-019: the themed renderer re-lays out the content and styles it.

This is the default mode, so these tests pin the contract that makes it safe to
default to:

* **the content is the author's** — every paragraph, list level, table cell and
  picture survives the re-layout; nothing is silently dropped or truncated;
* **the grouping is the author's** — the source rows and columns are recovered, so
  an icon stays on the row of its own label and a card keeps its parts;
* **the layout is the platform's** — each cell flows in reading order, heading
  hoisted, page number in its own reserved strip, and *no two drawn texts overlap*
  even when the source frames do (asserted over the produced SVG, not argued);
* **the look is the platform's** — its type stack, its type scale, its palette,
  its chrome; no source typeface, colour, fill or geometry is reproduced;
* **the font problem is gone** — an unavailable source font can no longer degrade
  a themed scene;
* **degradation is explicit** — a chart/SmartArt panel and a
  ``TEXT_OVERFLOW:`` both pull the scene into review.
"""

from __future__ import annotations

import re
import struct
import zlib
from html import unescape

import pytest

from app.compiler.extractors.pptx import PptxExtractor
from app.compiler.media import document_media_refs, read_media_parts
from app.compiler.renderers import flow
from app.compiler.renderers.base import (
    RenderBudget,
    RenderConfig,
    RenderRequest,
    RenderStatus,
)
from app.compiler.renderers.mentora_theme import DEFAULT_THEME
from app.compiler.renderers.textmetrics import measure
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

CANVAS_WIDTH = 1280.0
CANVAS_HEIGHT = 720.0
CONTENT_LEFT = _THEME.margin_px
CONTENT_RIGHT = CANVAS_WIDTH - _THEME.margin_px
CONTENT_BOTTOM = CANVAS_HEIGHT - _THEME.bottom_zone_px


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
_TAG = re.compile(r"<[^>]+>")


def _texts(svg: str) -> list[dict[str, str]]:
    """Every drawn ``<text>`` with its attributes and (unescaped) content."""

    found = []
    for raw, content in _TEXT.findall(svg):
        attrs = dict(_ATTR.findall(raw))
        attrs["content"] = unescape(_TAG.sub("", content))
        found.append(attrs)
    return found


def _label(svg: str, content: str) -> dict[str, str]:
    return next(text for text in _texts(svg) if text["content"] == content)


def _drawn_boxes(svg: str) -> list[tuple[float, float, float, float, str]]:
    """Estimate every drawn text's line box, to assert the render has no collisions."""

    boxes = []
    for attrs in _texts(svg):
        content = attrs["content"]
        size = float(attrs.get("font-size") or 0.0)
        x = float(attrs.get("x") or 0.0)
        bold = attrs.get("font-weight") == "bold"
        width = measure(content, size, bold=bold)
        anchor = attrs.get("text-anchor", "start")
        if anchor == "end":
            left = x - width
        elif anchor == "middle":
            left = x - width / 2
        else:
            left = x
        top = float(attrs["y"]) - size * 0.82
        boxes.append((left, top, left + width, top + size * _THEME.line_spacing, content))
    return boxes


def _assert_no_overlap(svg: str) -> None:
    boxes = _drawn_boxes(svg)
    for index, first in enumerate(boxes):
        for second in boxes[index + 1 :]:
            overlap_x = min(first[2], second[2]) - max(first[0], second[0])
            overlap_y = min(first[3], second[3]) - max(first[1], second[1])
            assert not (overlap_x > 0.5 and overlap_y > 0.5), (
                f"{first[4]!r} overlaps {second[4]!r}: {first} {second}"
            )


def _png(width: int, height: int) -> bytes:
    """A valid minimal PNG of a known size (so the aspect can be read from it)."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        payload = tag + data
        return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x00\x00\x00" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


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
    assert any("re-laid out" in reason for reason in support.reasons)


def test_the_theme_is_bound_into_the_renderer_identity(object_store):
    """A theme change alters every slide, so it must change the config hash."""

    plain = ThemedSvgRenderer(object_store, RenderConfig())
    restyled = ThemedSvgRenderer(
        object_store, RenderConfig(), theme=_THEME.with_version("9.9.9")
    )

    assert plain.identity().config_hash != restyled.identity().config_hash
    assert plain.theme_identity() == {"name": "mentora-default", "version": "4.0.0"}


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


# -- the layout is the platform's (the collision fix) ------------------------------
def test_overlapping_source_frames_are_re_laid_out_without_overlap(
    themed_renderer, object_store
):
    """Three frames stacked on the origin: the platform re-flows them instead.

    This is the failure the re-layout exists to fix — copying the author's
    geometry onto the platform's typeface reproduced the collision.
    """

    deck = themed_pptx(
        [
            text_shape(2, "A", text="First block", x=0, y=0, cx=914400, cy=914400),
            text_shape(3, "B", text="Second block", x=0, y=0, cx=914400, cy=914400),
            text_shape(4, "C", text="Third block", x=0, y=0, cx=914400, cy=914400),
        ]
    )
    _, report = _render(themed_renderer, deck)
    svg = _svg(object_store, report.scene(0))

    for content in ("First block", "Second block", "Third block"):
        assert content in svg
    baselines = [float(_label(svg, text)["y"]) for text in ("First block", "Second block", "Third block")]
    assert baselines == sorted(baselines)
    assert baselines[0] != baselines[1] != baselines[2], "no two blocks share a line"
    _assert_no_overlap(svg)


def test_every_drawn_text_stays_inside_the_page_margins(themed_renderer, object_store):
    deck = themed_pptx(
        [
            text_shape(2, "Kicker", text="KHOA QUẢN TRỊ"),
            text_shape(3, "Title", text="BÁO CÁO TỔNG KẾT", placeholder="title"),
            text_shape(4, "Body", paragraphs=[(0, text) for text in ("Một dòng", "Hai dòng", "Ba dòng")]),
        ]
    )
    _, report = _render(themed_renderer, deck)
    svg = _svg(object_store, report.scene(0))

    _assert_no_overlap(svg)
    for left, _, right, _, content in _drawn_boxes(svg):
        assert left >= CONTENT_LEFT - 1, (content, left)
        assert right <= CONTENT_RIGHT + 1, (content, right)
    for text in _texts(svg):
        assert CONTENT_LEFT <= float(text["y"]) <= CANVAS_HEIGHT, text["content"]
    # Body content never enters the reserved footer strip (the page number does).
    for _, _, _, bottom, content in _drawn_boxes(svg):
        if content != "1":
            assert bottom <= CONTENT_BOTTOM + 1, content


def test_the_page_number_sits_in_its_own_reserved_strip(themed_renderer, object_store):
    deck = themed_pptx(
        [text_shape(2, "Title", text="Báo cáo", placeholder="title"),
         text_shape(3, "Body", text="Nội dung chính")],
    )
    _, report = _render(themed_renderer, deck)
    svg = _svg(object_store, report.scene(0))

    page_number = _label(svg, "1")
    assert page_number["text-anchor"] == "end"
    assert float(page_number["x"]) == pytest.approx(CONTENT_RIGHT)
    assert float(page_number["y"]) == pytest.approx(CANVAS_HEIGHT - _THEME.footer_from_bottom_px)
    # Nothing else is placed in that strip.
    for _, _, _, bottom, content in _drawn_boxes(svg):
        if content != "1":
            assert bottom <= CONTENT_BOTTOM + 1, content


def test_a_designed_slide_becomes_a_heading_and_a_body(themed_renderer, object_store):
    """Kicker, title and subtitle are hoisted; the rest of the content follows."""

    deck = themed_pptx(
        [
            text_shape(2, "Kicker", text="KHOA QUẢN TRỊ"),
            text_shape(3, "Title", text="BÁO CÁO TỔNG KẾT", placeholder="title"),
            text_shape(4, "Subtitle", text="Hải Phòng và các tỉnh lân cận"),
            text_shape(5, "Body", paragraphs=[(0, "Số liệu"), (0, "Kết luận")]),
        ]
    )
    _, report = _render(themed_renderer, deck)
    scene = report.scene(0)
    svg = _svg(object_store, scene)

    assert scene.fidelity == "THEMED_RENDERED"
    kicker = _label(svg, "KHOA QUẢN TRỊ")
    title = _label(svg, "BÁO CÁO TỔNG KẾT")
    subtitle = _label(svg, "Hải Phòng và các tỉnh lân cận")
    # Reading order down the column, at the theme's sizes and inks.
    assert float(kicker["y"]) < float(title["y"]) < float(subtitle["y"])
    assert float(title["font-size"]) == pytest.approx(_THEME.title_px)
    assert float(kicker["font-size"]) == pytest.approx(_THEME.kicker_px)
    assert title["fill"] == _THEME.primary and title.get("font-weight") == "bold"
    assert kicker["fill"] == _THEME.muted
    assert subtitle["fill"] == _THEME.muted
    assert "<line " in svg, "the heading is separated by a hairline rule"
    _assert_no_overlap(svg)


# -- the look is the platform's ----------------------------------------------------
def test_the_theme_type_scale_replaces_the_authors(themed_renderer, object_store):
    deck = themed_pptx(
        [
            shape_xml(
                2,
                "Heading",
                placeholder="title",
                tx_body=paragraph_xml(
                    "Big heading", r_pr='<a:latin typeface="Be Vietnam Pro"/>'
                ),
            )
        ]
    )
    _, report = _render(themed_renderer, deck)
    svg = _svg(object_store, report.scene(0))
    text = _label(svg, "Big heading")

    # The master's title style is 40 pt (53.33 px); the platform draws its own scale.
    assert float(text["font-size"]) == pytest.approx(_THEME.title_px)
    assert float(text["font-size"]) != pytest.approx(40.0 * 96.0 / 72.0)
    assert text.get("font-weight") == "bold"
    assert THEME_FONT_MARKER in text["font-family"]
    assert "Be Vietnam Pro" not in svg


def test_the_render_draws_the_theme_palette_and_page_number(themed_renderer, object_store):
    deck = themed_pptx(
        [
            text_shape(2, "Title", text="Báo cáo", placeholder="title"),
            text_shape(3, "Body", paragraphs=[(0, "Số liệu"), (0, "Kết luận")]),
        ]
    )
    _, report = _render(themed_renderer, deck)
    svg = _svg(object_store, report.scene(0))

    assert THEME_FONT_MARKER in svg, "the theme's own font stack is used"
    assert (
        f'<rect x="0" y="0" width="{CANVAS_WIDTH:g}" height="{CANVAS_HEIGHT:g}" '
        f'fill="{_THEME.background}"' in svg
    )
    assert _label(svg, "Báo cáo")["fill"] == _THEME.primary, "headings take the brand ink"
    assert _label(svg, "Số liệu")["fill"] == _THEME.ink, "body text takes the ink"
    assert _label(svg, "1")["text-anchor"] == "end"


def test_no_source_colour_or_geometry_is_reproduced(themed_renderer, object_store):
    """Every painted colour is the theme's: the author's palette is not copied."""

    background = (
        '<p:bg><p:bgPr><a:solidFill><a:srgbClr val="0B1F3A"/></a:solidFill></p:bgPr></p:bg>'
    )
    deck = themed_pptx(
        [
            shape_xml(
                2,
                "Banner",
                sp_pr=xfrm(914400, 914400, 4572000, 914400)
                + '<a:solidFill><a:srgbClr val="FF00AA"/></a:solidFill>',
                tx_body=paragraph_xml(
                    "Hello",
                    r_pr=(
                        '<a:solidFill><a:srgbClr val="FDFDFD"/></a:solidFill>'
                        '<a:highlight><a:srgbClr val="FFFF00"/></a:highlight>'
                    ),
                )
                + paragraph_xml("World"),
            ),
            text_shape(3, "Title", text="Banner section", placeholder="title"),
        ],
        background=background,
    )
    _, report = _render(themed_renderer, deck)
    svg = _svg(object_store, report.scene(0))

    for source_colour in ("0B1F3A", "FF00AA", "FDFDFD", "FFFF00"):
        assert source_colour not in svg, source_colour
    assert _label(svg, "Hello")["fill"] == _THEME.ink


def test_a_decorative_shape_without_text_is_dropped(themed_renderer, object_store):
    """A bar/rule/logo is not content: the theme draws its own chrome."""

    deck = themed_pptx(
        [
            shape_xml(
                2,
                "Bar",
                sp_pr=xfrm(0, 0, 9144000, 91440)
                + '<a:solidFill><a:srgbClr val="FF00AA"/></a:solidFill>',
            )
        ]
    )
    _, report = _render(themed_renderer, deck)
    scene = report.scene(0)
    svg = _svg(object_store, scene)

    assert scene.fidelity == "THEMED_RENDERED"
    assert "FF00AA" not in svg
    assert svg.count("<rect") == 1, "only the theme background is painted"
    assert "<line " not in svg, "no heading means no rule"


# -- content survives the re-flow --------------------------------------------------
def test_emphasis_list_levels_and_tables_survive(themed_renderer, object_store):
    deck = themed_pptx(
        [
            text_shape(2, "Title", text="Results", placeholder="title"),
            shape_xml(
                3,
                "Body",
                tx_body=paragraph_xml("Plain ")
                + paragraph_xml("", r_pr="", p_pr="<a:buNone/>")
                + paragraph_xml("Bold bit", r_pr_attrs=' b="1"')
                + paragraph_xml("Nested", level=1),
            ),
            table_shape(5, "Table", [["Model", "BLEU"], ["Baseline", "24.1"]],
                        x=838200, y=1825625, cx=10515600, cy=914400),
        ]
    )
    _, report = _render(themed_renderer, deck)
    scene = report.scene(0)
    svg = _svg(object_store, scene)

    assert scene.fidelity == "THEMED_RENDERED"
    for content in ("Plain", "Bold bit", "Nested", "Model", "BLEU", "Baseline", "24.1"):
        assert content in svg, content
    assert _label(svg, "Bold bit").get("font-weight") == "bold"
    # List paragraphs get the theme's marker; a nested level is indented.
    assert "•" in svg
    assert float(_label(svg, "Nested")["x"]) > float(_label(svg, "Plain")["x"])
    _assert_no_overlap(svg)


def test_a_table_is_drawn_without_a_grid(themed_renderer, object_store):
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
    svg = _svg(object_store, report.scene(0))

    # Header band and row bands, and no cell borders at all.
    assert f'fill="{_THEME.surface_alt}"' in svg
    assert f'fill="{_THEME.surface}"' in svg
    assert re.findall(r"<rect[^>]*stroke", svg) == [], "table cells are not outlined"
    # Numbers are aligned by their digits, text by its letters.
    assert _label(svg, "24.1")["text-anchor"] == "end"
    assert _label(svg, "Baseline").get("text-anchor", "start") == "start"


def test_a_picture_is_re_framed_from_its_own_bytes(themed_renderer, object_store):
    """The picture's own aspect drives its frame — not the author's box."""

    deck = themed_pptx(
        [picture_shape(4, "Figure", rel_id="rIdImg")], image=_png(200, 100)
    )
    _, report = _render(themed_renderer, deck)
    scene = report.scene(0)
    svg = _svg(object_store, scene)

    assert scene.fidelity == "THEMED_RENDERED"
    image = re.search(r'<image ([^>]*)/?>', svg)
    assert image is not None
    attrs = dict(_ATTR.findall(image.group(1)))
    width, height = float(attrs["width"]), float(attrs["height"])
    assert width / height == pytest.approx(2.0, rel=1e-3)
    assert float(attrs["x"]) >= CONTENT_LEFT - 1
    assert float(attrs["y"]) + height <= CONTENT_BOTTOM + 1


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
    assert "chart: Scores" in svg, "the teacher can see what the panel stands for"
    assert scene.missing_fonts == ()


def test_content_that_does_not_fit_is_flagged_not_truncated(themed_renderer, object_store):
    deck = themed_pptx(
        [
            text_shape(2, "Title", text="Dense", placeholder="title"),
            text_shape(
                3,
                "Body",
                paragraphs=[(0, f"Paragraph {index} of the slide body") for index in range(200)],
            ),
        ]
    )
    _, report = _render(themed_renderer, deck)
    scene = report.scene(0)
    svg = _svg(object_store, scene)

    assert scene.fidelity == "DEGRADED_RENDERED"
    assert f"{TEXT_OVERFLOW_PREFIX}ppt/slides/slide1.xml" in scene.warnings
    # Everything is still placed — the last paragraph is drawn, just unreachable.
    assert "Paragraph 199 of the slide body" in svg
    assert len(_texts(svg)) >= 200
    # The page number is omitted rather than painted over the spilled content.
    assert "text-anchor=\"end\"" not in svg


def test_an_unresolved_picture_is_a_labelled_panel_not_a_failure(
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
    # The relationship resolves but the part is missing: a labelled panel and a
    # warning, not a failed slide (V0-018 media semantics, retained).
    deck = build_pptx(
        [[picture_shape(4, "Figure", rel_id="rIdImg")]],
        extra_slide_rels={1: [("rIdImg", REL_IMAGE, "../media/image1.png")]},
    )
    _, report = _render(themed_renderer, deck)
    scene = report.scene(0)

    assert scene.status is RenderStatus.RENDERED
    assert scene.fidelity == "THEMED_RENDERED"
    assert any(warning.startswith("MEDIA_UNAVAILABLE:") for warning in scene.warnings)


# -- the look is the platform's (continued) -----------------------------------------
def test_the_source_hierarchy_survives_as_the_theme_type_rows(themed_renderer, object_store):
    """A 40 pt statistic, an 18 pt line and a 12 pt note stay three distinct rows.

    The theme owns the sizes, but a slide that says something big and something
    small must still read that way — the source only chooses the *row*.
    """

    deck = themed_pptx(
        [
            text_shape(2, "Title", text="BÁO CÁO", placeholder="title"),
            shape_xml(3, "Stat", tx_body=paragraph_xml("59", r_pr_attrs=' sz="4000"')),
            shape_xml(4, "Body", tx_body=paragraph_xml("Tổng số CBGV và NLĐ", r_pr_attrs=' sz="1800"')),
            shape_xml(5, "Note", tx_body=paragraph_xml("Nguồn: Phòng TC-HC", r_pr_attrs=' sz="1200"')),
        ]
    )
    _, report = _render(themed_renderer, deck)
    scene = report.scene(0)
    svg = _svg(object_store, scene)

    assert scene.fidelity == "THEMED_RENDERED"
    lead = float(_label(svg, "59")["font-size"])
    body = float(_label(svg, "Tổng số CBGV và NLĐ")["font-size"])
    caption = float(_label(svg, "Nguồn: Phòng TC-HC")["font-size"])

    assert lead == pytest.approx(_THEME.body_px * _THEME.lead_scale)
    assert body == pytest.approx(_THEME.body_px * _THEME.body_scale)
    assert caption == pytest.approx(_THEME.body_px * _THEME.caption_scale)
    assert lead > body > caption
    assert _label(svg, "59")["fill"] == _THEME.ink
    assert _label(svg, "Nguồn: Phòng TC-HC")["fill"] == _THEME.muted, "a note is not the body ink"
    _assert_no_overlap(svg)


def test_a_picture_only_slide_may_use_the_whole_body(themed_renderer, object_store):
    only = _render(
        themed_renderer,
        themed_pptx([picture_shape(4, "Figure", rel_id="rIdImg")], image=_png(200, 100)),
    )[1]
    mixed = _render(
        themed_renderer,
        themed_pptx(
            [
                text_shape(2, "Title", text="Báo cáo", placeholder="title"),
                text_shape(3, "Body", paragraphs=[(0, "Một dòng"), (0, "Hai dòng")]),
                picture_shape(5, "Figure", rel_id="rIdOther"),
            ],
            image=_png(200, 100),
            extra_slide_rels={1: [("rIdOther", REL_IMAGE, "../media/image1.png")]},
        ),
    )[1]

    def frame(report):
        svg = _svg(object_store, report.scene(0))
        match = re.search(r"<image ([^>]*)/?>", svg)
        assert match is not None
        attrs = dict(_ATTR.findall(match.group(1)))
        return {key: float(attrs[key]) for key in ("x", "y", "width", "height")}

    alone = frame(only)
    assert alone["width"] / alone["height"] == pytest.approx(2.0, rel=1e-3)
    assert alone["height"] == pytest.approx(CANVAS_HEIGHT - _THEME.bottom_zone_px - _THEME.margin_px, rel=1e-2)
    assert alone["height"] > frame(mixed)["height"], "a mixed slide keeps pictures to their share"


def test_an_empty_slide_is_just_the_theme_background(themed_renderer, object_store):
    _, report = _render(themed_renderer, build_pptx([[]]))
    scene = report.scene(0)
    svg = _svg(object_store, scene)

    assert scene.fidelity == "THEMED_RENDERED"
    assert svg.count("<rect") == 1


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


# -- grouping: the author's rows and columns survive the re-layout -----------------
#: Slide 21 of the real deck is a card grid: each card is a badge beside its title,
#: then an icon beside its label. Flattening that into one column put every icon on
#: its own line, which reads as nonsense; these tests pin the recovered grouping.
_EMU = 9525


def _px(value: float) -> int:
    return int(round(value * _EMU))


def _picture(shape_id: int, name: str, *, x: float, y: float, size: float, rel_id: str) -> str:
    return (
        f'<p:pic><p:nvPicPr><p:cNvPr id="{shape_id}" name="{name}"/>'
        f"<p:cNvPicPr/><p:nvPr/></p:nvPicPr>"
        f'<p:blipFill><a:blip r:embed="{rel_id}"/></p:blipFill>'
        f'<p:spPr><a:xfrm><a:off x="{_px(x)}" y="{_px(y)}"/>'
        f'<a:ext cx="{_px(size)}" cy="{_px(size)}"/></a:xfrm></p:spPr></p:pic>'
    )


def _card_grid() -> bytes:
    return themed_pptx(
        [
            text_shape(
                2,
                "Title",
                text="Kết quả đạt được",
                placeholder="title",
                x=_px(56),
                y=_px(40),
                cx=_px(1168),
                cy=_px(60),
            ),
            _picture(3, "Badge A", x=60, y=200, size=24, rel_id="rIdImg"),
            text_shape(4, "Label A", text="Đào tạo", x=_px(95), y=_px(196), cx=_px(200), cy=_px(40)),
            _picture(5, "Icon A", x=60, y=250, size=21, rel_id="rIdImg"),
            text_shape(
                6, "Body A", text="Mở ngành đào tạo thạc sĩ", x=_px(90), y=_px(250), cx=_px(250), cy=_px(80)
            ),
            _picture(7, "Badge B", x=500, y=200, size=24, rel_id="rIdImg"),
            text_shape(
                8, "Label B", text="Nghiên cứu", x=_px(535), y=_px(196), cx=_px(200), cy=_px(40)
            ),
            _picture(9, "Icon B", x=500, y=250, size=21, rel_id="rIdImg"),
            text_shape(
                10,
                "Body B",
                text="Thực hiện đề tài cấp trường",
                x=_px(530),
                y=_px(250),
                cx=_px(250),
                cy=_px(80),
            ),
        ],
        image=_png(8, 8),
    )


def _layout_of(renderer, data: bytes):
    document = PptxExtractor().extract(data)
    media = read_media_parts(data, document_media_refs(document))
    scene = document.slides[0]
    header, body = renderer._content(scene, media)
    return flow.layout(
        body=body, header=header, theme=renderer.theme, width=CANVAS_WIDTH, height=CANVAS_HEIGHT
    )


def test_every_icon_is_placed_on_the_row_of_its_own_label(themed_renderer):
    result = _layout_of(themed_renderer, _card_grid())

    icons = [item for item in result.items if isinstance(item, flow.PlacedPicture)]
    labels = [item for item in result.items if isinstance(item, flow.PlacedText)]

    assert len(icons) == 4, "the cards' four pictures are still all drawn"
    for icon in icons:
        same_row = [
            label
            for label in labels
            if label.box.x >= icon.box.right
            and min(icon.box.bottom, label.box.bottom) - max(icon.box.y, label.box.y) > 2.0
        ]
        assert same_row, f"{icon.box} has no label beside it"


def test_a_card_grid_is_drawn_as_surface_panels_without_borders(themed_renderer, object_store):
    _, report = _render(themed_renderer, _card_grid())
    svg = _svg(object_store, report.scene(0))

    assert svg.count(f'fill="{_THEME.surface}"') == 2, "one flat fill per card cell"
    assert re.findall(r"<rect[^>]*stroke", svg) == [], "a card panel is a fill, never a border"


def test_a_plain_list_slide_stays_one_column(themed_renderer, object_store):
    """A full-width object spans the region, so no column can be cut through it."""

    deck = themed_pptx(
        [
            text_shape(2, "Title", text="Hạn chế", placeholder="title"),
            text_shape(3, "One", text="Chỉ tiêu thứ nhất", x=_px(56), y=_px(200), cx=_px(1168), cy=_px(40)),
            text_shape(4, "Two", text="Chỉ tiêu thứ hai", x=_px(56), y=_px(250), cx=_px(1168), cy=_px(40)),
            text_shape(5, "Three", text="Chỉ tiêu thứ ba", x=_px(56), y=_px(300), cx=_px(1168), cy=_px(40)),
        ]
    )
    _, report = _render(themed_renderer, deck)
    svg = _svg(object_store, report.scene(0))
    result = _layout_of(themed_renderer, deck)

    assert result.surfaces == (), "an ungrouped slide has no card panels"
    lists = [
        [line.text for line in item.lines]
        for item in result.items
        if isinstance(item, flow.PlacedText)
    ]
    assert ["Chỉ tiêu thứ hai", "Chỉ tiêu thứ ba"] in lists, (
        "consecutive same-emphasis lines stay one list"
    )
    for text in ("Chỉ tiêu thứ nhất", "Chỉ tiêu thứ hai", "Chỉ tiêu thứ ba"):
        assert text in svg


def test_grouping_never_drops_a_fragment(themed_renderer, object_store):
    _, report = _render(themed_renderer, _card_grid())
    svg = _svg(object_store, report.scene(0))

    for fragment in (
        "Kết quả đạt được",
        "Đào tạo",
        "Mở ngành đào tạo thạc sĩ",
        "Nghiên cứu",
        "Thực hiện đề tài cấp trường",
    ):
        assert fragment in svg
    _assert_no_overlap(svg)
    for box in _drawn_boxes(svg):
        assert box[0] >= CONTENT_LEFT - 0.5 and box[2] <= CONTENT_RIGHT + 0.5, box
