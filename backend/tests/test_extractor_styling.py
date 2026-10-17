"""V0-018: presentation styling resolved from the theme/layout/master chain.

PowerPoint keeps almost all look information outside the slide, so these tests
build a deck with a real theme, master, and layout and assert that the extractor
resolves *effective* values (colours, fonts, sizes, geometry, fills) into the
Content IR — the property that lets a renderer reproduce the original without
knowing anything about OOXML inheritance.
"""

from __future__ import annotations

from app.compiler.extractors.pptx import PptxExtractor
from tests.fixtures import (
    REL_IMAGE,
    TINY_PNG,
    paragraph_xml,
    shape_xml,
    text_shape,
    themed_pptx,
    xfrm,
)

RECT = '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'


def _object(document, name):
    slide = document.slides[0]
    return next(o for o in slide.objects if o.name == name)


# -- theme ------------------------------------------------------------------------
def test_theme_colors_and_fonts_are_resolved(extractor):
    """``schemeClr`` resolves through the colour map to real sRGB."""

    shapes = [
        shape_xml(
            2,
            "Card",
            sp_pr=xfrm(0, 0, 914400, 914400)
            + RECT
            + '<a:solidFill><a:schemeClr val="accent1"/></a:solidFill>',
        )
    ]
    card = _object(extractor.extract(themed_pptx(shapes)), "Card")

    assert card.fill == {"type": "solid", "color": {"value": "#1B3A8C", "alpha": 1.0}}


def test_color_map_is_applied_to_the_scheme(extractor):
    """A master ``p:clrMap`` remaps format names before the theme is consulted."""

    from tests.fixtures import slide_master_xml

    master = slide_master_xml(
        clr_map='bg1="dk2" tx1="lt1" bg2="lt2" tx2="dk2" accent1="accent1" '
        'accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" '
        'accent6="accent6" hlink="hlink" folHlink="folHlink"'
    )
    shapes = [
        shape_xml(
            2,
            "Card",
            sp_pr=xfrm(0, 0, 914400, 914400)
            + RECT
            + '<a:solidFill><a:schemeClr val="bg1"/></a:solidFill>',
        )
    ]
    card = _object(extractor.extract(themed_pptx(shapes, master_xml=master)), "Card")

    # bg1 -> dk2 -> #44546A, not the theme's lt1 white.
    assert card.fill["color"]["value"] == "#44546A"


def test_color_modifiers_are_applied(extractor):
    """``lumMod``/``shade``/``alpha`` change the resolved colour."""

    shapes = [
        shape_xml(
            2,
            "Card",
            sp_pr=xfrm(0, 0, 914400, 914400)
            + RECT
            + '<a:solidFill><a:srgbClr val="FFFFFF"><a:alpha val="50000"/></a:srgbClr>'
            "</a:solidFill>",
        )
    ]
    card = _object(extractor.extract(themed_pptx(shapes)), "Card")

    assert card.fill["color"] == {"value": "#FFFFFF", "alpha": 0.5}


# -- text style cascade -----------------------------------------------------------
def test_title_placeholder_inherits_layout_geometry_and_master_style(extractor):
    """No ``a:xfrm`` on the slide, no ``a:rPr`` on the run: both are inherited."""

    shapes = [
        shape_xml(
            2,
            "Title",
            placeholder="title",
            tx_body='<a:bodyPr/><a:lstStyle/>' + paragraph_xml("Themed title"),
        )
    ]
    title = _object(extractor.extract(themed_pptx(shapes)), "Title")

    # Geometry comes from the layout placeholder of the same type.
    assert (title.bounds.x, title.bounds.y) == (838200, 365125)
    assert (title.bounds.width, title.bounds.height) == (10515600, 1325563)
    # Text defaults come from the master's p:titleStyle.
    run = title.paragraphs[0].runs[0]
    assert run.size_pt == 40.0
    assert run.bold is True
    assert run.font == "Major Sans"
    assert run.color == {"value": "#111111", "alpha": 1.0}
    assert title.paragraphs[0].align == "l"


