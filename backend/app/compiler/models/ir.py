"""Internal Content IR models (compiler-owned, never served raw to clients).

DEC-CONTENT-001: runtime never parses original source documents — the compiler
produces this IR. Fields mirror ``contracts/ctf/scene.schema.json`` so a scene
can be lifted into a CTF package later. ``docs/architecture/05_CONTENT_MODELS_AND_FIDELITY.md``.

``fidelity`` produced by the extractor is provisional: the render stage (V0-005)
is the only stage that can classify a scene against a renderer, and it overwrites
the value together with ``renderer``/``fallback_asset``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

#: Bumped whenever the IR shape changes: 1.1.0 added text runs + fonts and
#: explicit per-object ``reading_order`` (V0-004).
CONTENT_IR_SCHEMA_VERSION = "content-ir/1.1.0"
EXTRACTOR_NAME = "stdlib-ooxml-pptx"
EXTRACTOR_VERSION = "1.1.0"

#: Fidelity classification from ``contracts/ctf/scene.schema.json``.
#: ``docs/architecture/04_CONTENT_COMPILER.md`` additionally has a *failed*
#: classification, but that is not a fidelity: a failed render blocks
#: publication instead of entering a package, so it is not in the schema enum.
FIDELITY_NATIVE = "NATIVE_RENDERED"
FIDELITY_COMPATIBLE = "COMPATIBLE_RENDERED"
FIDELITY_STRUCTURAL = "STRUCTURAL_RENDERED"
FIDELITY_DEGRADED = "DEGRADED_RENDERED"
FIDELITY_VALUES = (
    FIDELITY_NATIVE,
    FIDELITY_COMPATIBLE,
    FIDELITY_STRUCTURAL,
    FIDELITY_DEGRADED,
)

#: Values that require a human check of meaning (``04_CONTENT_COMPILER.md``).
FIDELITY_REQUIRES_REVIEW = frozenset({FIDELITY_DEGRADED})


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

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "font": self.font}


@dataclass(frozen=True)
class TextParagraph:
    level: int
    text: str
    runs: list[TextRun] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "text": self.text,
            "runs": [run.to_dict() for run in self.runs],
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
