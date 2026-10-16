"""Deterministic PPTX (OOXML) structural extractor.

Dependency-free: reads the package with ``zipfile`` and parses parts with
``xml.etree``. No macro/script/OLE is ever executed and archive expansion is
bounded (``docs/architecture/04_CONTENT_COMPILER.md`` security/reproducibility).
Produces :class:`ContentIRDocument`.

Scope = V0-004 "structural extraction": slide order/dimensions, text runs and
notes, images, shapes, groups, tables, chart/media refs, normalized bounds,
reading order, stable source IDs, warnings/provenance. Vision analysis, SmartArt
reconstruction, and native animation are out of scope.

Degradation policy: a damaged package raises (stable code, no partial output),
while a *locally* damaged part (unresolvable relationship, malformed ``.rels``,
unmodelled element) degrades only the affected object and is surfaced as a
warning, so one bad relationship can never drop a slide.
"""

from __future__ import annotations

import posixpath
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import replace
from io import BytesIO
from typing import Optional

from app.common.errors import ErrorCode, error
from app.compiler.models.ir import (
    Bounds,
    ContentIRDocument,
    EXTRACTOR_NAME,
    EXTRACTOR_VERSION,
    FIDELITY_STRUCTURAL,
    ShapeObject,
    SlideScene,
    TextParagraph,
    TextRun,
)

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CHART = "http://schemas.openxmlformats.org/drawingml/2006/chart"

CONTENT_TYPES_PART = "[Content_Types].xml"
PRESENTATION_PART = "ppt/presentation.xml"

#: 16:9 default used only when a package omits ``p:sldSz``.
DEFAULT_SLIDE_WIDTH_EMU = 12192000
DEFAULT_SLIDE_HEIGHT_EMU = 6858000


def _t(ns: str, local: str) -> str:
    return f"{{{ns}}}{local}"


def _child(el: Optional[ET.Element], ns: str, local: str) -> Optional[ET.Element]:
    return el.find(_t(ns, local)) if el is not None else None


def _children(el: Optional[ET.Element], ns: str, local: str) -> list[ET.Element]:
    return el.findall(_t(ns, local)) if el is not None else []


#: ``p:spTree`` / ``p:grpSp`` header elements that carry no slide content.
_NON_VISUAL_TAGS = frozenset({_t(P, "nvGrpSpPr"), _t(P, "grpSpPr")})

#: Character-property elements that may carry a typeface.
_CHAR_PROPS = frozenset({_t(A, "rPr"), _t(A, "defRPr"), _t(A, "endParaRPr")})


def _rels_part_for(part: str) -> str:
    directory, base = posixpath.split(part)
    return posixpath.join(directory, "_rels", f"{base}.rels")


def _resolve_target(part: str, target: str) -> str:
    return posixpath.normpath(posixpath.join(posixpath.dirname(part), target))


def _typeface_from(rpr: Optional[ET.Element]) -> Optional[str]:
    """Effective typeface of a character-property element.

    Theme references (``+mj-lt`` / ``+mn-lt``) are placeholders resolved by the
    theme part, so they are reported as "unknown" instead of being mistaken for
    a font family (which would produce a bogus missing-font warning later).
    """

    if rpr is None:
        return None
    for tag in ("latin", "ea", "cs"):
        node = _child(rpr, A, tag)
        if node is None:
            continue
        typeface = node.get("typeface")
        if typeface and not typeface.startswith("+"):
            return typeface
    return None


def _typefaces_in(element: Optional[ET.Element]) -> list[str]:
    """Distinct typefaces used anywhere inside ``element`` (sorted)."""

    if element is None:
        return []
    found: set[str] = set()
    for node in element.iter():
        if node.tag in _CHAR_PROPS:
            typeface = _typeface_from(node)
            if typeface:
                found.add(typeface)
    return sorted(found)