def test_layout_text_style_overrides_the_master(extractor):
    """The layout's ``lstStyle`` wins for the level it defines, the master for the rest."""

    shapes = [
        shape_xml(
            2,
            "Body",
            placeholder="body",
            ph_idx="1",
            tx_body="<a:bodyPr/><a:lstStyle/>"
            + paragraph_xml("First")
            + paragraph_xml("Second", level=1),
        )
    ]
    body = _object(extractor.extract(themed_pptx(shapes)), "Body")
    first, second = body.paragraphs

    # Level 1: the layout's 14 pt overrides the master's 18 pt; the bullet and
    # hanging indent still come from the master's p:bodyStyle.
    assert first.runs[0].size_pt == 14.0
    assert first.bullet == {"char": "•"}
    assert first.margin_left_emu == 342900
    assert first.runs[0].font == "Minor Sans"
    # Level 2: only the master defines it.
    assert second.level == 1
    assert second.runs[0].size_pt == 16.0
    assert second.bullet == {"char": "–"}
    assert second.margin_left_emu == 742950


def test_explicit_run_formatting_beats_inherited(extractor):
    shapes = [
        shape_xml(
            2,
            "Title",
            placeholder="title",
            tx_body='<a:bodyPr/><a:lstStyle/>'
            + paragraph_xml(
                "Explicit",
                p_pr_attrs=' algn="ctr"',
                r_pr_attrs=' sz="2400" b="0" i="1" u="sng"',
                r_pr='<a:solidFill><a:srgbClr val="FF5500"/></a:solidFill>'
                '<a:latin typeface="Explicit Sans"/>',
            ),
        )
    ]
    para = _object(extractor.extract(themed_pptx(shapes)), "Title").paragraphs[0]

    assert para.align == "ctr"
    run = para.runs[0]
    assert run.size_pt == 24.0
    assert run.bold is False
    assert run.italic is True
    assert run.underline is True
    assert run.font == "Explicit Sans"
    assert run.color == {"value": "#FF5500", "alpha": 1.0}


def test_line_spacing_points_are_kept_absolute(extractor):
    """``spcPts`` is an absolute leading, not a multiple of the font size."""

    shapes = [
        shape_xml(
            2,
            "Body",
            tx_body='<a:bodyPr/><a:lstStyle/>'
            + paragraph_xml("Line", p_pr='<a:lnSpc><a:spcPts val="2000"/></a:lnSpc>'),
        )
    ]
    para = _object(extractor.extract(themed_pptx(shapes)), "Body").paragraphs[0]

    assert para.line_spacing_pt == 20.0
    assert para.line_spacing is None


# -- shapes -----------------------------------------------------------------------
def test_shape_fill_line_geometry_and_rotation(extractor):
    shapes = [
        shape_xml(
            2,
            "Card",
            sp_pr='<a:xfrm rot="2700000" flipH="1"><a:off x="100" y="200"/>'
            '<a:ext cx="300" cy="400"/></a:xfrm>'
            '<a:prstGeom prst="roundRect"><a:avLst/></a:prstGeom>'
            '<a:solidFill><a:schemeClr val="accent2"/></a:solidFill>'
            '<a:ln w="25400" cap="flat"><a:solidFill><a:srgbClr val="DCE4EE"/></a:solidFill>'
            '<a:prstDash val="dash"/></a:ln>',
        )
    ]
    card = _object(extractor.extract(themed_pptx(shapes)), "Card")

    assert card.geometry == "roundRect"
    assert card.rotation == 45.0
    assert card.flip_h is True
    assert card.flip_v is False
    assert card.fill["color"]["value"] == "#0A6EBD"
    # The line colour sits inside a:solidFill, so it must be looked up there.
    assert card.line == {
        "color": {"value": "#DCE4EE", "alpha": 1.0},
        "width_emu": 25400,
        "dash": "dash",
    }


def test_empty_line_element_means_no_outline(extractor):
    """``<a:ln/>`` with no colour must not become an invented outline."""

    shapes = [shape_xml(2, "Card", sp_pr=xfrm(0, 0, 100, 100) + RECT + "<a:ln/>")]
    card = _object(extractor.extract(themed_pptx(shapes)), "Card")

    assert card.line is None


