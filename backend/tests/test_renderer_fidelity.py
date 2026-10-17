"""V0-018: the local renderer must reproduce the extracted look, not a sketch.

These tests render real decks (theme + master + layout + shapes) and assert on the
produced SVG. They are deliberately *structural*: an SVG element with the right
colour, size, position, or inline image proves the style survived the pipeline,
without pinning the whole document byte-for-byte.
"""

from __future__ import annotations

from app.compiler.extractors.pptx import PptxExtractor
from app.compiler.media import document_media_refs, read_media_parts
from app.compiler.renderers.base import (
    RenderBudget,
    RenderConfig,
    RenderRequest,
    RenderStatus,
)
from app.compiler.renderers.structural import StructuralSvgRenderer
from tests.fixtures import (
    REL_IMAGE,
    REL_SLIDE_MASTER,
    TINY_PNG,
    _rels_xml,
    paragraph_xml,
    shape_xml,
    slide_layout_xml,
    text_shape,
    themed_pptx,
    xfrm,
)

RECT = '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
ROUND_RECT = '<a:prstGeom prst="roundRect"><a:avLst/></a:prstGeom>'

#: A slide exercising theme colour, inherited master font/size, rotation, a
#: line-less shape, and a picture.
def styled_deck(*, max_inline_media_bytes: int | None = None) -> bytes:
    picture = (
        '<p:pic><p:nvPicPr><p:cNvPr id="6" name="Photo"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>'
        '<p:blipFill><a:blip r:embed="rIdImg"/>'
        '<a:srcRect l="10000" t="25000" r="5000" b="15000"/></p:blipFill>'
        '<p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="914400" cy="457200"/></a:xfrm>'
        "</p:spPr></p:pic>"
    )
    shapes = [
        shape_xml(
            2,
            "Card",
            sp_pr=xfrm(600000, 900000, 4572000, 914400)
            + RECT
            + '<a:solidFill><a:schemeClr val="accent1"/></a:solidFill>',
        ),
        shape_xml(
            3,
            "Title",
            placeholder="title",
            tx_body='<a:bodyPr/><a:lstStyle/>' + paragraph_xml("Themed title"),
        ),
        shape_xml(
            4,
            "Rotated",
            sp_pr='<a:xfrm rot="2700000"><a:off x="100" y="200"/>'
            '<a:ext cx="914400" cy="914400"/></a:xfrm>'
            + ROUND_RECT
            + '<a:solidFill><a:srgbClr val="DDDDDD"/></a:solidFill>'
            '<a:ln w="25400"><a:solidFill><a:srgbClr val="DCE4EE"/></a:solidFill></a:ln>',
        ),
        shape_xml(
            5,
            "NoLine",
            sp_pr=xfrm(0, 0, 914400, 914400)
            + RECT
            + "<a:ln/>"
            + '<a:solidFill><a:srgbClr val="EEEEEE"/></a:solidFill>',
        ),
        picture,
    ]
    return themed_pptx(shapes, image=TINY_PNG)


def _render(object_store, deck: bytes, config: RenderConfig | None = None):
    config = config or RenderConfig()
    renderer = StructuralSvgRenderer(object_store, config)
    document = PptxExtractor().extract(deck)
    report = renderer.render(
        RenderRequest(
            document=document,
            identity=renderer.identity(),
            media=read_media_parts(deck, document_media_refs(document)),
        ),
        budget=RenderBudget(config.deadline_seconds, max_attempts=1),
    )
    return report


def _svg(object_store, report, order: int = 0) -> str:
    return object_store.get(report.scene(order).asset_ref).decode()


# -- resolved style reaches the output ---------------------------------------------
def test_theme_fill_and_inherited_master_text_reach_the_svg(object_store):
    """A theme colour and a master-only font size are both drawn literally."""

    svg = _svg(object_store, _render(object_store, styled_deck()))

    assert 'fill="#1B3A8C"' in svg  # theme accent1
    # The master's family is unavailable, so it is substituted in place (V0-019 v5)
    # rather than named first and left to the client's fonts.
    assert 'font-family="Noto Sans' in svg
    assert "Major Sans" not in svg
    assert 'font-size="53.33"' in svg  # 40 pt
    assert 'font-weight="bold"' in svg