class PptxExtractor:
    def __init__(
        self,
        *,
        max_entries: int = 5000,
        max_uncompressed_bytes: int = 500 * 1024 * 1024,
    ) -> None:
        self._max_entries = max_entries
        self._max_uncompressed_bytes = max_uncompressed_bytes
        self._archive: Optional[zipfile.ZipFile] = None

    # -- public API -------------------------------------------------------------
    def extract(
        self,
        data: bytes,
        *,
        source_ref: Optional[dict] = None,
        source_sha256: Optional[str] = None,
    ) -> ContentIRDocument:
        source_ref = dict(source_ref or {})
        if source_sha256:
            source_ref.setdefault("sha256", source_sha256)

        try:
            archive = zipfile.ZipFile(BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise error(ErrorCode.INVALID_PPTX_PACKAGE, "not a valid OOXML/zip package") from exc

        self._archive = archive
        with archive:
            self._guard_archive(archive)
            names = set(archive.namelist())
            if CONTENT_TYPES_PART not in names or PRESENTATION_PART not in names:
                raise error(
                    ErrorCode.INVALID_PPTX_PACKAGE,
                    "package is missing OOXML presentation parts",
                )

            warnings: list[str] = []
            presentation = self._read_xml(archive, PRESENTATION_PART)
            rels = self._read_rels(archive, _rels_part_for(PRESENTATION_PART), warnings)
            width, height, size_warnings = self._slide_size(presentation)
            warnings.extend(size_warnings)
            slide_parts = self._slide_parts(presentation, rels, names, warnings)

            slides: list[SlideScene] = []
            for order, part in enumerate(slide_parts):
                scene = self._extract_scene(archive, part, order, width, height, source_ref)
                slides.append(scene)
                # Roll slide-level warnings up to the document for callers that
                # only look at the top level.
                warnings.extend(scene.warnings)

        if not slides:
            warnings.append("presentation contains no slides")

        return ContentIRDocument(
            source_ref=source_ref,
            slide_width=width,
            slide_height=height,
            slides=slides,
            warnings=warnings,
            provenance={
                "extractor": EXTRACTOR_NAME,
                "extractor_version": EXTRACTOR_VERSION,
                "source_sha256": source_sha256,
            },
        )

    # -- guards / helpers -------------------------------------------------------
    def _guard_archive(self, archive: zipfile.ZipFile) -> None:
        infos = archive.infolist()
        if len(infos) > self._max_entries:
            raise error(ErrorCode.ARCHIVE_TOO_LARGE, "archive has too many entries")
        total = sum(info.file_size for info in infos)
        if total > self._max_uncompressed_bytes:
            raise error(ErrorCode.ARCHIVE_TOO_LARGE, "archive expands beyond the size budget")

    def _read_xml(self, archive: zipfile.ZipFile, part: str) -> ET.Element:
        try:
            payload = archive.read(part)
        except KeyError as exc:
            raise error(ErrorCode.INVALID_PPTX_PACKAGE, f"missing part {part!r}") from exc
        try:
            return ET.fromstring(payload)
        except ET.ParseError as exc:
            raise error(ErrorCode.INVALID_PPTX_PACKAGE, f"malformed XML in {part!r}") from exc

    def _read_rels(
        self,
        archive: zipfile.ZipFile,
        rels_part: str,
        warnings: Optional[list[str]] = None,
    ) -> dict[str, str]:
        """Relationship id -> target. A damaged ``.rels`` degrades to no rels.

        Raising here would discard an otherwise readable slide, so a malformed
        relationship part only produces a warning (V0-004 "corrupted
        relationship fixtures").
        """

        if rels_part not in archive.namelist():
            return {}
        try:
            root = ET.fromstring(archive.read(rels_part))
        except (ET.ParseError, KeyError) as exc:
            if warnings is not None:
                warnings.append(f"malformed relationships part {rels_part!r}: {exc}")
            return {}
        rels: dict[str, str] = {}
        for rel in root.findall(_t(PKG_REL, "Relationship")):
            rel_id = rel.get("Id")
            target = rel.get("Target")
            if not rel_id or not target:
                continue
            if rel.get("TargetMode") == "External":
                # Nothing to resolve inside the package; never fetched.
                continue
            rels[rel_id] = target
        return rels

    def _slide_size(self, presentation: ET.Element) -> tuple[int, int, list[str]]:
        size = _child(presentation, P, "sldSz")
        if size is None:
            return DEFAULT_SLIDE_WIDTH_EMU, DEFAULT_SLIDE_HEIGHT_EMU, ["slide size missing; used default"]
        try:
            return int(size.get("cx", DEFAULT_SLIDE_WIDTH_EMU)), int(
                size.get("cy", DEFAULT_SLIDE_HEIGHT_EMU)
            ), []
        except ValueError:
            return DEFAULT_SLIDE_WIDTH_EMU, DEFAULT_SLIDE_HEIGHT_EMU, ["slide size unparsable; used default"]

    def _slide_parts(
        self,
        presentation: ET.Element,
        rels: dict[str, str],
        names: set[str],
        warnings: list[str],
    ) -> list[Optional[str]]:
        """Return slide part names in presentation order (``None`` = broken ref)."""

        parts: list[Optional[str]] = []
        id_list = _child(presentation, P, "sldIdLst")
        for slide_id in _children(id_list, P, "sldId"):
            rel_id = slide_id.get(_t(R, "id"))
            target = rels.get(rel_id) if rel_id else None
            if target is None:
                parts.append(None)
                continue
            part = _resolve_target(PRESENTATION_PART, target)
            if part not in names:
                warnings.append(f"slide part {part!r} referenced but absent")
                parts.append(None)
                continue
            parts.append(part)
        return parts

    # -- scene extraction -------------------------------------------------------
    def _extract_scene(
        self,
        archive: zipfile.ZipFile,
        part: Optional[str],
        order: int,
        width: int,
        height: int,
        source_ref: dict,
    ) -> SlideScene:
        if part is None:
            return SlideScene(
                scene_id=f"ppt/slides/slide{order + 1}.xml",
                source_ref={**source_ref, "part": None},
                order=order,
                width=width,
                height=height,
                fallback_asset=None,
                fidelity=FIDELITY_STRUCTURAL,
                objects=[],
                notes=None,
                warnings=["slide part missing; retained placeholder to avoid omission"],
                provenance={"extractor": EXTRACTOR_NAME, "extractor_version": EXTRACTOR_VERSION},
            )

        slide = self._read_xml(archive, part)
        warnings: list[str] = []
        sp_tree = _child(_child(slide, P, "cSld"), P, "spTree")
        objects = self._walk(sp_tree, part, warnings)
        # Reading order is the flattened walk order; make it explicit so
        # downstream stages do not have to infer it from list position.
        objects = [replace(obj, reading_order=index) for index, obj in enumerate(objects)]
        notes = self._extract_notes(archive, part, warnings)
        provenance = {
            "extractor": EXTRACTOR_NAME,
            "extractor_version": EXTRACTOR_VERSION,
            "part": part,
        }
        return SlideScene(
            scene_id=part,
            source_ref={**source_ref, "part": part},
            order=order,
            width=width,
            height=height,
            fallback_asset=None,
            fidelity=FIDELITY_STRUCTURAL,
            objects=objects,
            notes=notes,
            warnings=warnings,
            provenance=provenance,
        )

    def _walk(
        self,
        container: Optional[ET.Element],
        part: str,
        warnings: list[str],
        depth: int = 0,
    ) -> list[ShapeObject]:
        """Collect the shape objects directly held by ``container``.

        ``container`` is a slide ``p:spTree`` or a ``p:grpSp``. Both hold their
        children as immediate elements — a group does **not** wrap its shapes in
        a nested ``p:spTree`` (that exists only once, at the slide level).
        ``depth`` records how deep a shape sits inside nested groups.
        """

        objects: list[ShapeObject] = []
        if container is None:
            return objects
        for child in list(container):
            tag = child.tag
            if tag in _NON_VISUAL_TAGS:
                continue
            if tag == _t(P, "grpSp"):
                # Emit the group, then its (flattened) contents one level deeper.
                objects.append(self._extract_group(child, part, depth))
                objects.extend(self._walk(child, part, warnings, depth + 1))
            elif tag == _t(P, "sp"):
                objects.append(self._extract_shape(child, part, depth))
            elif tag == _t(P, "pic"):
                objects.append(self._extract_picture(child, part, warnings, depth))
            elif tag == _t(P, "graphicFrame"):
                objects.append(self._extract_graphic_frame(child, part, warnings, depth))
            elif tag == _t(P, "cxnSp"):
                objects.append(self._extract_connector(child, part, depth))
            else:
                # Surface containers we do not model instead of dropping them
                # silently (e.g. p:contentPart, mc:AlternateContent).
                warnings.append(
                    f"unsupported element <{tag.rsplit('}', 1)[-1]}> in {part!r}; skipped"
                )
        return objects

    def _shape_identity(self, element: ET.Element, part: str) -> tuple[str, str, Optional[str]]:
        nv = _child(element, P, "nvSpPr")
        if nv is None:
            nv = _child(element, P, "nvPicPr")
        c_nv_pr = _child(nv, P, "cNvPr")
        shape_id = c_nv_pr.get("id", "") if c_nv_pr is not None else ""
        name = c_nv_pr.get("name", "") if c_nv_pr is not None else ""
        placeholder = None
        if nv is not None:
            ph = _child(_child(nv, P, "nvPr"), P, "ph")
            if ph is not None:
                placeholder = ph.get("type", "body")
        return f"{part}#{shape_id}", name, placeholder

    def _bounds(self, element: ET.Element) -> Optional[Bounds]:
        sp_pr = _child(element, P, "spPr")
        if sp_pr is None:
            sp_pr = _child(element, P, "grpSpPr")
        xfrm = _child(sp_pr, A, "xfrm")
        if xfrm is None:
            return None
        off = _child(xfrm, A, "off")
        ext = _child(xfrm, A, "ext")
        return Bounds(
            x=int(off.get("x")) if off is not None and off.get("x") else None,
            y=int(off.get("y")) if off is not None and off.get("y") else None,
            width=int(ext.get("cx")) if ext is not None and ext.get("cx") else None,
            height=int(ext.get("cy")) if ext is not None and ext.get("cy") else None,
        )

    def _paragraphs(self, element: ET.Element) -> list[TextParagraph]:
        """Paragraphs with their runs, so run-level text and fonts survive."""

        tx_body = _child(element, P, "txBody")
        if tx_body is None:
            return []
        result: list[TextParagraph] = []
        for para in _children(tx_body, A, "p"):
            p_pr = _child(para, A, "pPr")
            level = int(p_pr.get("lvl", "0")) if p_pr is not None and p_pr.get("lvl") else 0
            # Paragraph-level default character properties apply to runs that
            # do not override them.
            default_typeface = _typeface_from(_child(p_pr, A, "defRPr"))
            runs: list[TextRun] = []
            for run in _children(para, A, "r"):
                for run_text in _children(run, A, "t"):
                    if run_text.text is None:
                        continue
                    typeface = _typeface_from(_child(run, A, "rPr")) or default_typeface
                    runs.append(TextRun(text=run_text.text, font=typeface))
            text = "".join(run.text for run in runs)
            if text:
                result.append(TextParagraph(level=level, text=text, runs=runs))
        return result

    def _extract_shape(self, element: ET.Element, part: str, depth: int = 0) -> ShapeObject:
        source_id, name, placeholder = self._shape_identity(element, part)
        paragraphs = self._paragraphs(element)
        return ShapeObject(
            source_id=source_id,
            kind="text" if paragraphs else "shape",
            name=name,
            placeholder=placeholder,
            bounds=self._bounds(element),
            paragraphs=paragraphs,
            fonts=_typefaces_in(element),
            depth=depth,
        )

    def _extract_connector(self, element: ET.Element, part: str, depth: int = 0) -> ShapeObject:
        source_id, name, placeholder = self._shape_identity(element, part)
        return ShapeObject(
            source_id=source_id,
            kind="connector",
            name=name,
            placeholder=placeholder,
            bounds=self._bounds(element),
            depth=depth,
        )

    def _extract_group(self, element: ET.Element, part: str, depth: int = 0) -> ShapeObject:
        nv = _child(element, P, "nvGrpSpPr")
        c_nv_pr = _child(nv, P, "cNvPr")
        shape_id = c_nv_pr.get("id", "") if c_nv_pr is not None else ""
        name = c_nv_pr.get("name", "") if c_nv_pr is not None else ""
        return ShapeObject(
            source_id=f"{part}#{shape_id}",
            kind="group",
            name=name,
            bounds=self._bounds(element),
            depth=depth,
        )

    def _extract_picture(
        self,
        element: ET.Element,
        part: str,
        warnings: list[str],
        depth: int = 0,
    ) -> ShapeObject:
        source_id, name, placeholder = self._shape_identity(element, part)
        media_ref = None
        blip = element.find(f".//{_t(A, 'blip')}")
        if blip is not None:
            rel_id = blip.get(_t(R, "embed")) or blip.get(_t(R, "link"))
            media_ref = self._resolve_rel(part, rel_id, warnings) if rel_id else None
            if rel_id and media_ref is None:
                warnings.append(f"picture on {part!r} has no resolvable image reference")
        return ShapeObject(
            source_id=source_id,
            kind="picture",
            name=name,
            placeholder=placeholder,
            bounds=self._bounds(element),
            media_ref=media_ref,
            depth=depth,
        )

    def _extract_graphic_frame(
        self,
        element: ET.Element,
        part: str,
        warnings: list[str],
        depth: int = 0,
    ) -> ShapeObject:
        nv = _child(element, P, "nvGraphicFramePr")
        c_nv_pr = _child(nv, P, "cNvPr")
        shape_id = c_nv_pr.get("id", "") if c_nv_pr is not None else ""
        name = c_nv_pr.get("name", "") if c_nv_pr is not None else ""
        xfrm = _child(element, P, "xfrm")
        bounds = None
        if xfrm is not None:
            off = _child(xfrm, A, "off")
            ext = _child(xfrm, A, "ext")
            bounds = Bounds(
                x=int(off.get("x")) if off is not None and off.get("x") else None,
                y=int(off.get("y")) if off is not None and off.get("y") else None,
                width=int(ext.get("cx")) if ext is not None and ext.get("cx") else None,
                height=int(ext.get("cy")) if ext is not None and ext.get("cy") else None,
            )

        table = element.find(f".//{_t(A, 'tbl')}")
        if table is not None:
            rows: list[list[str]] = []
            for row in _children(table, A, "tr"):
                cells: list[str] = []
                for cell in _children(row, A, "tc"):
                    text = "".join(
                        t.text or ""
                        for t in cell.findall(f".//{_t(A, 't')}")
                    )
                    cells.append(text)
                rows.append(cells)
            return ShapeObject(
                source_id=f"{part}#{shape_id}",
                kind="table",
                name=name,
                bounds=bounds,
                table=rows,
                fonts=_typefaces_in(table),
                depth=depth,
            )

        # A chart frame references its definition part; keep the reference even
        # though the series data itself is out of scope (vision/chart semantics).
        chart = element.find(f".//{_t(CHART, 'chart')}")
        if chart is not None:
            rel_id = chart.get(_t(R, "id"))
            chart_ref = self._resolve_rel(part, rel_id, warnings) if rel_id else None
            if rel_id and chart_ref is None:
                warnings.append(f"chart on {part!r} has no resolvable chart reference")
            return ShapeObject(
                source_id=f"{part}#{shape_id}",
                kind="chart",
                name=name,
                bounds=bounds,
                media_ref=chart_ref,
                depth=depth,
            )

        graphic_data = element.find(f".//{_t(A, 'graphicData')}")
        uri = graphic_data.get("uri", "") if graphic_data is not None else ""
        return ShapeObject(
            source_id=f"{part}#{shape_id}",
            kind="graphicFrame",
            name=name,
            bounds=bounds,
            depth=depth,
        )

    def _resolve_rel(self, part: str, rel_id: str, warnings: list[str]) -> Optional[str]:
        rels = self._read_rels(self._archive, _rels_part_for(part), warnings) if self._archive else {}
        target = rels.get(rel_id)
        if target is None:
            warnings.append(f"unresolved relationship {rel_id!r} in {part!r}")
            return None
        resolved = _resolve_target(part, target)
        if self._archive is not None and resolved not in self._archive.namelist():
            # Keep the reference (it is still provenance) but say it is broken.
            warnings.append(f"referenced part {resolved!r} is absent from the package")
        return resolved

    def _extract_notes(
        self, archive: zipfile.ZipFile, slide_part: str, warnings: list[str]
    ) -> Optional[str]:
        rels = self._read_rels(archive, _rels_part_for(slide_part), warnings)
        for target in rels.values():
            if "notesSlide" not in target:
                continue
            notes_part = _resolve_target(slide_part, target)
            if notes_part not in archive.namelist():
                warnings.append(f"notes part {notes_part!r} referenced but absent")
                continue
            notes_root = self._read_xml(archive, notes_part)
            sp_tree = _child(_child(notes_root, P, "cSld"), P, "spTree")
            lines: list[str] = []
            for shape in _children(sp_tree, P, "sp"):
                _sid, _name, placeholder = self._shape_identity(shape, notes_part)
                if placeholder == "sldNum":
                    continue
                lines.extend(p.text for p in self._paragraphs(shape))
            if lines:
                return "\n".join(lines)
        return None