def test_no_fill_is_distinguished_from_unknown(extractor):
    shapes = [shape_xml(2, "Clear", sp_pr=xfrm(0, 0, 100, 100) + RECT + "<a:noFill/>")]
    card = _object(extractor.extract(themed_pptx(shapes)), "Clear")

    assert card.fill == {"type": "none"}


def test_gradient_fill_is_extracted(extractor):
    shapes = [
        shape_xml(
            2,
            "Bar",
            sp_pr=xfrm(0, 0, 914400, 914400)
            + RECT
            + '<a:gradFill><a:gsLst>'
            '<a:gs pos="0"><a:srgbClr val="1B3A8C"/></a:gs>'
            '<a:gs pos="100000"><a:srgbClr val="4FB3F0"/></a:gs>'
            '</a:gsLst><a:lin ang="5400000" scaled="0"/></a:gradFill>',
        )
    ]
    bar = _object(extractor.extract(themed_pptx(shapes)), "Bar")

    assert bar.fill == {
        "type": "gradient",
        "angle": 90.0,
        "stops": [
            {"position": 0.0, "color": {"value": "#1B3A8C", "alpha": 1.0}},
            {"position": 1.0, "color": {"value": "#4FB3F0", "alpha": 1.0}},
        ],
    }


def test_custom_geometry_becomes_a_unit_square_path(extractor):
    shapes = [
        shape_xml(
            2,
            "Banner",
            sp_pr=xfrm(0, 0, 1000, 500)
            + '<a:custGeom><a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/>'
            '<a:rect l="0" t="0" r="1000" b="500"/><a:pathLst>'
            '<a:path w="1000" h="500">'
            '<a:moveTo><a:pt x="0" y="0"/></a:moveTo>'
            '<a:lnTo><a:pt x="1000" y="0"/></a:lnTo>'
            '<a:lnTo><a:pt x="1000" y="500"/></a:lnTo>'
            '<a:close/>'
            "</a:path></a:pathLst></a:custGeom>"
            + '<a:solidFill><a:schemeClr val="accent3"/></a:solidFill>',
        )
    ]
    banner = _object(extractor.extract(themed_pptx(shapes)), "Banner")

    assert banner.geometry == "custGeom"
    assert banner.custom_path == "M0 0 L1 0 L1 1 Z"


def test_unresolvable_custom_geometry_falls_back(extractor):
    """A formula-driven point must not produce a guessed path."""

    shapes = [
        shape_xml(
            2,
            "Banner",
            sp_pr=xfrm(0, 0, 1000, 500)
            + '<a:custGeom><a:pathLst><a:path w="1000" h="500">'
            '<a:moveTo><a:pt x="*/2" y="0"/></a:moveTo>'
            '<a:lnTo><a:pt x="1000" y="500"/></a:lnTo>'
            "</a:path></a:pathLst></a:custGeom>",
        )
    ]
    banner = _object(extractor.extract(themed_pptx(shapes)), "Banner")

    assert banner.custom_path is None


# -- background -------------------------------------------------------------------
def test_slide_background_is_extracted(extractor):
    background = (
        "<p:bg><p:bgPr><a:gradFill><a:gsLst>"
        '<a:gs pos="0"><a:srgbClr val="FFFFFF"/></a:gs>'
        '<a:gs pos="100000"><a:srgbClr val="EEF2F7"/></a:gs>'
        "</a:gsLst><a:lin ang=\"5400000\"/></a:gradFill></p:bgPr></p:bg>"
    )
    document = extractor.extract(themed_pptx([], background=background))

    assert document.slides[0].background["type"] == "gradient"


def test_background_falls_back_to_the_layout_then_master(extractor):
    """No slide background -> the master's ``p:bg`` applies (via the layout)."""

    document = extractor.extract(themed_pptx([]))
    background = document.slides[0].background

    # Master background is ``schemeClr bg1`` -> clrMap bg1 -> lt1 -> FFFFFF.
    assert background == {"type": "solid", "color": {"value": "#FFFFFF", "alpha": 1.0}}


