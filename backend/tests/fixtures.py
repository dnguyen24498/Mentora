"""Builders for minimal-but-structurally-valid OOXML .pptx packages.

Used by tests instead of binary fixtures so the expected structure is explicit.
Only the parts the extractor reads are produced.
"""

from __future__ import annotations

import base64
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


def shape_xml(
    shape_id: int,
    name: str,
    *,
    sp_pr: str = "",
    tx_body: str = "",
    placeholder: str | None = None,
    ph_idx: str | None = None,
) -> str:
    """A ``p:sp`` with caller-supplied ``spPr``/``txBody`` (V0-018 styling tests)."""

    if placeholder is None:
        ph = ""
    elif ph_idx is None:
        ph = f'<p:ph type="{placeholder}"/>'
    else:
        ph = f'<p:ph type="{placeholder}" idx="{ph_idx}"/>'
    body = f"<p:txBody>{tx_body}</p:txBody>" if tx_body else ""
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{shape_id}" name="{name}"/>'
        f"<p:cNvSpPr/><p:nvPr>{ph}</p:nvPr></p:nvSpPr>"
        f"<p:spPr>{sp_pr}</p:spPr>{body}</p:sp>"
    )


def paragraph_xml(
    text: str,
    *,
    level: int = 0,
    p_pr: str = "",
    p_pr_attrs: str = "",
    r_pr: str = "",
    r_pr_attrs: str = "",
) -> str:
    """An ``a:p`` with optional paragraph attributes/children and run properties."""

    attributes = f"{lvl(level)}{p_pr_attrs}"
    properties = f"<a:pPr{attributes}>{p_pr}</a:pPr>" if (attributes or p_pr) else ""
    run = f'<a:rPr lang="en-US"{r_pr_attrs}>{r_pr}</a:rPr>' if (r_pr_attrs or r_pr) else "<a:rPr/>"
    return f"<a:p>{properties}<a:r>{run}<a:t>{escape(text)}</a:t></a:r></a:p>"


def lvl(level: int) -> str:
    return f' lvl="{level}"' if level else ""


def xfrm(x: int, y: int, cx: int, cy: int, *, extra: str = "") -> str:
    return f'<a:xfrm{extra}><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'


def simple_pptx(text: str = "Hello world", **kwargs) -> bytes:
    """One slide with a title and a body paragraph."""

    shapes = [
        text_shape(2, "Title 1", text=text, placeholder="title"),
        text_shape(3, "Body 1", text="Body line"),
    ]
    return build_pptx([shapes], **kwargs)


# -- themed deck (V0-018): theme + master + layout --------------------------------
REL_THEME = f"{R_NS}/theme"
REL_SLIDE_MASTER = f"{R_NS}/slideMaster"
REL_SLIDE_LAYOUT = f"{R_NS}/slideLayout"

#: A 1x1 PNG, so picture tests carry real image bytes rather than a placeholder.
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACklEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg=="
)

THEME_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<a:theme xmlns:a="{A_NS}" name="Test Theme"><a:themeElements>'
    '<a:clrScheme name="Test">'
    '<a:dk1><a:sysClr val="windowText" lastClr="111111"/></a:dk1>'
    '<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>'
    '<a:dk2><a:srgbClr val="44546A"/></a:dk2>'
    '<a:lt2><a:srgbClr val="E7E6E6"/></a:lt2>'
    '<a:accent1><a:srgbClr val="1B3A8C"/></a:accent1>'
    '<a:accent2><a:srgbClr val="0A6EBD"/></a:accent2>'
    '<a:accent3><a:srgbClr val="4FB3F0"/></a:accent3>'
    '<a:accent4><a:srgbClr val="7F7F7F"/></a:accent4>'
    '<a:accent5><a:srgbClr val="7F7F7F"/></a:accent5>'
    '<a:accent6><a:srgbClr val="7F7F7F"/></a:accent6>'
    '<a:hlink><a:srgbClr val="0563C1"/></a:hlink>'
    '<a:folHlink><a:srgbClr val="954F72"/></a:folHlink>'
    "</a:clrScheme>"
    '<a:fontScheme name="Test">'
    '<a:majorFont><a:latin typeface="Major Sans"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>'
    '<a:minorFont><a:latin typeface="Minor Sans"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont>'
    "</a:fontScheme>"
    '<a:fmtScheme name="Test"><a:fillStyleLst/><a:lnStyleLst/><a:effectStyleLst/>'
    "<a:bgFillStyleLst/></a:fmtScheme>"
    "</a:themeElements></a:theme>"
)

_MASTER_DEFAULT_CLR_MAP = (
    'bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" '
    'accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" '
    'hlink="hlink" folHlink="folHlink"'
)


