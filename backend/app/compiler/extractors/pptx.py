"""Deterministic PPTX (OOXML) structural + presentation extractor.

Dependency-free: reads the package with ``zipfile`` and parses parts with
``xml.etree``. No macro/script/OLE is ever executed and archive expansion is
bounded (``docs/architecture/04_CONTENT_COMPILER.md`` security/reproducibility).
Produces :class:`ContentIRDocument`.

Scope = V0-004 "structural extraction" plus V0-018 "presentation fidelity": slide
order/dimensions, text runs and notes, images, shapes, groups, tables, chart/media
refs, normalized bounds, reading order, stable source IDs, warnings/provenance,
and the resolved *look* of the slide — theme colours and fonts, slide/layout/master
backgrounds (a ``picture`` background resolved against the relationships of the
part that declares it), shape fill/line/geometry/rotation, per-run and per-paragraph
formatting, table metrics, and picture crop. Vision analysis, SmartArt
reconstruction, and native animation are out of scope.

Presentation attributes are resolved against the slide -> layout -> master ->
theme chain here, in the compiler, so the IR carries *effective* values and the
render stage needs no OOXML knowledge (``DEC-CONTENT-001``).

Degradation policy: a damaged package raises (stable code, no partial output),
while a *locally* damaged part (unresolvable relationship, malformed ``.rels``,
unmodelled element) degrades only the affected object and is surfaced as a
warning, so one bad relationship can never drop a slide.
"""

from __future__ import annotations

import posixpath
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, replace
from io import BytesIO
from typing import Callable, Optional

from app.common.errors import ErrorCode, error
from app.compiler.extractors.ooxml import (
    A,
    CHART,
    P,
    PKG_REL,
    R,
    children as _children,
    child as _child,
    qn as _t,
    rels_part_for as _rels_part_for,
    resolve_target as _resolve_target,
)
from app.compiler.extractors.style import (
    BodyFormat,
    LevelFormat,
    MasterStyles,
    PlaceholderDef,
    Transform,
    Xform,
    body_format,
    custom_path_from,
    empty_levels,
    geometry_from,
    group_transform,
    level_formats,
    match_placeholder,
    merge_body,
    merge_levels,
    merge_para,
    merge_run,
    para_format,
    parse_tx_styles,
    placeholder_defs,
    run_format,
    text_style_family,
    xform_from,
)
from app.compiler.extractors.theme import (
    Theme,
    fill_from,
    first_color,
    line_from,
    parse_clr_map,
    parse_theme,
)
from app.compiler.media import media_type_for_part
from app.compiler.models.ir import (
    Bounds,
    ContentIRDocument,
    EXTRACTOR_NAME,
    EXTRACTOR_VERSION,
    FIDELITY_STRUCTURAL,
    ShapeObject,
    SlideScene,
    TableCell,
    TextParagraph,
    TextRun,
)

CONTENT_TYPES_PART = "[Content_Types].xml"
PRESENTATION_PART = "ppt/presentation.xml"

#: 16:9 default used only when a package omits ``p:sldSz``.
DEFAULT_SLIDE_WIDTH_EMU = 12192000
DEFAULT_SLIDE_HEIGHT_EMU = 6858000

#: ``p:spTree`` / ``p:grpSp`` header elements that carry no slide content.
_NON_VISUAL_TAGS = frozenset({_t(P, "nvGrpSpPr"), _t(P, "grpSpPr")})

#: Character-property elements that may carry a typeface.
_CHAR_PROPS = frozenset({_t(A, "rPr"), _t(A, "defRPr"), _t(A, "endParaRPr")})


def _typeface_from(rpr: Optional[ET.Element], theme: Theme) -> Optional[str]:
    """Effective typeface of a character-property element, theme refs resolved."""

    if rpr is None:
        return None
    for tag in ("latin", "ea", "cs"):
        node = _child(rpr, A, tag)
        if node is None:
            continue
        typeface = theme.resolve_font_ref(node.get("typeface"))
        if typeface:
            return typeface
    return None