def test_text_is_placed_at_its_box_origin(object_store):
    """X must be absolute: 838200 EMU + the 91440 EMU inset is 97.6 px."""

    svg = _svg(object_store, _render(object_store, styled_deck()))

    assert '<text x="97.6"' in svg or '<text x="97.6" ' in svg


def test_rotation_emits_a_transform_around_the_shape_centre(object_store):
    svg = _svg(object_store, _render(object_store, styled_deck()))

    assert 'transform="rotate(45 ' in svg
    assert 'stroke="#DCE4EE" stroke-width="2.67"' in svg


def test_a_shape_with_no_line_is_filled_but_not_stroked(object_store):
    """``<a:ln/>`` must not become an invented outline."""

    svg = _svg(object_store, _render(object_store, styled_deck()))

    assert 'fill="#EEEEEE"/>' in svg
    assert 'fill="#EEEEEE" stroke' not in svg


def test_picture_is_inlined_and_cropped(object_store):
    svg = _svg(object_store, _render(object_store, styled_deck()))

    assert 'href="data:image/png;base64,' in svg
    # srcRect is implemented by clipping an oversized, negative-offset image.
    assert 'clipPath id="clip1"' in svg
    assert 'clip-path="url(#clip1)"' in svg


def test_table_cells_take_their_fill_text_and_column_ratio(object_store):
    table = (
        '<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="5" name="T"/>'
        "<p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr>"
        '<p:xfrm><a:off x="0" y="0"/><a:ext cx="914400" cy="457200"/></p:xfrm>'
        "<a:graphic><a:graphicData><a:tbl>"
        '<a:tblGrid><a:gridCol w="600000"/><a:gridCol w="314400"/></a:tblGrid>'
        '<a:tr h="228600">'
        "<a:tc><a:txBody><a:p><a:r><a:t>Head</a:t></a:r></a:p></a:txBody>"
        '<a:tcPr><a:solidFill><a:schemeClr val="accent1"/></a:solidFill></a:tcPr></a:tc>'
        "<a:tc><a:txBody><a:p><a:r><a:t>Value</a:t></a:r></a:p></a:txBody><a:tcPr/></a:tc>"
        "</a:tr></a:tbl></a:graphicData></a:graphic></p:graphicFrame>"
    )
    svg = _svg(object_store, _render(object_store, themed_pptx([table])))

    # 600000:314400 of 96 px -> 62.99 px, and the header keeps its theme fill.
    assert '<rect x="0" y="0" width="62.99" height="48" fill="#1B3A8C"' in svg
    assert '<rect x="62.99" y="0" width="33.01" height="48"' in svg
    assert ">Head</text>" in svg
    assert ">Value</text>" in svg


# -- picture backgrounds (V0-019 v5) -----------------------------------------------
#: ``p:bg`` with a picture fill — how a deck paints its title/section layouts.
_LAYOUT_BG = (
    '<p:bg><p:bgPr><a:blipFill dpi="0" rotWithShape="1">'
    '<a:blip r:embed="{rel}"/><a:srcRect/><a:stretch><a:fillRect/></a:stretch>'
    "</a:blipFill><a:effectLst/></p:bgPr></p:bg>"
)


