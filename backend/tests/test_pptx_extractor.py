import pytest

from app.common.errors import AppError, ErrorCode
from app.compiler.extractors.pptx import PptxExtractor
from tests.fixtures import (
    REL_CHART,
    REL_IMAGE,
    build_pptx,
    chart_shape,
    group_shape,
    picture_shape,
    simple_pptx,
    table_shape,
    text_shape,
)


def test_extracts_slide_text_and_notes(extractor):
    deck = build_pptx(
        [[text_shape(2, "Title", text="Attention", placeholder="title")]],
        notes={1: "Remember query/key/value"},
    )
    document = extractor.extract(deck, source_sha256="f" * 64)

    assert document.slide_count == 1
    scene = document.slides[0]
    assert scene.order == 0
    assert scene.notes == "Remember query/key/value"
    titles = [o for o in scene.objects if o.placeholder == "title"]
    assert titles and titles[0].paragraphs[0].text == "Attention"


def test_slide_dimensions_and_order(extractor):
    deck = build_pptx(
        [[text_shape(2, "A", text="one")], [text_shape(2, "B", text="two")]],
        width_emu=9144000,
        height_emu=6858000,
    )
    document = extractor.extract(deck)
    assert document.slide_width == 9144000
    assert document.slide_height == 6858000
    assert [s.order for s in document.slides] == [0, 1]
    assert document.slides[0].scene_id == "ppt/slides/slide1.xml"


def test_group_children_are_traversed(extractor):
    deck = build_pptx([[group_shape(10, "Group", [text_shape(11, "Inner", text="inside")])]])
    document = extractor.extract(deck)
    objects = document.slides[0].objects
    assert [o for o in objects if o.kind == "group"], "group container should be emitted"
    texts = [p.text for o in objects for p in o.paragraphs]
    assert "inside" in texts


def test_group_bounds_and_name_are_kept(extractor):
    deck = build_pptx([[group_shape(10, "KPI Row", [], cx=3657600, cy=914400)]])
    document = extractor.extract(deck)
    group = next(o for o in document.slides[0].objects if o.kind == "group")
    assert group.name == "KPI Row"
    assert group.bounds.width == 3657600
    assert group.bounds.height == 914400


def test_nested_groups_are_traversed(extractor):
    inner = group_shape(11, "Inner", [text_shape(12, "Leaf", text="deep-text")])
    deck = build_pptx([[group_shape(10, "Outer", [inner, text_shape(13, "Mid", text="mid-text")])]])
    document = extractor.extract(deck)
    texts = [p.text for o in document.slides[0].objects for p in o.paragraphs]
    assert "deep-text" in texts and "mid-text" in texts


def test_group_nesting_depth_is_recorded(extractor):
    inner = group_shape(11, "Inner", [text_shape(12, "Leaf", text="deep-text")])
    deck = build_pptx(
        [
            [
                text_shape(2, "Top", text="top-text"),
                group_shape(10, "Outer", [inner, text_shape(13, "Mid", text="mid-text")]),
            ]
        ]
    )
    document = extractor.extract(deck)
    by_text = {p.text: o.depth for o in document.slides[0].objects for p in o.paragraphs}
    assert by_text["top-text"] == 0
    assert by_text["mid-text"] == 1
    assert by_text["deep-text"] == 2
    groups = [o for o in document.slides[0].objects if o.kind == "group"]
    assert sorted(g.depth for g in groups) == [0, 1]