def test_background_reference_is_resolved(extractor):
    background = (
        '<p:bg><p:bgRef idx="1001"><a:schemeClr val="accent2"/></p:bgRef></p:bg>'
    )
    document = extractor.extract(themed_pptx([], background=background))

    assert document.slides[0].background == {
        "type": "solid",
        "color": {"value": "#0A6EBD", "alpha": 1.0},
    }


# -- groups -----------------------------------------------------------------------
def test_group_children_get_absolute_bounds(extractor):
    """Child coordinates are in group space; the IR must report slide space."""

    child = text_shape(10, "Inner", text="Inner", x=500, y=700, cx=1000, cy=1000)
    group = (
        '<p:grpSp><p:nvGrpSpPr><p:cNvPr id="9" name="G"/><p:cNvGrpSpPr/>'
        "<p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm>"
        '<a:off x="1000" y="2000"/><a:ext cx="2000" cy="2000"/>'
        '<a:chOff x="0" y="0"/><a:chExt cx="4000" cy="4000"/>'
        "</a:xfrm></p:grpSpPr>" + child + "</p:grpSp>"
    )
    document = extractor.extract(themed_pptx([group]))
    inner = _object(document, "Inner")

    # scale = 2000/4000 = 0.5; ox = 1000 - 0 = 1000, oy = 2000.
    assert inner.depth == 1
    assert inner.bounds.x == 1000 + 500 * 0.5
    assert inner.bounds.y == 2000 + 700 * 0.5
    assert inner.bounds.width == 500
    assert inner.bounds.height == 500


def test_nested_groups_compose_their_transforms(extractor):
    inner_child = text_shape(11, "Deep", text="Deep", x=100, y=100, cx=100, cy=100)
    inner_group = (
        '<p:grpSp><p:nvGrpSpPr><p:cNvPr id="10" name="G2"/><p:cNvGrpSpPr/>'
        "<p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm>"
        '<a:off x="0" y="0"/><a:ext cx="200" cy="200"/>'
        '<a:chOff x="0" y="0"/><a:chExt cx="200" cy="200"/>'
        "</a:xfrm></p:grpSpPr>" + inner_child + "</p:grpSp>"
    )
    outer_group = (
        '<p:grpSp><p:nvGrpSpPr><p:cNvPr id="9" name="G1"/><p:cNvGrpSpPr/>'
        "<p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm>"
        '<a:off x="400" y="600"/><a:ext cx="400" cy="400"/>'
        '<a:chOff x="0" y="0"/><a:chExt cx="200" cy="200"/>'
        "</a:xfrm></p:grpSpPr>" + inner_group + "</p:grpSp>"
    )
    document = extractor.extract(themed_pptx([outer_group]))
    deep = _object(document, "Deep")

    # inner: identity; outer: scale 2, offset 400/600.
    assert deep.depth == 2
    assert deep.bounds.x == 400 + 100 * 2
    assert deep.bounds.width == 200


# -- pictures ---------------------------------------------------------------------
def test_picture_media_type_and_crop(extractor):
    picture = (
        '<p:pic><p:nvPicPr><p:cNvPr id="4" name="Photo"/><p:cNvPicPr/>'
        "<p:nvPr/></p:nvPicPr>"
        '<p:blipFill><a:blip r:embed="rIdImg"/><a:srcRect l="10000" t="25000" '
        'r="5000" b="15000"/></p:blipFill>'
        '<p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="914400" cy="457200"/></a:xfrm>'
        "</p:spPr></p:pic>"
    )
    document = extractor.extract(themed_pptx([picture], image=TINY_PNG))
    photo = _object(document, "Photo")

    assert photo.media_ref == "ppt/media/image1.png"
    assert photo.media_type == "image/png"
    assert photo.crop == {"left": 0.1, "top": 0.25, "right": 0.05, "bottom": 0.15}


