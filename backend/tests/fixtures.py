"""Builders for minimal-but-structurally-valid OOXML .pptx packages.

Used by tests instead of binary fixtures so the expected structure is explicit.
Only the parts the extractor reads are produced.
"""

from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
CHART_NS = "http://schemas.openxmlformats.org/drawingml/2006/chart"

REL_SLIDE = f"{R_NS}/slide"
REL_NOTES = f"{R_NS}/notesSlide"
REL_IMAGE = f"{R_NS}/image"
REL_CHART = f"{R_NS}/chart"
REL_OFFICE_DOCUMENT = f"{R_NS}/officeDocument"

_NSDECL = f'xmlns:a="{A_NS}" xmlns:r="{R_NS}" xmlns:p="{P_NS}" xmlns:c="{CHART_NS}"'


def _para(level: int, text: str, font: str | None = None) -> str:
    ppr = f'<a:pPr lvl="{level}"/>' if level else ""
    rpr = f'<a:rPr lang="en-US"><a:latin typeface="{font}"/></a:rPr>' if font else ""
    # Text is escaped like a real part: raw "&"/"<" would make the package malformed.
    return (
        f"<a:p>{ppr}<a:r>{rpr}<a:t>{escape(text)}</a:t></a:r></a:p>"
    )


def text_shape(
    shape_id: int,
    name: str,
    *,
    text: str | None = None,
    paragraphs: list[tuple[int, str]] | None = None,
    font: str | None = None,
    x: int = 0,
    y: int = 0,
    cx: int = 914400,
    cy: int = 914400,
    placeholder: str | None = None,
) -> str:
    ph = f'<p:ph type="{placeholder}"/>' if placeholder else ""
    body = "".join(
        _para(level, value, font) for level, value in (paragraphs or [(0, text or "")])
    )
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{shape_id}" name="{name}"/>'
        f"<p:cNvSpPr/><p:nvPr>{ph}</p:nvPr></p:nvSpPr>"
        f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm></p:spPr>'
        f"<p:txBody><a:bodyPr/><a:lstStyle/>{body}</p:txBody></p:sp>"
    )


def table_shape(
    shape_id: int,
    name: str,
    rows: list[list[str]],
    *,
    x: int = 0,
    y: int = 0,
    cx: int = 914400,
    cy: int = 914400,
) -> str:
    trs = ""
    for row in rows:
        cells = "".join(
            f'<a:tc><a:txBody><a:p><a:r><a:t>{cell}</a:t></a:r></a:p></a:txBody></a:tc>' for cell in row
        )
        trs += f"<a:tr>{cells}</a:tr>"
    return (
        f'<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="{shape_id}" name="{name}"/>'
        f"<p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr>"
        f'<p:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></p:xfrm>'
        f'<a:graphic><a:graphicData uri="{A_NS}/table"><a:tbl>{trs}</a:tbl></a:graphicData></a:graphic>'
        f"</p:graphicFrame>"
    )


def picture_shape(shape_id: int, name: str, rel_id: str = "rIdImg") -> str:
    return (
        f'<p:pic><p:nvPicPr><p:cNvPr id="{shape_id}" name="{name}"/>'
        f"<p:cNvPicPr/><p:nvPr/></p:nvPicPr>"
        f'<p:blipFill><a:blip r:embed="{rel_id}"/></p:blipFill>'
        f'<p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="914400" cy="914400"/></a:xfrm></p:spPr></p:pic>'
    )


def chart_shape(shape_id: int, name: str, rel_id: str = "rIdChart") -> str:
    """A ``p:graphicFrame`` wrapping a chart reference (no series data)."""

    return (
        f'<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="{shape_id}" name="{name}"/>'
        f"<p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr>"
        f'<p:xfrm><a:off x="0" y="0"/><a:ext cx="1828800" cy="914400"/></p:xfrm>'
        f'<a:graphic><a:graphicData uri="{CHART_NS}">'
        f'<c:chart r:id="{rel_id}"/>'
        f"</a:graphicData></a:graphic></p:graphicFrame>"
    )


def group_shape(
    shape_id: int,
    name: str,
    children: list[str],
    *,
    x: int = 0,
    y: int = 0,
    cx: int = 1828800,
    cy: int = 1828800,
) -> str:
    """A ``p:grpSp`` whose children are embedded directly, as PowerPoint writes them.

    PresentationML groups hold their shapes as *immediate children*; there is no
    nested ``p:spTree`` inside a group (``p:spTree`` exists once, at slide level).
    """

    return (
        f'<p:grpSp><p:nvGrpSpPr><p:cNvPr id="{shape_id}" name="{name}"/>'
        f"<p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>"
        f"<p:grpSpPr><a:xfrm><a:off x=\"{x}\" y=\"{y}\"/>"
        f'<a:ext cx="{cx}" cy="{cy}"/><a:chOff x="0" y="0"/>'
        f'<a:chExt cx="{cx}" cy="{cy}"/></a:xfrm></p:grpSpPr>'
        f"{''.join(children)}</p:grpSp>"
    )