def slide_master_xml(*, clr_map: str = _MASTER_DEFAULT_CLR_MAP) -> str:
    """A slide master with a colour map, a background, and ``p:txStyles``.

    ``titleStyle`` gives 40 pt bold in the theme's major font; ``bodyStyle``
    gives 18 pt with a bullet and a hanging indent; ``otherStyle`` gives 18 pt.
    """

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<p:sldMaster {_NSDECL}><p:cSld>'
        '<p:bg><p:bgPr><a:solidFill><a:schemeClr val="bg1"/></a:solidFill></p:bgPr></p:bg>'
        "<p:spTree>"
        '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>'
        '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Master Title"/>'
        '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>'
        '<p:spPr><a:xfrm><a:off x="457200" y="274638"/><a:ext cx="8229600" cy="1143000"/></a:xfrm></p:spPr>'
        '<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:endParaRPr lang="en-US"/></a:p></p:txBody></p:sp>'
        '<p:sp><p:nvSpPr><p:cNvPr id="3" name="Master Body"/>'
        '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
        '<p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr>'
        '<p:spPr><a:xfrm><a:off x="457200" y="1600200"/><a:ext cx="8229600" cy="4525963"/></a:xfrm></p:spPr>'
        '<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:endParaRPr lang="en-US"/></a:p></p:txBody></p:sp>'
        "</p:spTree></p:cSld>"
        f"<p:clrMap {clr_map}/>"
        "<p:txStyles>"
        '<p:titleStyle><a:lvl1pPr algn="l"><a:defRPr sz="4000" b="1">'
        '<a:solidFill><a:schemeClr val="tx1"/></a:solidFill><a:latin typeface="+mj-lt"/>'
        "</a:defRPr></a:lvl1pPr></p:titleStyle>"
        '<p:bodyStyle><a:lvl1pPr marL="342900" indent="-342900"><a:buChar char="•"/>'
        '<a:defRPr sz="1800"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill>'
        '<a:latin typeface="+mn-lt"/></a:defRPr></a:lvl1pPr>'
        '<a:lvl2pPr marL="742950" indent="-285750"><a:buChar char="–"/>'
        '<a:defRPr sz="1600"/></a:lvl2pPr></p:bodyStyle>'
        '<p:otherStyle><a:lvl1pPr><a:defRPr sz="1800"/></a:lvl1pPr></p:otherStyle>'
        "</p:txStyles></p:sldMaster>"
    )


def slide_layout_xml() -> str:
    """A layout whose title/body placeholders carry slide geometry.

    The title placeholder deliberately sets no ``defRPr`` (so the master's 40 pt
    wins) while the body placeholder sets 14 pt (so the layout overrides the
    master's 18 pt) — the two halves of the text-style cascade.
    """

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<p:sldLayout {_NSDECL} type="title" preserve="1"><p:cSld>'
        "<p:spTree>"
        '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>'
        '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Layout Title"/>'
        '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>'
        '<p:spPr><a:xfrm><a:off x="838200" y="365125"/><a:ext cx="10515600" cy="1325563"/></a:xfrm></p:spPr>'
        '<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:endParaRPr lang="en-US"/></a:p></p:txBody></p:sp>'
        '<p:sp><p:nvSpPr><p:cNvPr id="3" name="Layout Body"/>'
        '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
        '<p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr>'
        '<p:spPr><a:xfrm><a:off x="838200" y="1825625"/><a:ext cx="10515600" cy="4351338"/></a:xfrm></p:spPr>'
        '<p:txBody><a:bodyPr/><a:lstStyle><a:lvl1pPr><a:defRPr sz="1400"/></a:lvl1pPr>'
        "</a:lstStyle><a:p><a:endParaRPr lang=\"en-US\"/></a:p></p:txBody></p:sp>"
        "</p:spTree></p:cSld></p:sldLayout>"
    )


def themed_slide_xml(shapes: list[str], *, background: str = "") -> str:
    header = (
        '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f"<p:sld {_NSDECL}><p:cSld>{background}<p:spTree>{header}"
        f"{''.join(shapes)}</p:spTree></p:cSld></p:sld>"
    )


def themed_pptx(
    shapes: list[str],
    *,
    background: str = "",
    image: bytes | None = None,
    display_slide: list[str] | None = None,
    master_xml: str | None = None,
    **kwargs,
) -> bytes:
    """Assemble a deck that inherits from a theme, master, and layout.

    ``display_slide`` replaces the slide's own shape list for the *parts* that do
    not need layout support (used to prove group transforms etc. in isolation).
    """

    slide_rels: list[tuple[str, str, str]] = [
        ("rIdLayout", REL_SLIDE_LAYOUT, "../slideLayouts/slideLayout1.xml")
    ]
    entries: dict[str, bytes] = {
        "ppt/theme/theme1.xml": THEME_XML.encode(),
        "ppt/slideMasters/slideMaster1.xml": (master_xml or slide_master_xml()).encode(),
        "ppt/slideMasters/_rels/slideMaster1.xml.rels": _rels_xml(
            [("rId1", REL_THEME, "../theme/theme1.xml")]
        ).encode(),
        "ppt/slideLayouts/slideLayout1.xml": slide_layout_xml().encode(),
        "ppt/slideLayouts/_rels/slideLayout1.xml.rels": _rels_xml(
            [("rId1", REL_SLIDE_MASTER, "../slideMasters/slideMaster1.xml")]
        ).encode(),
        "ppt/slides/slide1.xml": themed_slide_xml(
            display_slide if display_slide is not None else shapes, background=background
        ).encode(),
    }
    if image is not None:
        entries["ppt/media/image1.png"] = image
        slide_rels.append(("rIdImg", REL_IMAGE, "../media/image1.png"))
    extra_entries = kwargs.pop("extra_entries", None) or {}
    caller_rels = kwargs.pop("extra_slide_rels", None) or {}
    slide_rels.extend(caller_rels.get(1, []))
    return build_pptx(
        [shapes],
        extra_slide_rels={1: slide_rels},
        extra_entries={**entries, **extra_entries},
        **kwargs,
    )