def test_picture_inside_group_is_captured(extractor):
    deck = build_pptx(
        [[group_shape(10, "Group", [picture_shape(11, "Pic", rel_id="rIdImg")])]],
        extra_slide_rels={1: [("rIdImg", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image", "../media/image1.png")]},
        extra_entries={"ppt/media/image1.png": b"PNGDATA"},
    )
    document = extractor.extract(deck)
    pictures = [o for o in document.slides[0].objects if o.kind == "picture"]
    assert pictures and pictures[0].media_ref == "ppt/media/image1.png"


def test_no_text_is_lost_from_grouped_shapes(extractor):
    """Regression: every paragraph in a group must reach the IR."""

    inner = [text_shape(20 + i, f"G{i}", text=f"group-text-{i}") for i in range(4)]
    deck = build_pptx(
        [[text_shape(2, "Top", text="top-text"), group_shape(10, "Group", inner)]]
    )
    document = extractor.extract(deck)
    texts = {p.text for o in document.slides[0].objects for p in o.paragraphs}
    assert texts >= {"top-text"} | {f"group-text-{i}" for i in range(4)}


def test_unsupported_container_is_reported_not_dropped(extractor):
    deck = build_pptx([[text_shape(2, "A", text="keep"), "<p:contentPart/>"]])
    document = extractor.extract(deck)
    scene = document.slides[0]
    assert any("contentPart" in w for w in scene.warnings)
    assert "keep" in [p.text for o in scene.objects for p in o.paragraphs]


def test_table_is_extracted(extractor):
    deck = build_pptx([[table_shape(5, "Table", [["a", "b"], ["c", "d"]])]])
    document = extractor.extract(deck)
    tables = [o for o in document.slides[0].objects if o.kind == "table"]
    assert tables and tables[0].table == [["a", "b"], ["c", "d"]]


def test_picture_media_reference_resolved(extractor):
    deck = build_pptx(
        [[picture_shape(4, "Pic", rel_id="rIdImg")]],
        extra_slide_rels={1: [("rIdImg", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image", "../media/image1.png")]},
        extra_entries={"ppt/media/image1.png": b"PNGDATA"},
    )
    document = extractor.extract(deck)
    pictures = [o for o in document.slides[0].objects if o.kind == "picture"]
    assert pictures and pictures[0].media_ref == "ppt/media/image1.png"


def test_missing_slide_part_is_not_silently_omitted(extractor):
    deck = build_pptx(
        [[text_shape(2, "A", text="one")], [text_shape(2, "B", text="two")]],
        missing_slide=2,
    )
    document = extractor.extract(deck)
    assert document.slide_count == 2
    assert any("missing" in w for w in document.slides[1].warnings)


def test_not_a_zip_is_rejected(extractor):
    with pytest.raises(AppError) as exc:
        extractor.extract(b"not a package")
    assert exc.value.code is ErrorCode.INVALID_PPTX_PACKAGE


def test_missing_presentation_part_is_rejected(extractor):
    deck = build_pptx([[text_shape(2, "A", text="one")]], include_presentation=False)
    with pytest.raises(AppError) as exc:
        extractor.extract(deck)
    assert exc.value.code is ErrorCode.INVALID_PPTX_PACKAGE


def test_archive_entry_budget_is_enforced():
    tiny = PptxExtractor(max_entries=1)
    with pytest.raises(AppError) as exc:
        tiny.extract(simple_pptx())
    assert exc.value.code is ErrorCode.ARCHIVE_TOO_LARGE


# -- V0-004: text runs, fonts, chart refs, reading order, broken relationships ---
def test_text_runs_are_preserved_with_their_fonts(extractor):
    deck = build_pptx(
        [[text_shape(2, "Title", text="Attention", font="Bree Serif", placeholder="title")]]
    )
    document = extractor.extract(deck)
    shape = document.slides[0].objects[0]

    assert shape.paragraphs[0].text == "Attention"
    runs = shape.paragraphs[0].runs
    assert [r.text for r in runs] == ["Attention"]
    assert runs[0].font == "Bree Serif"
    assert shape.fonts == ["Bree Serif"]


def test_theme_font_references_are_not_reported_as_fonts(extractor):
    """``+mj-lt`` is a theme placeholder, not a font family."""

    shape = (
        '<p:sp><p:nvSpPr><p:cNvPr id="2" name="T"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
        "<p:spPr/>"
        '<p:txBody><a:bodyPr/><a:p><a:r><a:rPr><a:latin typeface="+mj-lt"/></a:rPr>'
        "<a:t>themed</a:t></a:r></a:p></p:txBody></p:sp>"
    )
    document = extractor.extract(build_pptx([[shape]]))
    obj = document.slides[0].objects[0]
    assert obj.paragraphs[0].runs[0].font is None
    assert obj.fonts == []


def test_slide_fonts_are_aggregated(extractor):
    deck = build_pptx(
        [
            [
                text_shape(2, "A", text="one", font="Inter"),
                text_shape(3, "B", text="two", font="Inter"),
                text_shape(4, "C", text="three", font="VNI-Times"),
            ]
        ]
    )
    document = extractor.extract(deck)
    assert document.slides[0].fonts() == ["Inter", "VNI-Times"]


def test_reading_order_is_explicit_and_follows_the_shape_tree(extractor):
    inner = group_shape(11, "Inner", [text_shape(12, "Leaf", text="deep-text")])
    deck = build_pptx(
        [[text_shape(2, "Top", text="top-text"), group_shape(10, "Outer", [inner])]]
    )
    document = extractor.extract(deck)
    objects = document.slides[0].objects

    assert [o.reading_order for o in objects] == list(range(len(objects)))
    by_name = {o.name: o.reading_order for o in objects}
    assert by_name["Top"] < by_name["Outer"] < by_name["Inner"] < by_name["Leaf"]


def test_chart_reference_is_resolved(extractor):
    deck = build_pptx(
        [[chart_shape(6, "Scores")]],
        extra_slide_rels={1: [("rIdChart", REL_CHART, "../charts/chart1.xml")]},
        extra_entries={"ppt/charts/chart1.xml": b"<c:chartSpace/>"},
    )
    document = extractor.extract(deck)
    charts = [o for o in document.slides[0].objects if o.kind == "chart"]
    assert charts and charts[0].media_ref == "ppt/charts/chart1.xml"


def test_broken_relationship_warns_and_does_not_crash(extractor):
    deck = build_pptx([[picture_shape(4, "Figure", rel_id="rIdMissing")]])
    document = extractor.extract(deck)
    scene = document.slides[0]
    assert any("unresolved relationship 'rIdMissing'" in w for w in scene.warnings)
    # The picture is still reported; only its reference is unknown.
    assert [o for o in scene.objects if o.kind == "picture"]


def test_reference_to_absent_part_warns(extractor):
    deck = build_pptx(
        [[picture_shape(4, "Figure", rel_id="rIdImg")]],
        extra_slide_rels={1: [("rIdImg", REL_IMAGE, "../media/missing.png")]},
    )
    document = extractor.extract(deck)
    assert any("'ppt/media/missing.png' is absent" in w for w in document.slides[0].warnings)


def test_malformed_relationship_part_degrades_instead_of_failing(extractor):
    deck = build_pptx(
        [[text_shape(2, "Keep", text="still-extracted")]],
        extra_entries={"ppt/slides/_rels/slide1.xml.rels": b"<Relationships><broken"},
    )
    document = extractor.extract(deck)
    warnings = document.slides[0].warnings
    assert any("malformed relationships part" in w for w in warnings)
    assert "still-extracted" in [p.text for o in document.slides[0].objects for p in o.paragraphs]


def test_external_relationship_is_never_resolved_into_the_package(extractor):
    """``TargetMode="External"`` must never be turned into a package path."""

    external_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="rIdImg" Type="{REL_IMAGE}" '
        'Target="https://example.invalid/pic.png" TargetMode="External"/>'
        "</Relationships>"
    )
    deck = build_pptx(
        [[picture_shape(4, "Linked", rel_id="rIdImg")]],
        extra_entries={"ppt/slides/_rels/slide1.xml.rels": external_rels.encode()},
    )
    document = extractor.extract(deck)
    pictures = [o for o in document.slides[0].objects if o.kind == "picture"]
    assert pictures and pictures[0].media_ref is None
    assert not any("example.invalid" in str(o.media_ref) for s in document.slides for o in s.objects)


def test_ir_is_schema_versioned(extractor):
    document = extractor.extract(simple_pptx())
    data = document.to_dict()
    assert data["schema_version"].startswith("content-ir/")
    assert data["provenance"]["extractor"]
    assert data["provenance"]["extractor_version"]


def test_bounds_can_be_normalized_to_the_canvas(extractor):
    from app.compiler.models.ir import Bounds

    deck = build_pptx(
        [[text_shape(2, "A", text="one", x=1524000, y=0, cx=1524000, cy=1524000)]],
        width_emu=3048000,
        height_emu=3048000,
    )
    document = extractor.extract(deck)
    bounds = document.slides[0].objects[0].bounds
    assert bounds.normalized(document.slide_width, document.slide_height) == {
        "x": 0.5,
        "y": 0.0,
        "width": 0.5,
        "height": 0.5,
    }


def test_bounds_normalization_tolerates_unknown_components():
    from app.compiler.models.ir import Bounds

    assert Bounds().normalized(1000, 1000) == {
        "x": None,
        "y": None,
        "width": None,
        "height": None,
    }
    assert Bounds(x=1).normalized(0, 0)["x"] is None