def _typefaces_in(element: Optional[ET.Element], theme: Theme) -> list[str]:
    """Distinct typefaces used anywhere inside ``element`` (sorted)."""

    if element is None:
        return []
    found: set[str] = set()
    for node in element.iter():
        if node.tag in _CHAR_PROPS:
            typeface = _typeface_from(node, theme)
            if typeface:
                found.add(typeface)
    return sorted(found)


def _effective_fonts(
    element: Optional[ET.Element], theme: Theme, paragraphs: list[TextParagraph]
) -> list[str]:
    """Typefaces a shape actually renders with.

    Declarations inside the shape are not enough: an unstyled placeholder takes
    its font from the master's ``p:txStyles``, so the resolved run fonts count
    too. Without this the fidelity gate would stay green while the slide
    silently rendered in a substituted face.
    """

    found = set(_typefaces_in(element, theme))
    for paragraph in paragraphs:
        for run in paragraph.runs:
            if run.font:
                found.add(run.font)
    return sorted(found)


@dataclass(frozen=True)
class DeckContext:
    """The layout/master/theme chain one slide inherits from."""

    theme: Theme
    styles: MasterStyles
    layout_placeholders: list[PlaceholderDef] = field(default_factory=list)
    master_placeholders: list[PlaceholderDef] = field(default_factory=list)
    background: Optional[dict] = None
    warnings: tuple[str, ...] = ()

    def placeholder(
        self, placeholder: Optional[str], idx: Optional[str]
    ) -> tuple[Optional[PlaceholderDef], Optional[PlaceholderDef]]:
        """(layout definition, master definition) for a slide placeholder."""

        return (
            match_placeholder(self.layout_placeholders, placeholder, idx),
            match_placeholder(self.master_placeholders, placeholder, idx),
        )

    def baseline_levels(
        self,
        placeholder: Optional[str],
        layout_def: Optional[PlaceholderDef],
        master_def: Optional[PlaceholderDef],
        shape_levels: Optional[list[LevelFormat]],
    ) -> list[LevelFormat]:
        """Master text style <- master placeholder <- layout placeholder <- shape."""

        levels = self.styles.levels_for(placeholder)
        if master_def is not None:
            levels = merge_levels(levels, master_def.levels)
        if layout_def is not None:
            levels = merge_levels(levels, layout_def.levels)
        if shape_levels is not None:
            levels = merge_levels(levels, shape_levels)
        return levels


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
        self._rels_cache: dict[str, dict[str, str]] = {}
        self._rels_warned: set[str] = set()
        self._context_cache: dict[str, DeckContext] = {}

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
        self._rels_cache = {}
        self._rels_warned = set()
        self._context_cache = {}
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

    def _read_xml_optional(self, part: Optional[str]) -> Optional[ET.Element]:
        """Best-effort part read: a missing/malformed theme/layout is not fatal."""

        if not part or self._archive is None or part not in self._archive.namelist():
            return None
        try:
            return ET.fromstring(self._archive.read(part))
        except (ET.ParseError, KeyError, zipfile.BadZipFile):
            return None

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

    def _rels_for(self, part: str, warnings: list[str]) -> dict[str, str]:
        """Cached relationship read for one part (one malformed warning per part)."""

        if part in self._rels_cache:
            return self._rels_cache[part]
        if self._archive is None:
            return {}
        rels_part = _rels_part_for(part)
        collected: list[str] = []
        rels = self._read_rels(self._archive, rels_part, collected)
        if collected and rels_part not in self._rels_warned:
            self._rels_warned.add(rels_part)
            warnings.extend(collected)
        self._rels_cache[part] = rels
        return rels

    def _rel_of_type(
        self, part: str, suffix: str, warnings: list[str]
    ) -> Optional[str]:
        """Target part of the first relationship whose type ends with ``suffix``."""

        if self._archive is None:
            return None
        rels_part = _rels_part_for(part)
        if rels_part not in self._archive.namelist():
            return None
        root = self._read_xml_optional(rels_part)
        if root is None:
            return None
        for rel in root.findall(_t(PKG_REL, "Relationship")):
            rel_type = rel.get("Type") or ""
            if not rel_type.endswith(suffix):
                continue
            target = rel.get("Target")
            if not target or rel.get("TargetMode") == "External":
                continue
            return _resolve_target(part, target)
        return None

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

    # -- theme / layout / master context ----------------------------------------
    def _context(self, slide_part: str, warnings: list[str]) -> DeckContext:
        """Resolve slide -> layout -> master -> theme, cached per layout."""

        layout_part = self._rel_of_type(slide_part, "/slideLayout", warnings)
        cache_key = layout_part or slide_part
        if cache_key in self._context_cache:
            return self._context_cache[cache_key]

        collected: list[str] = []
        context = self._build_context(layout_part, collected)
        context = replace(context, warnings=tuple(collected))
        self._context_cache[cache_key] = context
        warnings.extend(collected)
        return context

    def _build_context(self, layout_part: Optional[str], warnings: list[str]) -> DeckContext:
        layout_root = self._read_xml_optional(layout_part)
        if layout_part and layout_root is None:
            warnings.append(
                f"slide layout {layout_part!r} is unreadable; slide styling falls back to defaults"
            )
        master_part = (
            self._rel_of_type(layout_part, "/slideMaster", warnings) if layout_part else None
        )
        master_root = self._read_xml_optional(master_part)
        if master_part and master_root is None:
            warnings.append(
                f"slide master {master_part!r} is unreadable; slide styling falls back to defaults"
            )
        theme_part = (
            self._rel_of_type(master_part, "/theme", warnings) if master_part else None
        )
        theme = parse_theme(self._read_xml_optional(theme_part))
        theme = replace(theme, clr_map=parse_clr_map(master_root))
        styles = parse_tx_styles(master_root, theme)
        master_placeholders = placeholder_defs(
            _child(_child(master_root, P, "cSld"), P, "spTree"), theme
        )
        layout_placeholders = placeholder_defs(
            _child(_child(layout_root, P, "cSld"), P, "spTree"), theme
        )
        # Background: the layout wins over the master; the slide wins over both.
        # Each level resolves its own picture-fill relationship (a layout's ``p:bg``
        # references the *layout's* rels, not the slide's) — V0-019 v6.
        background = (
            self._background_fill(
                _child(layout_root, P, "cSld"),
                theme,
                self._media_resolver(layout_part, warnings) if layout_part else None,
                warnings,
            )
            or self._background_fill(
                _child(master_root, P, "cSld"),
                theme,
                self._media_resolver(master_part, warnings) if master_part else None,
                warnings,
            )
        )
        return DeckContext(
            theme=theme,
            styles=styles,
            layout_placeholders=layout_placeholders,
            master_placeholders=master_placeholders,
            background=background,
        )

    def _background_fill(
        self,
        c_sld: Optional[ET.Element],
        theme: Theme,
        resolve_media: Optional[Callable[[str], Optional[tuple[str, Optional[str]]]]] = None,
        warnings: Optional[list[str]] = None,
    ) -> Optional[dict]:
        """``p:cSld/p:bg`` (solid/gradient/picture fill, or a ``p:bgRef`` colour).

        ``p:bg`` may be a **picture** fill (``a:blipFill``): the art-directed dark
        backgrounds a deck puts on its title/section layouts. Its relationship
        belongs to the part that declares it, so the caller passes that part's
        ``resolve_media`` — a layout's background cannot be resolved against the
        slide's relationships.
        """

        bg = _child(c_sld, P, "bg")
        if bg is None:
            return None
        bg_pr = _child(bg, P, "bgPr")
        if bg_pr is not None:
            fill = fill_from(bg_pr, theme, resolve_media=resolve_media)
            if fill is not None:
                if fill.get("type") == "none" and _child(bg_pr, A, "blipFill") is not None:
                    # A picture background whose bytes we cannot resolve must not
                    # mask a usable background further up (slide > layout > master).
                    if warnings is not None:
                        warnings.append(
                            "a picture slide background could not be resolved; "
                            "the next background up is used"
                        )
                    return None
                return fill
        ref = _child(bg, P, "bgRef")
        if ref is not None:
            if _child(ref, A, "noFill") is not None:
                return {"type": "none"}
            color = first_color(ref, theme)
            if color:
                return {"type": "solid", "color": color}
        return None

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
        context = self._context(part, warnings)
        theme = context.theme
        c_sld = _child(slide, P, "cSld")
        sp_tree = _child(c_sld, P, "spTree")

        resolve_media = self._media_resolver(part, warnings)
        background = (
            self._background_fill(c_sld, theme, resolve_media, warnings) or context.background
        )

        objects = self._walk(sp_tree, part, warnings, context, Transform(), 0)
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
            background=background,
        )

    def _media_resolver(
        self, part: str, warnings: list[str]
    ) -> Callable[[str], Optional[tuple[str, Optional[str]]]]:
        """Resolve a relationship id to ``(media part, mime)`` for inlineable images."""

        def resolve(rel_id: str) -> Optional[tuple[str, Optional[str]]]:
            target = self._resolve_rel(part, rel_id, warnings, warn_missing=False)
            if not target:
                return None
            mime = media_type_for_part(target)
            if mime is None:
                warnings.append(f"media part {target!r} is not an inlineable image")
                return None
            return target, mime

        return resolve

    def _walk(
        self,
        container: Optional[ET.Element],
        part: str,
        warnings: list[str],
        context: DeckContext,
        transform: Transform,
        depth: int = 0,
    ) -> list[ShapeObject]:
        """Collect the shape objects directly held by ``container``.

        ``container`` is a slide ``p:spTree`` or a ``p:grpSp``. Both hold their
        children as immediate elements — a group does **not** wrap its shapes in
        a nested ``p:spTree`` (that exists only once, at the slide level).
        ``depth`` records how deep a shape sits inside nested groups, and
        ``transform`` maps the current child coordinate space back to the slide
        (so grouped shapes carry absolute bounds).
        """

        objects: list[ShapeObject] = []
        if container is None:
            return objects
        for element in list(container):
            tag = element.tag
            if tag in _NON_VISUAL_TAGS:
                continue
            if tag == _t(P, "grpSp"):
                xform = xform_from(_child(element, P, "grpSpPr")) or xform_from(
                    _child(element, P, "spPr")
                )
                objects.append(self._extract_group(element, part, transform, depth))
                child_transform = group_transform(xform).compose(transform)
                objects.extend(
                    self._walk(element, part, warnings, context, child_transform, depth + 1)
                )
            elif tag == _t(P, "sp"):
                objects.append(self._extract_shape(element, part, warnings, context, transform, depth))
            elif tag == _t(P, "pic"):
                objects.append(self._extract_picture(element, part, warnings, context, transform, depth))
            elif tag == _t(P, "graphicFrame"):
                objects.append(
                    self._extract_graphic_frame(element, part, warnings, context, transform, depth)
                )
            elif tag == _t(P, "cxnSp"):
                objects.append(self._extract_connector(element, part, context, transform, depth))
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
        placeholder, _idx = self._placeholder_ref(element)
        return f"{part}#{shape_id}", name, placeholder

    def _placeholder_ref(self, element: ET.Element) -> tuple[Optional[str], Optional[str]]:
        """(``p:ph/@type``, ``p:ph/@idx``); type defaults to "body" per the schema."""

        for nv_name in ("nvSpPr", "nvPicPr", "nvGraphicFramePr"):
            nv = _child(element, P, nv_name)
            ph = _child(_child(nv, P, "nvPr"), P, "ph")
            if ph is not None:
                return ph.get("type") or "body", ph.get("idx")
            if nv is not None:
                return None, None
        return None, None

    def _bounds(self, element: ET.Element) -> Optional[Bounds]:
        sp_pr = _child(element, P, "spPr")
        if sp_pr is None:
            sp_pr = _child(element, P, "grpSpPr")
        xform = xform_from(sp_pr)
        return xform.bounds() if xform is not None else None

    def _paragraphs(
        self,
        element: ET.Element,
        theme: Theme,
        baseline: Optional[list[LevelFormat]] = None,
    ) -> list[TextParagraph]:
        """Paragraphs with their runs and effective formatting.

        ``baseline`` is the per-level default resolved from the master/layout
        chain; each paragraph then applies its own ``a:pPr``/``a:rPr`` on top.
        """

        tx_body = _child(element, P, "txBody")
        if tx_body is None:
            # Table cells carry their text body in the drawing namespace
            # (``a:txBody``); shapes use ``p:txBody``.
            tx_body = _child(element, A, "txBody")
        if tx_body is None:
            return []
        levels = baseline or empty_levels()
        result: list[TextParagraph] = []
        for para in _children(tx_body, A, "p"):
            p_pr = _child(para, A, "pPr")
            raw_level = p_pr.get("lvl") if p_pr is not None else None
            try:
                level = max(0, min(8, int(raw_level))) if raw_level else 0
            except ValueError:
                level = 0
            base = levels[level]
            para_fmt = merge_para(base.para, para_format(p_pr, theme))
            run_base = merge_run(base.run, run_format(_child(p_pr, A, "defRPr"), theme))
            runs: list[TextRun] = []
            for node in list(para):
                if node.tag == _t(A, "r"):
                    fmt = merge_run(run_base, run_format(_child(node, A, "rPr"), theme))
                    for run_text in _children(node, A, "t"):
                        if run_text.text is None:
                            continue
                        runs.append(
                            TextRun(
                                text=run_text.text,
                                font=fmt.font,
                                size_pt=fmt.size_pt,
                                bold=fmt.bold,
                                italic=fmt.italic,
                                underline=fmt.underline,
                                color=fmt.color,
                                highlight=fmt.highlight,
                            )
                        )
                elif node.tag == _t(A, "br"):
                    runs.append(TextRun(text="\n", font=run_base.font, size_pt=run_base.size_pt))
                elif node.tag == _t(A, "fld"):
                    # Slide-number/date fields: keep the visible text.
                    for run_text in _children(node, A, "t"):
                        if run_text.text:
                            runs.append(
                                TextRun(text=run_text.text, font=run_base.font, size_pt=run_base.size_pt)
                            )
            text = "".join(run.text for run in runs)
            if text:
                result.append(
                    TextParagraph(
                        level=level,
                        text=text,
                        runs=runs,
                        align=para_fmt.align,
                        bullet=para_fmt.bullet,
                        margin_left_emu=para_fmt.margin_left_emu,
                        indent_emu=para_fmt.indent_emu,
                        space_before_pt=para_fmt.space_before_pt,
                        space_after_pt=para_fmt.space_after_pt,
                        line_spacing=para_fmt.line_spacing,
                        line_spacing_pt=para_fmt.line_spacing_pt,
                    )
                )
        return result

    def _shape_formats(
        self,
        element: ET.Element,
        context: DeckContext,
    ) -> tuple[
        Optional[PlaceholderDef],
        Optional[PlaceholderDef],
        list[LevelFormat],
        BodyFormat,
    ]:
        """Effective (layout def, master def, per-level text defaults, body format)."""

        placeholder, idx = self._placeholder_ref(element)
        layout_def, master_def = context.placeholder(placeholder, idx)
        tx_body = _child(element, P, "txBody")
        shape_levels = level_formats(_child(tx_body, A, "lstStyle"), context.theme)
        baseline = context.baseline_levels(placeholder, layout_def, master_def, shape_levels)
        body = body_format(_child(tx_body, A, "bodyPr"))
        if master_def is not None:
            body = merge_body(master_def.body, body)
        if layout_def is not None:
            body = merge_body(layout_def.body, body)
        return layout_def, master_def, baseline, body

    def _shape_bounds(
        self,
        element: ET.Element,
        layout_def: Optional[PlaceholderDef],
        master_def: Optional[PlaceholderDef],
        transform: Transform,
    ) -> Optional[Bounds]:
        """Own ``a:xfrm`` if present, else the layout/master placeholder geometry."""

        sp_pr = _child(element, P, "spPr")
        xform = xform_from(sp_pr)
        if xform is not None:
            return transform.apply(xform.bounds())
        if layout_def is not None and layout_def.bounds is not None:
            return layout_def.bounds
        if master_def is not None and master_def.bounds is not None:
            return master_def.bounds
        return None

    def _extract_shape(
        self,
        element: ET.Element,
        part: str,
        warnings: list[str],
        context: DeckContext,
        transform: Transform,
        depth: int = 0,
    ) -> ShapeObject:
        source_id, name, placeholder = self._shape_identity(element, part)
        theme = context.theme
        layout_def, master_def, baseline, body = self._shape_formats(element, context)
        paragraphs = self._paragraphs(element, theme, baseline)
        sp_pr = _child(element, P, "spPr")
        style_el = _child(element, P, "style")
        xform = xform_from(sp_pr)
        fill = fill_from(sp_pr, theme, resolve_media=self._media_resolver(part, warnings), style_el=style_el)
        if fill is None and layout_def is not None:
            fill = layout_def.fill
        if fill is None and master_def is not None:
            fill = master_def.fill
        line = line_from(sp_pr, theme, style_el=style_el)
        geometry = geometry_from(sp_pr)
        if geometry is None and layout_def is not None:
            geometry = layout_def.geometry
        if geometry is None:
            geometry = "rect"
        return ShapeObject(
            source_id=source_id,
            kind="text" if paragraphs else "shape",
            name=name,
            placeholder=placeholder,
            bounds=self._shape_bounds(element, layout_def, master_def, transform),
            paragraphs=paragraphs,
            fonts=_effective_fonts(element, theme, paragraphs),
            depth=depth,
            geometry=geometry,
            custom_path=custom_path_from(sp_pr),
            fill=fill,
            line=line,
            rotation=xform.rotation if xform else None,
            flip_h=xform.flip_h if xform else False,
            flip_v=xform.flip_v if xform else False,
            anchor=body.anchor,
            insets=body.insets,
            autofit=body.autofit,
            font_scale=body.font_scale,
        )

    def _extract_connector(
        self,
        element: ET.Element,
        part: str,
        context: DeckContext,
        transform: Transform,
        depth: int = 0,
    ) -> ShapeObject:
        source_id, name, placeholder = self._shape_identity(element, part)
        sp_pr = _child(element, P, "spPr")
        xform = xform_from(sp_pr)
        style_el = _child(element, P, "style")
        return ShapeObject(
            source_id=source_id,
            kind="connector",
            name=name,
            placeholder=placeholder,
            bounds=transform.apply(xform.bounds()) if xform else None,
            depth=depth,
            geometry=geometry_from(sp_pr) or "line",
            line=line_from(sp_pr, context.theme, style_el=style_el),
            fill={"type": "none"},
            rotation=xform.rotation if xform else None,
            flip_h=xform.flip_h if xform else False,
            flip_v=xform.flip_v if xform else False,
        )

    def _extract_group(
        self,
        element: ET.Element,
        part: str,
        transform: Transform,
        depth: int = 0,
    ) -> ShapeObject:
        nv = _child(element, P, "nvGrpSpPr")
        c_nv_pr = _child(nv, P, "cNvPr")
        shape_id = c_nv_pr.get("id", "") if c_nv_pr is not None else ""
        name = c_nv_pr.get("name", "") if c_nv_pr is not None else ""
        xform = xform_from(_child(element, P, "grpSpPr")) or xform_from(
            _child(element, P, "spPr")
        )
        return ShapeObject(
            source_id=f"{part}#{shape_id}",
            kind="group",
            name=name,
            bounds=transform.apply(xform.bounds()) if xform else None,
            depth=depth,
            fill={"type": "none"},
            rotation=xform.rotation if xform else None,
            flip_h=xform.flip_h if xform else False,
            flip_v=xform.flip_v if xform else False,
        )

    def _extract_picture(
        self,
        element: ET.Element,
        part: str,
        warnings: list[str],
        context: DeckContext,
        transform: Transform,
        depth: int = 0,
    ) -> ShapeObject:
        source_id, name, placeholder = self._shape_identity(element, part)
        media_ref = None
        media_type = None
        blip = element.find(f".//{_t(A, 'blip')}")
        if blip is not None:
            rel_id = blip.get(_t(R, "embed")) or blip.get(_t(R, "link"))
            media_ref = self._resolve_rel(part, rel_id, warnings) if rel_id else None
            if rel_id and media_ref is None:
                warnings.append(f"picture on {part!r} has no resolvable image reference")
            elif media_ref:
                media_type = media_type_for_part(media_ref)
                if media_type is None:
                    warnings.append(
                        f"picture on {part!r} uses {media_ref!r}, which cannot be inlined"
                    )
        sp_pr = _child(element, P, "spPr")
        xform = xform_from(sp_pr)
        style_el = _child(element, P, "style")
        return ShapeObject(
            source_id=source_id,
            kind="picture",
            name=name,
            placeholder=placeholder,
            bounds=transform.apply(xform.bounds()) if xform else None,
            media_ref=media_ref,
            media_type=media_type,
            crop=self._src_rect(element),
            depth=depth,
            geometry=geometry_from(sp_pr) or "rect",
            fill=fill_from(sp_pr, context.theme, style_el=style_el),
            line=line_from(sp_pr, context.theme, style_el=style_el),
            rotation=xform.rotation if xform else None,
            flip_h=xform.flip_h if xform else False,
            flip_v=xform.flip_v if xform else False,
        )

    @staticmethod
    def _src_rect(element: ET.Element) -> Optional[dict]:
        """``a:srcRect`` crop as fractions removed from each edge."""

        src = element.find(f".//{_t(A, 'srcRect')}")
        if src is None:
            return None
        crop: dict[str, float] = {}
        for edge, attribute in (("left", "l"), ("top", "t"), ("right", "r"), ("bottom", "b")):
            raw = src.get(attribute)
            if raw in (None, "", "0"):
                continue
            try:
                crop[edge] = abs(int(raw)) / 100000
            except ValueError:
                continue
        return crop or None

    def _extract_graphic_frame(
        self,
        element: ET.Element,
        part: str,
        warnings: list[str],
        context: DeckContext,
        transform: Transform,
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
        bounds = transform.apply(bounds)
        theme = context.theme

        table = element.find(f".//{_t(A, 'tbl')}")
        if table is not None:
            rows: list[list[str]] = []
            cells: list[list[TableCell]] = []
            for row in _children(table, A, "tr"):
                cell_text: list[str] = []
                cell_models: list[TableCell] = []
                for cell in _children(row, A, "tc"):
                    paragraphs = self._paragraphs(cell, theme)
                    cell_text.append("".join(p.text for p in paragraphs))
                    cell_models.append(
                        TableCell(
                            paragraphs=paragraphs,
                            fill=self._cell_fill(cell, theme),
                            grid_span=_int_attr(cell, A, "tcPr", "gridSpan") or 1,
                            row_span=_int_attr(cell, A, "tcPr", "rowSpan") or 1,
                            h_merge=_bool_attr(cell, A, "tcPr", "hMerge"),
                            v_merge=_bool_attr(cell, A, "tcPr", "vMerge"),
                        )
                    )
                rows.append(cell_text)
                cells.append(cell_models)
            grid = _child(table, A, "tblGrid")
            columns = [
                width
                for width in (
                    _int_attr_node(column, "w") for column in _children(grid, A, "gridCol")
                )
                if width is not None
            ]
            row_heights = [
                height
                for height in (_int_attr_node(row, "h") for row in _children(table, A, "tr"))
                if height is not None
            ]
            return ShapeObject(
                source_id=f"{part}#{shape_id}",
                kind="table",
                name=name,
                bounds=bounds,
                table=rows,
                table_cells=cells,
                table_columns=columns or None,
                table_rows=row_heights or None,
                fonts=_effective_fonts(
                    table,
                    theme,
                    [p for row in cells for cell in row for p in cell.paragraphs],
                ),
                depth=depth,
                geometry="rect",
                fill=fill_from(element, theme, style_el=_child(element, P, "style")),
                line=line_from(element, theme, style_el=_child(element, P, "style")),
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
                geometry="rect",
            )

        graphic_data = element.find(f".//{_t(A, 'graphicData')}")
        uri = graphic_data.get("uri", "") if graphic_data is not None else ""
        del uri
        return ShapeObject(
            source_id=f"{part}#{shape_id}",
            kind="graphicFrame",
            name=name,
            bounds=bounds,
            depth=depth,
            geometry="rect",
        )

    def _cell_fill(self, cell: ET.Element, theme: Theme) -> Optional[dict]:
        tc_pr = _child(cell, A, "tcPr")
        if tc_pr is None:
            return None
        fill = fill_from(tc_pr, theme)
        return fill

    def _resolve_rel(
        self,
        part: str,
        rel_id: str,
        warnings: list[str],
        *,
        warn_missing: bool = True,
    ) -> Optional[str]:
        rels = self._rels_for(part, warnings)
        target = rels.get(rel_id)
        if target is None:
            if warn_missing:
                warnings.append(f"unresolved relationship {rel_id!r} in {part!r}")
            return None
        resolved = _resolve_target(part, target)
        if self._archive is not None and resolved not in self._archive.namelist():
            # Keep the reference (it is still provenance) but say it is broken.
            if warn_missing:
                warnings.append(f"referenced part {resolved!r} is absent from the package")
        return resolved

    def _extract_notes(
        self, archive: zipfile.ZipFile, slide_part: str, warnings: list[str]
    ) -> Optional[str]:
        rels = self._rels_for(slide_part, warnings)
        for target in rels.values():
            if "notesSlide" not in target:
                continue
            notes_part = _resolve_target(slide_part, target)
            if notes_part not in archive.namelist():
                warnings.append(f"notes part {notes_part!r} referenced but absent")
                continue
            notes_root = self._read_xml(archive, notes_part)
            context = self._context(slide_part, warnings)
            sp_tree = _child(_child(notes_root, P, "cSld"), P, "spTree")
            lines: list[str] = []
            for shape in _children(sp_tree, P, "sp"):
                _sid, _name, placeholder = self._shape_identity(shape, notes_part)
                if placeholder == "sldNum":
                    continue
                lines.extend(p.text for p in self._paragraphs(shape, context.theme))
            if lines:
                return "\n".join(lines)
        return None


def _int_attr_node(element: Optional[ET.Element], name: str) -> Optional[int]:
    if element is None:
        return None
    raw = element.get(name)
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _int_attr(element: ET.Element, ns: str, container: str, name: str) -> Optional[int]:
    return _int_attr_node(_child(element, ns, container), name)


def _bool_attr(element: ET.Element, ns: str, container: str, name: str) -> bool:
    node = _child(element, ns, container)
    raw = node.get(name) if node is not None else None
    return raw in ("1", "true", "on")


__all__ = [
    "CONTENT_TYPES_PART",
    "DEFAULT_SLIDE_HEIGHT_EMU",
    "DEFAULT_SLIDE_WIDTH_EMU",
    "DeckContext",
    "PRESENTATION_PART",
    "PptxExtractor",
]
