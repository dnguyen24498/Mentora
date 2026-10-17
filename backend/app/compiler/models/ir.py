"""Internal Content IR models (compiler-owned, never served raw to clients).

DEC-CONTENT-001: runtime never parses original source documents — the compiler
produces this IR. Fields mirror ``contracts/ctf/scene.schema.json`` so a scene
can be lifted into a CTF package later. ``docs/architecture/05_CONTENT_MODELS_AND_FIDELITY.md``.

``fidelity`` produced by the extractor is provisional: the render stage (V0-005)
is the only stage that can classify a scene against a renderer, and it overwrites
the value together with ``renderer``/``fallback_asset``.

Presentation attributes (V0-018) are *facts about the source slide*, resolved by
the compiler against the slide -> layout -> master -> theme chain. They are
carried so the local renderer can reproduce the original look (``DEC-CONTENT-006``
keeps the renderer identity explicit, so no consumer mistakes this for a native
PowerPoint render).

JSON shapes used across the models (kept as plain dictionaries because they are
serialised verbatim into a scene document):

``ColorRef``
    ``{"value": "#RRGGBB", "alpha": 1.0}`` — resolved sRGB, alpha 0..1.
``Fill``
    ``{"type": "none"}``
    | ``{"type": "solid", "color": ColorRef}``
    | ``{"type": "gradient", "angle": <deg>, "stops": [{"position": 0..1, "color": ColorRef}]}``
    | ``{"type": "picture", "media_ref": <part>, "crop": Crop|None}``
``Line``
    ``{"color": ColorRef|None, "width_emu": int|None, "dash": str|None}``
``Crop``
    ``{"left": <fraction>, "top": <fraction>, "right": <fraction>, "bottom": <fraction>}``
    (fractions of the image, removed from each edge).
``Insets``
    ``{"left": <emu>, "top": <emu>, "right": <emu>, "bottom": <emu>}``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

#: Bumped whenever the IR shape changes. 1.1.0 added text runs + fonts and
#: explicit per-object ``reading_order`` (V0-004); 1.2.0 added presentation
#: styling resolved from the theme/layout/master chain (V0-018).
CONTENT_IR_SCHEMA_VERSION = "content-ir/1.2.0"
EXTRACTOR_NAME = "stdlib-ooxml-pptx"
#: Bumped whenever extraction *behaviour* changes (the IR shape can stay put).
#: 1.2.0 resolved the theme/layout/master styling chain (V0-018); 1.3.0 resolves a
#: picture (``a:blipFill``) slide background against the relationships of the part
#: that declares it — the layout's art-directed backgrounds (V0-019 v5). The value
#: is also the package cache key's ``compiler_version``, so a bump retires packages
#: built by an older extractor.
EXTRACTOR_VERSION = "1.3.0"

#: Fidelity classification from ``contracts/ctf/scene.schema.json``.
#: ``docs/architecture/04_CONTENT_COMPILER.md`` additionally has a *failed*
#: classification, but that is not a fidelity: a failed render blocks
#: publication instead of entering a package, so it is not in the schema enum.
FIDELITY_NATIVE = "NATIVE_RENDERED"
FIDELITY_COMPATIBLE = "COMPATIBLE_RENDERED"
FIDELITY_STRUCTURAL = "STRUCTURAL_RENDERED"
#: Themed re-layout (V0-019): the scene's *content* (text, pictures, tables) is the
#: author's, but the *placement* and *appearance* (column, type scale, typeface,
#: palette, chrome) are the platform's, not the source deck's. It is deliberately
#: **not** on the fidelity-to-source ladder — there is nothing to be faithful *to*
#: — so consumers must not read it as "better" or "worse" than
#: ``STRUCTURAL_RENDERED``.
FIDELITY_THEMED = "THEMED_RENDERED"
FIDELITY_DEGRADED = "DEGRADED_RENDERED"
FIDELITY_VALUES = (
    FIDELITY_NATIVE,
    FIDELITY_COMPATIBLE,
    FIDELITY_STRUCTURAL,
    FIDELITY_THEMED,
    FIDELITY_DEGRADED,
)

#: Values that require a human check of meaning (``04_CONTENT_COMPILER.md``).
FIDELITY_REQUIRES_REVIEW = frozenset({FIDELITY_DEGRADED})


def _compact(data: dict[str, Any]) -> dict[str, Any]:
    """Drop ``None`` values so optional presentation facts stay out of payloads."""

    return {key: value for key, value in data.items() if value is not None}


@dataclass(frozen=True)
class Bounds:
    """Normalized-to-package EMU bounds; any component may be unknown."""

    x: Optional[int] = None
    y: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}

    def normalized(self, canvas_width: int, canvas_height: int) -> dict[str, Optional[float]]:
        """Bounds as fractions of the package canvas (0..1).

        Layout must not depend on the source canvas or on a particular viewport,
        so consumers (the renderer) work in these fractions and multiply by the
        device size.
        """

        def fraction(value: Optional[int], extent: int) -> Optional[float]:
            if value is None or extent <= 0:
                return None
            return value / extent

        return {
            "x": fraction(self.x, canvas_width),
            "y": fraction(self.y, canvas_height),
            "width": fraction(self.width, canvas_width),
            "height": fraction(self.height, canvas_height),
        }


@dataclass(frozen=True)
class TextRun:
    """A single ``a:r`` run: the smallest unit that carries character formatting."""

    text: str
    #: Effective typeface (latin, else east-asian, else complex-script). Theme
    #: references (``+mj-lt``/``+mn-lt``) are resolved by the theme, not here,
    #: and are reported as ``None`` rather than as a font family.
    font: Optional[str] = None
    #: Effective size in points (``a:rPr/@sz`` is 1/100 pt).
    size_pt: Optional[float] = None
    bold: Optional[bool] = None
    italic: Optional[bool] = None
    underline: Optional[bool] = None
    #: Resolved run colour (``ColorRef``); ``None`` means "inherit theme text".
    color: Optional[dict[str, Any]] = None
    #: Resolved highlight colour (``ColorRef``), when the run sets one.
    highlight: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"text": self.text, "font": self.font}
        data.update(
            _compact(
                {
                    "size_pt": self.size_pt,
                    "bold": self.bold,
                    "italic": self.italic,
                    "underline": self.underline,
                    "color": self.color,
                    "highlight": self.highlight,
                }
            )
        )
        return data


@dataclass(frozen=True)
class TextParagraph:
    level: int
    text: str
    runs: list[TextRun] = field(default_factory=list)
    #: ``a:pPr/@algn``: "l" | "ctr" | "r" | "just" | "dist".
    align: Optional[str] = None
    #: Bullet spec: ``{"none": True}`` | ``{"char": "•"}`` | ``{"autonum": "arabicPeriod"}``.
    bullet: Optional[dict[str, Any]] = None
    margin_left_emu: Optional[int] = None
    indent_emu: Optional[int] = None
    space_before_pt: Optional[float] = None
    space_after_pt: Optional[float] = None
    #: Line spacing as a multiple of the font size (``a:lnSpc/a:spcPct``).
    line_spacing: Optional[float] = None
    #: Absolute line spacing in points (``a:lnSpc/a:spcPts``); wins over
    #: ``line_spacing`` because OOXML's point form is not a multiple of the
    #: font size.
    line_spacing_pt: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "level": self.level,
            "text": self.text,
            "runs": [run.to_dict() for run in self.runs],
        }
        data.update(
            _compact(
                {
                    "align": self.align,
                    "bullet": self.bullet,
                    "margin_left_emu": self.margin_left_emu,
                    "indent_emu": self.indent_emu,
                    "space_before_pt": self.space_before_pt,
                    "space_after_pt": self.space_after_pt,
                    "line_spacing": self.line_spacing,
                    "line_spacing_pt": self.line_spacing_pt,
                }
            )
        )
        return data


@dataclass(frozen=True)
class TableCell:
    """One ``a:tc``: its fill, its text, and its merge state."""

    paragraphs: list[TextParagraph] = field(default_factory=list)
    fill: Optional[dict[str, Any]] = None
    grid_span: int = 1
    row_span: int = 1
    h_merge: bool = False
    v_merge: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "paragraphs": [p.to_dict() for p in self.paragraphs],
            "fill": self.fill,
            "grid_span": self.grid_span,
            "row_span": self.row_span,
            "h_merge": self.h_merge,
            "v_merge": self.v_merge,
        }


@dataclass(frozen=True)
class ShapeObject:
    source_id: str
    kind: str  # text | shape | picture | table | chart | connector | group | graphicFrame
    name: str
    placeholder: Optional[str] = None
    bounds: Optional[Bounds] = None
    paragraphs: list[TextParagraph] = field(default_factory=list)
    table: Optional[list[list[str]]] = None
    #: Referenced package part: the image for a picture, the chart definition
    #: for a chart (``ppt/charts/chart1.xml``). ``None`` when unresolved.
    media_ref: Optional[str] = None
    #: Distinct typefaces used by this object's text, sorted. Drives the
    #: missing-font check in the render stage.
    fonts: list[str] = field(default_factory=list)
    #: Nesting depth of grouped shapes (0 = directly on the slide).
    depth: int = 0
    #: Flattened reading order within the slide (0-based, groups included).
    reading_order: int = 0

    # -- presentation attributes (V0-018) --------------------------------------
    #: PresentationML preset geometry name (``a:prstGeom/@prst``), e.g. "rect".
    geometry: Optional[str] = None
    #: Custom geometry (``a:custGeom``) as an SVG path in the unit square, scaled
    #: to the object's bounds by the renderer.
    custom_path: Optional[str] = None
    fill: Optional[dict[str, Any]] = None
    line: Optional[dict[str, Any]] = None
    #: Clockwise rotation in degrees (``a:xfrm/@rot`` is 1/60000 degree).
    rotation: Optional[float] = None
    flip_h: bool = False
    flip_v: bool = False
    #: ``a:bodyPr`` anchor: "t" | "ctr" | "b".
    anchor: Optional[str] = None
    insets: Optional[dict[str, Any]] = None
    #: "none" | "shrink" (normAutofit) | "resize" (spAutoFit).
    autofit: Optional[str] = None
    #: ``a:normAutofit/@fontScale`` as a fraction (1/100000).
    font_scale: Optional[float] = None
    #: MIME type of ``media_ref`` when it is an image part.
    media_type: Optional[str] = None
    #: Source-rectangle crop of a picture (``a:srcRect``), as fractions.
    crop: Optional[dict[str, Any]] = None
    #: Table layout metrics (EMU) and per-cell styling; ``table`` keeps the text.
    table_columns: Optional[list[int]] = None
    table_rows: Optional[list[int]] = None
    table_cells: Optional[list[list[TableCell]]] = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "source_id": self.source_id,
            "kind": self.kind,
            "name": self.name,
            "placeholder": self.placeholder,
            "bounds": self.bounds.to_dict() if self.bounds else None,
            "depth": self.depth,
            "reading_order": self.reading_order,
            "paragraphs": [p.to_dict() for p in self.paragraphs],
        }
        if self.table is not None:
            data["table"] = self.table
        if self.media_ref is not None:
            data["media_ref"] = self.media_ref
        if self.fonts:
            data["fonts"] = self.fonts
        data.update(
            _compact(
                {
                    "geometry": self.geometry,
                    "custom_path": self.custom_path,
                    "fill": self.fill,
                    "line": self.line,
                    "rotation": self.rotation,
                    "anchor": self.anchor,
                    "insets": self.insets,
                    "autofit": self.autofit,
                    "font_scale": self.font_scale,
                    "media_type": self.media_type,
                    "crop": self.crop,
                    "table_columns": self.table_columns,
                    "table_rows": self.table_rows,
                    "table_cells": (
                        [[cell.to_dict() for cell in row] for row in self.table_cells]
                        if self.table_cells is not None
                        else None
                    ),
                }
            )
        )
        if self.flip_h:
            data["flip_h"] = True
        if self.flip_v:
            data["flip_v"] = True
        return data


@dataclass(frozen=True)
class SlideScene:
    scene_id: str
    source_ref: dict[str, Any]
    order: int
    width: int
    height: int
    fallback_asset: Optional[str]
    fidelity: str
    objects: list[ShapeObject]
    notes: Optional[str]
    warnings: list[str]
    provenance: dict[str, Any]
    steps: list[dict[str, Any]] = field(default_factory=list)
    renderer: Optional[dict[str, Any]] = None
    #: Slide background (``Fill``); ``None`` means "renderer default".
    background: Optional[dict[str, Any]] = None

    def fonts(self) -> list[str]:
        """Distinct typefaces used anywhere on the slide (sorted)."""

        found: set[str] = set()
        for obj in self.objects:
            found.update(obj.fonts)
        return sorted(found)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "scene_id": self.scene_id,
            "source_ref": self.source_ref,
            "order": self.order,
            "dimensions": {"width": self.width, "height": self.height},
            "fallback_asset": self.fallback_asset,
            "fidelity": self.fidelity,
            "objects": [o.to_dict() for o in self.objects],
            "steps": self.steps,
            "notes": self.notes,
            "warnings": self.warnings,
            "provenance": self.provenance,
        }
        if self.background is not None:
            data["background"] = self.background
        if self.renderer is not None:
            data["renderer"] = self.renderer
        return data


@dataclass(frozen=True)
class ContentIRDocument:
    source_ref: dict[str, Any]
    slide_width: int
    slide_height: int
    slides: list[SlideScene]
    warnings: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    schema_version: str = CONTENT_IR_SCHEMA_VERSION

    @property
    def slide_count(self) -> int:
        return len(self.slides)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_ref": self.source_ref,
            "slide_width": self.slide_width,
            "slide_height": self.slide_height,
            "slide_count": len(self.slides),
            "slides": [s.to_dict() for s in self.slides],
            "warnings": self.warnings,
            "provenance": self.provenance,
        }