def _deck_with_a_layout_background(*, rel: str = "rIdBg", image: bytes | None = TINY_PNG) -> bytes:
    """A deck whose *layout* paints the slide with a picture background.

    A layout's ``p:bg`` references the **layout's** relationships, so it only
    resolves when each level is resolved against the part that declares it.
    """

    layout = slide_layout_xml().replace("<p:cSld>", "<p:cSld>" + _LAYOUT_BG.format(rel=rel), 1)
    rels = [("rId1", REL_SLIDE_MASTER, "../slideMasters/slideMaster1.xml")]
    entries: dict[str, bytes] = {
        "ppt/slideLayouts/slideLayout1.xml": layout.encode(),
        "ppt/slideLayouts/_rels/slideLayout1.xml.rels": _rels_xml(rels).encode(),
    }
    if rel == "rIdBg" and image is not None:
        entries["ppt/media/bg.png"] = image
        # ``themed_pptx`` rebuilds the layout rels, so hand them over as extra entries.
        entries["ppt/slideLayouts/_rels/slideLayout1.xml.rels"] = _rels_xml(
            [*rels, ("rIdBg", REL_IMAGE, "../media/bg.png")]
        ).encode()
    return themed_pptx(
        [text_shape(2, "Title", text="Thank you")],
        extra_entries=entries,
    )


def test_a_picture_layout_background_is_resolved_and_inlined(object_store):
    """The layout's own ``a:blipFill`` background must reach the SVG as an image."""

    deck = _deck_with_a_layout_background()
    document = PptxExtractor().extract(deck)
    background = document.slides[0].background

    assert background["type"] == "picture"
    assert background["media_ref"] == "ppt/media/bg.png"
    assert background["media_type"] == "image/png"
    # The compiler must hand the bytes over, or the renderer cannot inline them.
    assert "ppt/media/bg.png" in document_media_refs(document)

    svg = _svg(object_store, _render(object_store, deck))

    assert 'preserveAspectRatio="none"' in svg  # stretched to the canvas
    assert "data:image/png;base64," in svg
    assert svg.index("data:image/png") < svg.index("<text")  # painted under the slide


def test_an_unresolvable_picture_background_does_not_mask_the_master(object_store):
    """A background we cannot resolve falls through instead of becoming "none".

    Returning ``{"type": "none"}`` for the unusable layout picture would win over
    the master and paint the slide white — which is how a dark title slide loses
    its background *and* its light text becomes unreadable.
    """

    deck = _deck_with_a_layout_background(rel="rIdMissing", image=None)
    document = PptxExtractor().extract(deck)

    assert document.slides[0].background["type"] == "solid"
    svg = _svg(object_store, _render(object_store, deck))
    assert "data:image" not in svg


# -- degradation is explicit, never silent -----------------------------------------
def test_inherited_unavailable_font_is_substituted_not_degraded(object_store):
    """The gate must see the master's font, and the run must still be drawn."""

    report = _render(object_store, styled_deck())
    result = report.scene(0)

    assert result.status is RenderStatus.RENDERED
    assert result.fidelity == "STRUCTURAL_RENDERED"
    assert "FONT_SUBSTITUTED:Major Sans" in result.warnings
    assert result.missing_fonts == ("Major Sans",)
    assert "Major Sans" not in _svg(object_store, report)


def test_an_oversized_picture_becomes_a_labelled_platform_panel(object_store):
    """Over-budget media must not fail the scene — the app's look replaces it."""

    config = RenderConfig(max_inline_media_bytes=1)
    report = _render(object_store, styled_deck(), config)
    result = report.scene(0)
    svg = _svg(object_store, report)

    assert result.status is RenderStatus.RENDERED
    assert result.fidelity == "STRUCTURAL_RENDERED"
    assert "MEDIA_BUDGET_EXCEEDED:ppt/media/image1.png" in result.warnings
    assert "data:image" not in svg
    # The fallback is the platform's own panel, not a foreign grey placeholder.
    assert 'fill="#F4F7FB"' in svg
    assert 'font-family="Noto Sans' in svg
    assert ">image1.png</text>" in svg


# -- determinism -------------------------------------------------------------------
def test_rendering_the_same_deck_twice_is_byte_identical(object_store):
    """Content-addressed output: same input, same config, same asset."""

    deck = styled_deck()
    first = _render(object_store, deck)
    second = _render(object_store, deck)

    assert first.scene(0).asset_ref == second.scene(0).asset_ref
    assert _svg(object_store, first) == _svg(object_store, second)