def test_non_inlineable_picture_is_warned_about(extractor):
    picture = (
        '<p:pic><p:nvPicPr><p:cNvPr id="4" name="Vector"/><p:cNvPicPr/>'
        "<p:nvPr/></p:nvPicPr>"
        '<p:blipFill><a:blip r:embed="rIdWmf"/></p:blipFill>'
        '<p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="100" cy="100"/></a:xfrm>'
        "</p:spPr></p:pic>"
    )
    document = extractor.extract(
        themed_pptx(
            [picture],
            extra_entries={"ppt/media/image1.wmf": b"wmfdata"},
            extra_slide_rels={1: [("rIdWmf", REL_IMAGE, "../media/image1.wmf")]},
        )
    )
    photo = _object(document, "Vector")

    assert photo.media_type is None
    assert any("cannot be inlined" in w for w in document.slides[0].warnings)


# -- tables -----------------------------------------------------------------------
def test_table_metrics_and_cell_fills(extractor):
    table = (
        '<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="5" name="T"/>'
        "<p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr>"
        '<p:xfrm><a:off x="0" y="0"/><a:ext cx="914400" cy="457200"/></p:xfrm>'
        "<a:graphic><a:graphicData><a:tbl>"
        "<a:tblGrid>"
        '<a:gridCol w="600000"/><a:gridCol w="314400"/>'
        "</a:tblGrid>"
        '<a:tr h="228600">'
        '<a:tc><a:txBody><a:p><a:r><a:t>Head</a:t></a:r></a:p></a:txBody>'
        '<a:tcPr><a:solidFill><a:schemeClr val="accent1"/></a:solidFill></a:tcPr></a:tc>'
        "<a:tc><a:txBody><a:p><a:r><a:t>Value</a:t></a:r></a:p></a:txBody><a:tcPr/></a:tc>"
        "</a:tr>"
        "</a:tbl></a:graphicData></a:graphic></p:graphicFrame>"
    )
    document = extractor.extract(themed_pptx([table]))
    parsed = _object(document, "T")

    assert parsed.table == [["Head", "Value"]]
    assert parsed.table_columns == [600000, 314400]
    assert parsed.table_rows == [228600]
    assert parsed.table_cells[0][0].fill == {
        "type": "solid",
        "color": {"value": "#1B3A8C", "alpha": 1.0},
    }
    assert parsed.table_cells[0][0].paragraphs[0].text == "Head"


def test_table_span_and_merge_flags(extractor):
    table = (
        '<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="5" name="T"/>'
        "<p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr>"
        '<p:xfrm><a:off x="0" y="0"/><a:ext cx="914400" cy="457200"/></p:xfrm>'
        "<a:graphic><a:graphicData><a:tbl>"
        '<a:tr h="228600">'
        '<a:tc gridSpan="2"><a:txBody><a:p><a:r><a:t>Wide</a:t></a:r></a:p></a:txBody>'
        '<a:tcPr gridSpan="2"/></a:tc>'
        '<a:tc hMerge="1"><a:txBody><a:p/></a:txBody><a:tcPr hMerge="1"/></a:tc>'
        "</a:tr></a:tbl></a:graphicData></a:graphic></p:graphicFrame>"
    )
    parsed = _object(extractor.extract(themed_pptx([table])), "T")

    assert parsed.table_cells[0][0].grid_span == 2
    assert parsed.table_cells[0][1].h_merge is True


# -- extraction-level invariants ---------------------------------------------------
def test_themed_deck_has_no_new_warnings(extractor):
    document = extractor.extract(themed_pptx([text_shape(2, "T", text="Hello")]))

    assert document.slides[0].warnings == []


def test_ir_schema_version_records_the_styling_revision(extractor):
    document = extractor.extract(themed_pptx([text_shape(2, "T", text="Hello")]))

    assert document.schema_version == "content-ir/1.2.0"
    assert document.provenance["extractor_version"] == "1.2.0"


def test_extraction_is_deterministic(extractor):
    deck = themed_pptx([text_shape(2, "T", text="Hello")])

    first = extractor.extract(deck).to_dict()
    second = PptxExtractor().extract(deck).to_dict()

    assert first == second