def slide_xml(shapes: list[str]) -> str:
    header = (
        '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>'
    )
    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f"<p:sld {_NSDECL}><p:cSld><p:spTree>{header}{''.join(shapes)}</p:spTree></p:cSld></p:sld>"
    )


def notes_xml(text: str) -> str:
    notes_body = text_shape(2, "Notes Placeholder", text=text, placeholder="body")
    slide_number = text_shape(3, "Slide Number Placeholder", text="999", placeholder="sldNum")
    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f"<p:notes {_NSDECL}><p:cSld><p:spTree>{notes_body}{slide_number}</p:spTree></p:cSld></p:notes>"
    )


def _rels_xml(rels: list[tuple[str, str, str]]) -> str:
    body = "".join(
        f'<Relationship Id="{rel_id}" Type="{rel_type}" Target="{target}"/>'
        for rel_id, rel_type, target in rels
    )
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{PKG_NS}">{body}</Relationships>'


def presentation_xml(slide_rel_ids: list[str], width_emu: int, height_emu: int) -> str:
    ids = "".join(
        f'<p:sldId id="{255 + index}" r:id="{rel_id}"/>'
        for index, rel_id in enumerate(slide_rel_ids, start=1)
    )
    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<p:presentation {_NSDECL}><p:sldIdLst>{ids}</p:sldIdLst>'
        f'<p:sldSz cx="{width_emu}" cy="{height_emu}"/></p:presentation>'
    )


def _content_types() -> str:
    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="{CT_NS}">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/ppt/presentation.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
        "</Types>"
    )


def build_pptx(
    slide_shapes: list[list[str]],
    *,
    width_emu: int = 12192000,
    height_emu: int = 6858000,
    notes: dict[int, str] | None = None,
    missing_slide: int | None = None,
    include_presentation: bool = True,
    include_content_types: bool = True,
    extra_slide_rels: dict[int, list[tuple[str, str, str]]] | None = None,
    extra_entries: dict[str, bytes] | None = None,
) -> bytes:
    """Assemble a .pptx. ``slide_shapes`` is a list of shape-XML lists (1 slide each)."""

    notes = notes or {}
    extra_slide_rels = extra_slide_rels or {}
    entries: dict[str, bytes] = {}

    slide_rel_ids: list[str] = []
    presentation_rels: list[tuple[str, str, str]] = []
    for index in range(1, len(slide_shapes) + 1):
        rel_id = f"rId{index}"
        slide_rel_ids.append(rel_id)
        presentation_rels.append((rel_id, REL_SLIDE, f"slides/slide{index}.xml"))
        if missing_slide == index:
            continue

        entries[f"ppt/slides/slide{index}.xml"] = slide_xml(slide_shapes[index - 1]).encode()

        slide_rels: list[tuple[str, str, str]] = []
        if index in notes:
            entries[f"ppt/notesSlides/notesSlide{index}.xml"] = notes_xml(notes[index]).encode()
            slide_rels.append(("rId1", REL_NOTES, f"../notesSlides/notesSlide{index}.xml"))
        slide_rels.extend(extra_slide_rels.get(index, []))
        if slide_rels:
            entries[f"ppt/slides/_rels/slide{index}.xml.rels"] = _rels_xml(slide_rels).encode()

    if include_presentation:
        entries["ppt/presentation.xml"] = presentation_xml(slide_rel_ids, width_emu, height_emu).encode()
    entries["ppt/_rels/presentation.xml.rels"] = _rels_xml(presentation_rels).encode()
    entries["_rels/.rels"] = _rels_xml([("rId1", REL_OFFICE_DOCUMENT, "ppt/presentation.xml")]).encode()
    if include_content_types:
        entries["[Content_Types].xml"] = _content_types().encode()
    entries.update(extra_entries or {})

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def simple_pptx(text: str = "Hello world", **kwargs) -> bytes:
    """One slide with a title and a body paragraph."""

    shapes = [
        text_shape(2, "Title 1", text=text, placeholder="title"),
        text_shape(3, "Body 1", text="Body line"),
    ]
    return build_pptx([shapes], **kwargs)
