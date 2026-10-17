"""V0-019 v7: the art a slide inherits from its layout and master.

A deck keeps its shared chrome — the crest, the badge, a rule, a static label —
on the *layout* (or the master), not on every slide. PowerPoint paints that art
under the slide's own objects, so a renderer that draws only ``p:sld`` loses it:
on the real reference deck the two logos at the top right of 26 slides live
nowhere but the layout.

Inheritance is deliberately **not** slide content: it carries no reading order of
its own and never contributes to the slide's text or object count. A layout or
master *placeholder* is not art either — it is a definition the slide's own
placeholder replaces, and PowerPoint does not render the empty ones.
"""

from __future__ import annotations

from base64 import b64encode

from app.compiler.extractors.pptx import PptxExtractor
from app.compiler.media import document_media_refs, read_media_parts
from app.compiler.renderers.base import RenderBudget, RenderConfig, RenderRequest
from app.compiler.renderers.structural import StructuralSvgRenderer
from tests.fixtures import (
    LAYOUT_ART_PART,
    MASTER_ART_PART,
    inherited_art_pptx,
    tiny_png,
)


def _render(object_store, deck: bytes):
    config = RenderConfig()
    renderer = StructuralSvgRenderer(object_store, config)
    document = PptxExtractor().extract(deck)
    return document, renderer.render(
        RenderRequest(
            document=document,
            identity=renderer.identity(),
            media=read_media_parts(deck, document_media_refs(document)),
        ),
        budget=RenderBudget(config.deadline_seconds, max_attempts=1),
    )


def _svg(object_store, report, order: int = 0) -> str:
    return object_store.get(report.scene(order).asset_ref).decode()


def _data_uri(rgb: tuple[int, int, int]) -> str:
    return "data:image/png;base64," + b64encode(tiny_png(rgb)).decode()


# -- extraction ---------------------------------------------------------------------
def test_master_then_layout_art_is_inherited_in_paint_order():
    """The master's shapes paint first, then the layout's, then the slide's."""

    scene = PptxExtractor().extract(inherited_art_pptx()).slides[0]

    assert [obj.name for obj in scene.inherited_objects] == [
        "Crest",
        "Badge",
        "Layout rule",
    ]
    # Each part resolves *its own* pictures, exactly as with a picture background:
    # the layout's badge is the layout's relationship, not the slide's.
    assert scene.inherited_objects[0].media_ref == MASTER_ART_PART
    assert scene.inherited_objects[1].media_ref == LAYOUT_ART_PART


def test_layout_placeholders_are_not_inherited():
    """A placeholder is a definition the slide replaces, not art."""

    scene = PptxExtractor().extract(inherited_art_pptx()).slides[0]

    assert scene.inherited_objects  # the art really is there
    assert all(obj.placeholder is None for obj in scene.inherited_objects)
    # ...and the layout's title/body placeholders did not become objects.
    assert [obj.name for obj in scene.objects] == ["Title"]


def test_inherited_art_is_not_the_slides_own_content():
    """It is chrome: no slide reading order, no slide text, no slide object."""

    scene = PptxExtractor().extract(inherited_art_pptx()).slides[0]

    assert [obj.name for obj in scene.objects] == ["Title"]
    assert [obj.reading_order for obj in scene.objects] == [0]
    assert [obj.reading_order for obj in scene.inherited_objects] == [0, 1, 2]


def test_the_slide_can_hide_inherited_art():
    """``p:sld/@showMasterSp="0"`` switches the whole inherited layer off."""

    scene = PptxExtractor().extract(
        inherited_art_pptx(slide_attrs='showMasterSp="0"')
    ).slides[0]

    assert scene.inherited_objects == []
    assert [obj.name for obj in scene.objects] == ["Title"]


def test_the_layout_can_hide_the_masters_art_only():
    """``p:sldLayout/@showMasterSp="0"`` hides the master's shapes, not its own."""

    scene = PptxExtractor().extract(
        inherited_art_pptx(layout_attrs='showMasterSp="0"')
    ).slides[0]

    assert [obj.name for obj in scene.inherited_objects] == ["Badge", "Layout rule"]


# -- rendering ----------------------------------------------------------------------
def test_inherited_art_is_drawn_under_the_slides_own_objects(object_store):
    """Paint order is the whole point: chrome sits behind the content."""

    deck = inherited_art_pptx()
    document = PptxExtractor().extract(deck)
    # The compiler must request the bytes, or the renderer cannot inline them.
    refs = document_media_refs(document)
    assert MASTER_ART_PART in refs
    assert LAYOUT_ART_PART in refs

    svg = _svg(object_store, _render(object_store, deck)[1])

    crest, badge = _data_uri((255, 0, 0)), _data_uri((0, 0, 255))
    assert crest in svg and badge in svg
    assert "#0A6EBD" in svg  # the layout rule's accent2 fill, drawn too
    assert svg.index(crest) < svg.index(badge) < svg.index("#0A6EBD") < svg.index("<text")


def test_inherited_art_is_absent_when_the_slide_hides_it(object_store):
    deck = inherited_art_pptx(slide_attrs='showMasterSp="0"')
    svg = _svg(object_store, _render(object_store, deck)[1])

    assert "data:image/png" not in svg
    assert "#0A6EBD" not in svg
    assert "<text" in svg  # the slide's own content is untouched


def test_the_package_scene_document_carries_the_inherited_art():
    """The package must describe what was drawn, not just the slide's own objects."""

    data = PptxExtractor().extract(inherited_art_pptx()).slides[0].to_dict()

    assert [obj["name"] for obj in data["inherited_objects"]] == [
        "Crest",
        "Badge",
        "Layout rule",
    ]
    assert data["inherited_objects"][1]["media_ref"] == LAYOUT_ART_PART
    # ...and a deck without inherited art does not grow an empty key.
    plain = PptxExtractor().extract(
        inherited_art_pptx(slide_attrs='showMasterSp="0"')
    ).slides[0].to_dict()
    assert "inherited_objects" not in plain
