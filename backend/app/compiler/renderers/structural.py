"""Deterministic local renderer: Content IR -> styled SVG fallback asset per slide.

This is the *local/dev* implementation of the ``DocumentRenderer`` interface used
while ``DEC-TECH-005`` (native PowerPoint rendering) is OPEN. It is
dependency-free (``xml.sax.saxutils`` + the object store) and pure: the same
document, media, and config always produce byte-identical output, which is what
"same engine/config gives stable logical output" means for the fidelity gate.

V0-018 raises this renderer from grey placeholders to a *faithful structural*
render: it draws the theme's colours and fonts, the slide background, preset and
custom geometry, solid/gradient/picture fills, outlines, rotation, real font
sizes with word wrapping and alignment, embedded pictures, and table styling.

It is still **not** a native PowerPoint render and is never reported as one
(``DEC-CONTENT-006``): charts, SmartArt, WordArt, equations, effects, and
animations are drawn as platform panels (see below), and text metrics are
estimated rather than measured. It never reads the original package
(``DEC-CONTENT-001``): the only inputs are the Content IR and the picture bytes
the compiler injects.

This renderer is the ``faithful`` render mode and the application **default**
(V0-019 v5). It reproduces the source deck's own resolved styling and placement;
``renderers/themed.py`` is the opt-in mode that re-lays the content out in the
platform grid instead of copying the author's geometry.

Platform fallback for components we cannot reproduce
----------------------------------------------------
The product rule is *"same layout as the author's deck; where a component cannot
be reproduced, draw it in the platform's default look, in place"*. So a component
this renderer cannot reproduce as authored is not dropped, and it does not degrade
the scene either — it keeps its exact position and size and is painted with
``mentora_theme`` (flat surface, muted label, the theme's type stack):

* an **unavailable source font** — the run is drawn in the platform's family
  (deterministically, so a client that happens to have the source font cannot get
  a different asset), recorded as ``FONT_SUBSTITUTED:<family>``;
* a **chart / SmartArt / WordArt / equation / graphic frame** — a flat platform
  panel labelled with the object, recorded as ``UNSUPPORTED_OBJECT:<kind>``;
* a **picture that cannot be inlined** (EMF/WMF/TIFF, over budget, bytes not
  supplied) — a flat platform panel labelled with the part, warning unchanged;
* an **unknown preset geometry** — drawn as its bounding rectangle.

Because every one of these has a legible platform representation, a scene only
reports ``DEGRADED_RENDERED`` when something genuinely cannot be drawn; a fallback
is a *warning* on a ``STRUCTURAL_RENDERED`` scene, not a review blocker.
"""

from __future__ import annotations

import base64
import math
import time
from typing import Any, Mapping, Optional
from xml.sax.saxutils import escape

from app.compiler.models.ir import (
    FIDELITY_STRUCTURAL,
    ContentIRDocument,
    ShapeObject,
    SlideScene,
    TableCell,
    TextParagraph,
)
from app.compiler.renderers.base import (
    CancelToken,
    CapabilityReport,
    DocumentRenderer,
    RenderBudget,
    RenderConfig,
    RenderErrorCode,
    RenderRequest,
    RenderStatus,
    RendererError,
    SceneRender,
)
from app.compiler.renderers.mentora_theme import DEFAULT_THEME, MentoraTheme

#: Emitted as ``MISSING_FONT:<family>`` so warnings stay greppable/metricable.
#: Still written by the test double; a real render *substitutes* instead.
MISSING_FONT_PREFIX = "MISSING_FONT:"
#: ``FONT_SUBSTITUTED:<family>`` — the source family is unavailable, so the run is
#: drawn in the platform's type stack (V0-019). A warning, not a degradation.
FONT_SUBSTITUTED_PREFIX = "FONT_SUBSTITUTED:"
#: Emitted as ``UNSUPPORTED_OBJECT:<kind>``.
UNSUPPORTED_OBJECT_PREFIX = "UNSUPPORTED_OBJECT:"
#: ``UNSUPPORTED_MEDIA:<part-or-extension>`` — a picture this build cannot inline.
UNSUPPORTED_MEDIA_PREFIX = "UNSUPPORTED_MEDIA:"
#: ``MEDIA_UNAVAILABLE:<part>`` — the compiler did not hand the bytes over.
MEDIA_UNAVAILABLE_PREFIX = "MEDIA_UNAVAILABLE:"
#: ``MEDIA_BUDGET_EXCEEDED:<part>`` — the picture did not fit the inline budget.
MEDIA_BUDGET_PREFIX = "MEDIA_BUDGET_EXCEEDED:"
#: ``UNSUPPORTED_GEOMETRY:<preset>`` — drawn as a rectangle instead.
UNSUPPORTED_GEOMETRY_PREFIX = "UNSUPPORTED_GEOMETRY:"

#: OOXML's default text colour (theme ``tx1`` = black).
DEFAULT_TEXT_COLOR = "#000000"

#: ``a:bodyPr`` spec defaults in EMU, used when a shape specifies no insets.
DEFAULT_INSETS_EMU = {"left": 91440, "top": 45720, "right": 91440, "bottom": 45720}

#: EMU per CSS pixel at the renderer's 96 dpi canvas.
EMU_PER_PIXEL = 9525
#: Points per CSS pixel at 96 dpi.
PT_PER_PIXEL = 0.75

#: Approximate advance widths (em) per character class, used to wrap text. SVG
#: has no text metrics, and measuring fonts would need a font engine (a new
#: production dependency), so wrapping is estimated deterministically.
_NARROW = set("iljtfrI.,:;'!|()[]{}/\\-")
_WIDE = set("mMwWMW@")
_UPPER = set("ABCDEFGHIJKLMNOPQRSTUVWXYZĐÁÀẢÃẠĂẤẦẨẪẬÂẾỀỂỄỆÉÈẺẼẸÍÌỈĨỊÓÒỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÚÙỦŨỤƯỨỪỬỮỰÝỲỶỸỴ")
_DIGITS = set("0123456789")

#: ``a:prstDash`` -> SVG ``stroke-dasharray``.
DASH_PATTERNS = {
    "dash": "6 4",
    "sysDash": "4 3",
    "lgDash": "12 6",
    "dashDot": "6 3 1 3",
    "lgDashDot": "12 4 1 4",
    "lgDashDotDot": "12 4 1 4 1 4",
    "sysDashDot": "4 2 1 2",
    "sysDashDotDot": "4 2 1 2 1 2",
    "dot": "1 3",
    "sysDot": "1 2",
}


def _attr(value: str) -> str:
    """Escape text for an XML attribute (``escape`` alone leaves quotes)."""

    return escape(value, {'"': "&quot;", "'": "&apos;"})


def _num(value: float) -> str:
    """Compact, deterministic number formatting."""

    return f"{value:.2f}".rstrip("0").rstrip(".") or "0"


class _Canvas:
    """Mutable SVG assembly state for one slide (ids stay deterministic)."""

    def __init__(
        self,
        width: float,
        height: float,
        scene: SlideScene,
        media: Mapping[str, bytes],
        config: RenderConfig,
        warnings: list[str],
    ) -> None:
        self.width = width
        self.height = height
        self.scene = scene
        self.media = media
        self.config = config
        self.warnings = warnings
        self.defs: list[str] = []
        self._ids = 0
        self.inlined_bytes = 0
        #: How many times a run's typeface had to be substituted (V0-019 v5). Used
        #: per text frame to decide whether the platform's fit rule applies.
        self.substitutions = 0

    def next_id(self, prefix: str) -> str:
        self._ids += 1
        return f"{prefix}{self._ids}"

    # -- fills ------------------------------------------------------------------
    def paint(self, fill: Optional[dict]) -> str:
        """SVG paint attributes (``fill``/``fill-opacity``) for a ``Fill``."""

        if not fill or fill.get("type") == "none":
            return 'fill="none"'
        kind = fill.get("type")
        if kind == "solid":
            color = fill.get("color") or {}
            value = color.get("value") or self.config.background
            opacity = color.get("alpha")
            extra = "" if opacity in (None, 1.0) else f' fill-opacity="{_num(float(opacity))}"'
            return f'fill="{_attr(value)}"{extra}'
        if kind == "gradient":
            gradient_id = self._gradient(fill)
            return f'fill="url(#{gradient_id})"' if gradient_id else f'fill="{self.config.background}"'
        if kind == "picture":
            gradient_id = self._picture_fill(fill)
            return f'fill="url(#{gradient_id})"' if gradient_id else 'fill="none"'
        return 'fill="none"'

    def _gradient(self, fill: dict) -> Optional[str]:
        stops = [s for s in (fill.get("stops") or []) if s.get("color")]
        if not stops:
            return None
        gradient_id = self.next_id("grad")
        angle = math.radians(float(fill.get("angle") or 0.0))
        dx, dy = math.cos(angle) / 2, math.sin(angle) / 2
        self.defs.append(
            f'<linearGradient id="{gradient_id}" x1="{_num(0.5 - dx)}" y1="{_num(0.5 - dy)}" '
            f'x2="{_num(0.5 + dx)}" y2="{_num(0.5 + dy)}">'
            + "".join(
                f'<stop offset="{_num(float(stop.get("position") or 0.0) * 100)}%" '
                f'stop-color="{_attr((stop.get("color") or {}).get("value") or "#ffffff")}"'
                + (
                    ""
                    if (stop.get("color") or {}).get("alpha") in (None, 1.0)
                    else f' stop-opacity="{_num(float((stop.get("color") or {}).get("alpha")))}"'
                )
                + "/>"
                for stop in stops
            )
            + "</linearGradient>"
        )
        return gradient_id

    def _picture_fill(self, fill: dict) -> Optional[str]:
        href = self.image_href(fill.get("media_ref"))
        if href is None:
            return None
        pattern_id = self.next_id("fillimg")
        self.defs.append(
            f'<pattern id="{pattern_id}" patternContentUnits="objectBoundingBox" '
            f'width="1" height="1"><image href="{_attr(href)}" width="1" height="1" '
            f'preserveAspectRatio="none"/></pattern>'
        )
        return pattern_id

    # -- media ------------------------------------------------------------------
    def image_href(self, part: Optional[str], *, required: bool = True) -> Optional[str]:
        """A ``data:`` URI for an image part, honouring the per-slide budget."""

        if not part:
            if required:
                self.warnings.append(f"{UNSUPPORTED_MEDIA_PREFIX}unresolved")
            return None
        payload = self.media.get(part)
        if payload is None:
            if required:
                self.warnings.append(f"{MEDIA_UNAVAILABLE_PREFIX}{part}")
            return None
        if self.inlined_bytes + len(payload) > self.config.max_inline_media_bytes:
            if required:
                self.warnings.append(f"{MEDIA_BUDGET_PREFIX}{part}")
            return None
        mime = _mime_for(part)
        if mime is None:
            if required:
                self.warnings.append(f"{UNSUPPORTED_MEDIA_PREFIX}{_basename(part)}")
            return None
        self.inlined_bytes += len(payload)
        encoded = base64.b64encode(payload).decode("ascii")
        return f"data:{mime};base64,{encoded}"


def _mime_for(part: str) -> Optional[str]:
    from app.compiler.media import media_type_for_part

    return media_type_for_part(part)


def _basename(part: Optional[str]) -> str:
    return part.rsplit("/", 1)[-1] if part else ""


class StructuralSvgRenderer(DocumentRenderer):
    """Draws a slide from the IR's resolved styling, as one SVG per slide."""

    renderer_id = "local-structural-svg"
    renderer_version = "3.0.0"
    engine = "stdlib-svg"
    fidelity_ceiling = FIDELITY_STRUCTURAL

    def __init__(
        self,
        object_store=None,
        config: Optional[RenderConfig] = None,
        *,
        theme: Optional[MentoraTheme] = None,
    ) -> None:
        super().__init__(config=config, object_store=object_store)
        #: The platform look used *only* for components this renderer cannot
        #: reproduce (V0-019). The source's own styling is what is drawn elsewhere.
        self.theme = theme or DEFAULT_THEME

    # -- interface --------------------------------------------------------------
    def inspect_support(self) -> CapabilityReport:
        return CapabilityReport(
            supports=True,
            engine=self.engine,
            version=self.renderer_version,
            fidelity_ceiling=self.fidelity_ceiling,
            supported_kinds=self.supported_kinds,
            available_fonts=tuple(sorted(self.config.available_fonts)),
            reasons=(
                "structural renderer (default): the slide's own layout, theme "
                "colours/fonts, fills, pictures and text formatting are reproduced; "
                "layout metrics are approximate",
                "a component that cannot be reproduced (an unavailable source font, "
                "a chart/SmartArt, an un-inlinable picture) is drawn in the platform "
                "look in place and recorded as a warning, never dropped",
                "native PowerPoint rendering is an OPEN decision (DEC-TECH-005)",
            ),
        )

    def classify(
        self, *, missing_fonts: tuple[str, ...], unsupported_kinds: tuple[str, ...]
    ) -> str:
        """Always the ceiling: fallbacks replace degradation (V0-019 v5).

        Unlike the historical rule, an unavailable font or an undrawable object no
        longer lowers the fidelity here, because each is *drawn* in the platform
        look and only *warned* about. ``DEGRADED_RENDERED`` stays reachable for
        anything that genuinely cannot be drawn (e.g. a failed asset write).
        """

        del missing_fonts, unsupported_kinds
        return self.fidelity_ceiling

    # -- per scene --------------------------------------------------------------
    def _attempt_scene(
        self,
        request: RenderRequest,
        scene: SlideScene,
        token: CancelToken,
        budget: RenderBudget,
    ) -> SceneRender:
        started = time.monotonic()
        if token.cancelled:
            return self._cancelled(scene, "render cancelled")
        if budget.expired():
            return self._failed(scene, RenderErrorCode.RENDER_TIMEOUT, "render deadline exceeded")

        missing = self.missing_fonts(scene)
        unsupported = self.unsupported_kinds(scene)
        # An unavailable font is *substituted* in ``_family`` (which records
        # ``FONT_SUBSTITUTED:``); an unsupported object is drawn as a platform
        # panel below. Both are warnings on a structural render, not degradations.
        warnings: list[str] = [f"{UNSUPPORTED_OBJECT_PREFIX}{kind}" for kind in unsupported]

        try:
            payload = self._svg(request.document, scene, request.media, warnings)
            if len(payload) > self.config.max_asset_bytes:
                raise RendererError(
                    RenderErrorCode.OUTPUT_TOO_LARGE,
                    f"rendered asset is {len(payload)} bytes > {self.config.max_asset_bytes}",
                )
            asset_ref = self._persist_asset(payload, "svg")
        except RendererError as exc:
            return self._failed(scene, exc.code, exc.message)
        except Exception as exc:  # defensive: a bad scene must not sink the deck
            return self._failed(
                scene, RenderErrorCode.RENDER_FAILED, f"{type(exc).__name__}: {exc}"
            )

        if budget.expired():
            # The work is done but the end-to-end deadline was blown; the asset
            # is kept (it is content-addressed and reusable) and the scene is
            # reported as a retryable timeout.
            return self._failed(scene, RenderErrorCode.RENDER_TIMEOUT, "render deadline exceeded")

        fidelity = self.classify(missing_fonts=missing, unsupported_kinds=unsupported)
        if fidelity != self.fidelity_ceiling:
            warnings.append("fidelity degraded; meaning requires review")
        return SceneRender(
            order=scene.order,
            scene_id=scene.scene_id,
            status=RenderStatus.RENDERED,
            fidelity=fidelity,
            asset_ref=asset_ref,
            asset_bytes=len(payload),
            renderer=request.identity,
            fonts_used=tuple(scene.fonts()),
            missing_fonts=missing,
            warnings=tuple(warnings),
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    # -- SVG --------------------------------------------------------------------
    def _svg(
        self,
        document: ContentIRDocument,
        scene: SlideScene,
        media: Mapping[str, bytes],
        warnings: list[str],
    ) -> bytes:
        del document
        width, height = float(self.config.width_px), float(self.config.height_px)
        canvas = _Canvas(width, height, scene, media, self.config, warnings)
        body: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{_num(width)}" '
            f'height="{_num(height)}" viewBox="0 0 {_num(width)} {_num(height)}" role="img">',
            f"<title>{escape(scene.scene_id)}</title>",
            f'<rect x="0" y="0" width="{_num(width)}" height="{_num(height)}" '
            f'fill="{_attr(self.config.background)}"/>',
        ]
        background = scene.background
        if background and background.get("type") not in (None, "none"):
            body.append(self._background(canvas, background))
        for obj in sorted(scene.objects, key=lambda o: o.reading_order):
            body.append(self._object(canvas, obj))
        defs = "".join(canvas.defs)
        parts = [body[0], body[1], f"<defs>{defs}</defs>" if defs else "", *body[2:], "</svg>"]
        return "".join(part for part in parts if part).encode("utf-8")

    def _background(self, canvas: _Canvas, fill: dict) -> str:
        if fill.get("type") == "picture":
            href = canvas.image_href(fill.get("media_ref"))
            if href is None:
                return ""
            return (
                f'<image x="0" y="0" width="{_num(canvas.width)}" height="{_num(canvas.height)}" '
                f'preserveAspectRatio="none" href="{_attr(href)}"/>'
            )
        return (
            f'<rect x="0" y="0" width="{_num(canvas.width)}" height="{_num(canvas.height)}" '
            f'{canvas.paint(fill)}/>'
        )

    # -- geometry ---------------------------------------------------------------
    def _px_bounds(self, obj: ShapeObject, scene: SlideScene) -> tuple[float, float, float, float]:
        width, height = float(self.config.width_px), float(self.config.height_px)
        norm = (
            obj.bounds.normalized(scene.width, scene.height)
            if obj.bounds is not None
            else {"x": None, "y": None, "width": None, "height": None}
        )
        x = (norm["x"] if norm["x"] is not None else 0.0) * width
        y = (norm["y"] if norm["y"] is not None else 0.0) * height
        box_w = (norm["width"] if norm["width"] is not None else 1.0) * width
        box_h = (norm["height"] if norm["height"] is not None else 0.06) * height
        # Keep everything inside the canvas so a bad source cannot produce
        # off-canvas geometry. Bounds may legitimately extend past the slide
        # (PowerPoint allows it), so clamp rather than drop.
        x = max(0.0, min(x, width))
        y = max(0.0, min(y, height))
        box_w = max(0.5, min(box_w, width - x))
        box_h = max(0.5, min(box_h, height - y))
        return x, y, box_w, box_h

    def _transform(self, obj: ShapeObject, x: float, y: float, w: float, h: float) -> str:
        """Rotation/flip about the shape centre, matching ``a:xfrm`` semantics."""

        parts: list[str] = []
        if obj.rotation:
            parts.append(
                f"rotate({_num(obj.rotation)} {_num(x + w / 2)} {_num(y + h / 2)})"
            )
        if obj.flip_h or obj.flip_v:
            sx = -1 if obj.flip_h else 1
            sy = -1 if obj.flip_v else 1
            parts.append(
                f"translate({_num(x + w / 2)} {_num(y + h / 2)}) scale({sx} {sy}) "
                f"translate({_num(-(x + w / 2))} {_num(-(y + h / 2))})"
            )
        return f' transform="{" ".join(parts)}"' if parts else ""

    def _stroke_attrs(self, canvas: _Canvas, line: Optional[dict]) -> str:
        if not line:
            return ""
        color = (line.get("color") or {})
        value = color.get("value")
        if value is None:
            value = "#1f2937"
        width_px = max(0.5, float(line.get("width_emu") or 12700) / EMU_PER_PIXEL)
        attrs = [f'stroke="{_attr(value)}"', f'stroke-width="{_num(width_px)}"']
        opacity = color.get("alpha")
        if opacity not in (None, 1.0):
            attrs.append(f'stroke-opacity="{_num(float(opacity))}"')
        dash = DASH_PATTERNS.get(str(line.get("dash") or "solid"))
        if dash:
            attrs.append(f'stroke-dasharray="{dash}"')
        return " " + " ".join(attrs)

    def _shape_body(self, canvas: _Canvas, obj: ShapeObject, x: float, y: float, w: float, h: float) -> str:
        """The fill/stroke element(s) for a shape's geometry ("" when invisible)."""

        paint = canvas.paint(obj.fill)
        stroke = self._stroke_attrs(canvas, obj.line)
        if not obj.line and not obj.custom_path and paint == 'fill="none"':
            # Text boxes and layout rulers carry no fill and no outline; an
            # invisible rectangle for each of them is pure payload noise.
            return ""
        if obj.custom_path:
            element = (
                f'<path d="{_attr(obj.custom_path)}" '
                f'transform="translate({_num(x)} {_num(y)}) scale({_num(w)} {_num(h)})" '
                f'vector-effect="non-scaling-stroke"'
            )
            return f"{element} {paint}{stroke}/>"
        preset = obj.geometry or "rect"
        geometry = self._geometry(preset, x, y, w, h)
        if geometry is None:
            # A shape we do not model still gets a visible structural body.
            canvas.warnings.append(f"{UNSUPPORTED_GEOMETRY_PREFIX}{preset}")
            geometry = (
                f'<rect x="{_num(x)}" y="{_num(y)}" width="{_num(w)}" height="{_num(h)}" '
                f'rx="{_num(min(w, h) * 0.08)}"'
            )
        if preset == "line":
            return geometry + stroke + "/>"
        return geometry + f" {paint}{stroke}/>"

    @staticmethod
    def _geometry(preset: str, x: float, y: float, w: float, h: float) -> Optional[str]:
        """SVG element (without closing) for a DrawingML preset geometry."""

        cx, cy = x + w / 2, y + h / 2
        if preset in ("rect", "rectangle"):
            return f'<rect x="{_num(x)}" y="{_num(y)}" width="{_num(w)}" height="{_num(h)}"'
        if preset in ("roundRect", "round1Rect", "round2SameRect", "round2DiagRect"):
            radius = min(w, h) * 0.16
            return (
                f'<rect x="{_num(x)}" y="{_num(y)}" width="{_num(w)}" height="{_num(h)}" '
                f'rx="{_num(radius)}" ry="{_num(radius)}"'
            )
        if preset in ("ellipse", "circle"):
            return (
                f'<ellipse cx="{_num(cx)}" cy="{_num(cy)}" rx="{_num(w / 2)}" ry="{_num(h / 2)}"'
            )
        if preset == "triangle":
            return (
                f'<polygon points="{_num(cx)},{_num(y)} {_num(x + w)},{_num(y + h)} '
                f'{_num(x)},{_num(y + h)}"'
            )
        if preset == "rtTriangle":
            return (
                f'<polygon points="{_num(x)},{_num(y)} {_num(x)},{_num(y + h)} '
                f'{_num(x + w)},{_num(y + h)}"'
            )
        if preset == "diamond":
            return (
                f'<polygon points="{_num(cx)},{_num(y)} {_num(x + w)},{_num(cy)} '
                f'{_num(cx)},{_num(y + h)} {_num(x)},{_num(cy)}"'
            )
        if preset == "pentagon":
            points = _regular_polygon(cx, cy, w / 2, h / 2, 5, -90)
            return f'<polygon points="{points}"'
        if preset == "hexagon":
            points = _regular_polygon(cx, cy, w / 2, h / 2, 6, 0)
            return f'<polygon points="{points}"'
        if preset == "star5":
            points = _star_points(cx, cy, w / 2, h / 2, 5)
            return f'<polygon points="{points}"'
        if preset in ("rightArrow", "leftArrow", "upArrow", "downArrow"):
            return f'<polygon points="{_arrow_points(preset, x, y, w, h)}"'
        if preset == "plus":
            arm_x, arm_y = w * 0.33, h * 0.33
            return (
                f'<polygon points="{_num(x + arm_x)},{_num(y)} {_num(x + w - arm_x)},{_num(y)} '
                f'{_num(x + w - arm_x)},{_num(y + arm_y)} {_num(x + w)},{_num(y + arm_y)} '
                f'{_num(x + w)},{_num(y + h - arm_y)} {_num(x + w - arm_x)},{_num(y + h - arm_y)} '
                f'{_num(x + w - arm_x)},{_num(y + h)} {_num(x + arm_x)},{_num(y + h)} '
                f'{_num(x + arm_x)},{_num(y + h - arm_y)} {_num(x)},{_num(y + h - arm_y)} '
                f'{_num(x)},{_num(y + arm_y)} {_num(x + arm_x)},{_num(y + arm_y)}"'
            )
        if preset in ("line", "straightConnector1"):
            return (
                f'<line x1="{_num(x)}" y1="{_num(y)}" x2="{_num(x + w)}" y2="{_num(y + h)}" '
                f'fill="none"'
            )
        return None

    # -- objects ----------------------------------------------------------------
    def _object(self, canvas: _Canvas, obj: ShapeObject) -> str:
        x, y, w, h = self._px_bounds(obj, canvas.scene)
        transform = self._transform(obj, x, y, w, h)

        if obj.kind == "group":
            # Children are emitted separately with absolute bounds; the container
            # itself paints nothing (its own frame is not drawn by PowerPoint).
            return ""

        if obj.kind == "picture":
            return self._picture(canvas, obj, x, y, w, h, transform)

        if obj.kind == "table":
            return self._table(canvas, obj, x, y, w, h, transform)

        if obj.kind in ("chart", "graphicFrame"):
            return self._placeholder(canvas, obj, x, y, w, h, transform)

        if obj.kind == "connector":
            return self._connector(canvas, obj, x, y, w, h, transform)

        body = self._shape_body(canvas, obj, x, y, w, h)
        text = self._text_block(canvas, obj, x, y, w, h)
        if transform and (body or text):
            return f'<g{transform}>{body}{text}</g>'
        return body + text

    def _picture(
        self,
        canvas: _Canvas,
        obj: ShapeObject,
        x: float,
        y: float,
        w: float,
        h: float,
        transform: str,
    ) -> str:
        if obj.media_type is None:
            return self._media_placeholder(canvas, obj, x, y, w, h, transform)
        href = canvas.image_href(obj.media_ref)
        if href is None:
            return self._media_placeholder(canvas, obj, x, y, w, h, transform)
        crop = obj.crop or {}
        left = float(crop.get("left") or 0.0)
        top = float(crop.get("top") or 0.0)
        right = float(crop.get("right") or 0.0)
        bottom = float(crop.get("bottom") or 0.0)
        keep_w = max(0.01, 1.0 - left - right)
        keep_h = max(0.01, 1.0 - top - bottom)
        inner = ""
        if left or top or right or bottom:
            # ``a:srcRect`` semantics: the kept window is scaled to fill the frame.
            full_w, full_h = w / keep_w, h / keep_h
            image_x, image_y = x - left * full_w, y - top * full_h
            clip_id = canvas.next_id("clip")
            canvas.defs.append(
                f'<clipPath id="{clip_id}"><rect x="{_num(x)}" y="{_num(y)}" '
                f'width="{_num(w)}" height="{_num(h)}"/></clipPath>'
            )
            inner = (
                f'<image x="{_num(image_x)}" y="{_num(image_y)}" width="{_num(full_w)}" '
                f'height="{_num(full_h)}" preserveAspectRatio="none" href="{_attr(href)}" '
                f'clip-path="url(#{clip_id})"/>'
            )
        else:
            inner = (
                f'<image x="{_num(x)}" y="{_num(y)}" width="{_num(w)}" height="{_num(h)}" '
                f'preserveAspectRatio="none" href="{_attr(href)}"/>'
            )
        parts = [f'<g{transform}>{inner}</g>' if transform else inner]
        if obj.line:
            stroke = self._stroke_attrs(canvas, obj.line)
            parts.append(
                f'<rect x="{_num(x)}" y="{_num(y)}" width="{_num(w)}" height="{_num(h)}" '
                f'fill="none"{stroke}/>'
            )
        return "".join(parts)

    def _media_placeholder(
        self,
        canvas: _Canvas,
        obj: ShapeObject,
        x: float,
        y: float,
        w: float,
        h: float,
        transform: str,
    ) -> str:
        label = _basename(obj.media_ref) or obj.name or "image"
        return self._platform_panel(canvas, x, y, w, h, label, transform)

    def _placeholder(
        self,
        canvas: _Canvas,
        obj: ShapeObject,
        x: float,
        y: float,
        w: float,
        h: float,
        transform: str,
    ) -> str:
        label = f"{obj.kind}: {obj.name or _basename(obj.media_ref)}"
        warning = f"{UNSUPPORTED_OBJECT_PREFIX}{obj.kind}"
        if warning not in canvas.warnings:
            canvas.warnings.append(warning)
        return self._platform_panel(canvas, x, y, w, h, label, transform)

    def _platform_panel(
        self,
        canvas: _Canvas,
        x: float,
        y: float,
        w: float,
        h: float,
        label: str,
        transform: str,
    ) -> str:
        """The app's default look for a component the source cannot be reproduced for.

        V0-019: the slide keeps the author's layout, and anything this renderer
        cannot reproduce (a chart/SmartArt, a picture it cannot inline, an
        unavailable font) is painted in the platform theme *in place* — flat
        surface, one hairline border, the theme's own type stack — so the deck
        reads as one document instead of showing a foreign grey box. The warning
        still names the object; only the pixels are the platform's.
        """

        theme = self.theme
        scale = h / theme.panel_px if theme.panel_px else 1.0
        size = max(9.0, theme.panel_label_px * min(1.0, scale))
        body = (
            f'<rect x="{_num(x)}" y="{_num(y)}" width="{_num(w)}" height="{_num(h)}" '
            f'rx="8" fill="{_attr(theme.surface)}" stroke="{_attr(theme.border)}" '
            f'stroke-width="1"/>'
            f'<text x="{_num(x + w / 2)}" y="{_num(y + h / 2 + size / 3)}" '
            f'text-anchor="middle" font-family="{_attr(theme.font_stack)}" '
            f'font-size="{_num(size)}" fill="{_attr(theme.muted)}">{escape(label)}</text>'
        )
        return f'<g{transform}>{body}</g>' if transform else body

    def _connector(
        self,
        canvas: _Canvas,
        obj: ShapeObject,
        x: float,
        y: float,
        w: float,
        h: float,
        transform: str,
    ) -> str:
        x1, y1, x2, y2 = x, y, x + w, y + h
        if obj.flip_h:
            x1, x2 = x2, x1
        if obj.flip_v:
            y1, y2 = y2, y1
        stroke = self._stroke_attrs(canvas, obj.line) or ' stroke="#475569" stroke-width="1"'
        line = (
            f'<line x1="{_num(x1)}" y1="{_num(y1)}" x2="{_num(x2)}" y2="{_num(y2)}" '
            f"fill=\"none\"{stroke}/>"
        )
        return f'<g{transform}>{line}</g>' if transform else line

    # -- tables -----------------------------------------------------------------
    def _table(
        self,
        canvas: _Canvas,
        obj: ShapeObject,
        x: float,
        y: float,
        w: float,
        h: float,
        transform: str,
    ) -> str:
        rows = obj.table or []
        if not rows:
            return (
                f'<rect x="{_num(x)}" y="{_num(y)}" width="{_num(w)}" height="{_num(h)}" '
                f'fill="#ffffff" stroke="#0f766e" stroke-width="1"/>'
            )
        cells = obj.table_cells or []
        column_count = max(len(row) for row in rows)
        widths = self._table_sizes(obj.table_columns, column_count, w)
        heights = self._table_sizes(obj.table_rows, len(rows), h)
        parts: list[str] = [
            f'<rect x="{_num(x)}" y="{_num(y)}" width="{_num(w)}" height="{_num(h)}" fill="#ffffff"/>'
        ]
        row_y = y
        for row_index, row in enumerate(rows):
            row_h = heights[row_index] if row_index < len(heights) else h / max(1, len(rows))
            column_x = x
            for column_index, cell_text in enumerate(row):
                column_w = widths[column_index] if column_index < len(widths) else w / max(1, column_count)
                cell = self._cell(cells, row_index, column_index)
                if cell is not None and (cell.h_merge or cell.v_merge):
                    column_x += column_w
                    continue
                span = cell.grid_span if cell is not None else 1
                spanned_w = sum(
                    widths[column_index + extra]
                    for extra in range(span)
                    if column_index + extra < len(widths)
                ) or column_w
                fill = canvas.paint(cell.fill) if cell and cell.fill else 'fill="none"'
                border = ' stroke="#cbd5e1" stroke-width="1"'
                parts.append(
                    f'<rect x="{_num(column_x)}" y="{_num(row_y)}" width="{_num(spanned_w)}" '
                    f'height="{_num(row_h)}" {fill}{border}/>'
                )
                paragraphs = cell.paragraphs if cell is not None else []
                if not paragraphs and cell_text:
                    paragraphs = [TextParagraph(level=0, text=cell_text)]
                parts.append(
                    self._text_block(
                        canvas,
                        obj,
                        column_x,
                        row_y,
                        spanned_w,
                        row_h,
                        paragraphs=paragraphs,
                        default_align="ctr",
                        default_size_pt=12.0,
                    )
                )
                column_x += spanned_w
            row_y += row_h
        body = "".join(parts)
        return f'<g{transform}>{body}</g>' if transform else body

    @staticmethod
    def _cell(cells: list[list[TableCell]], row: int, column: int) -> Optional[TableCell]:
        if row < len(cells) and column < len(cells[row]):
            return cells[row][column]
        return None

    @staticmethod
    def _table_sizes(values: Optional[list[int]], count: int, extent: float) -> list[float]:
        """Column/row sizes in px: use the source EMU metrics, scaled to the frame."""

        if not values or count <= 0:
            return [extent / max(1, count)] * max(1, count)
        total = sum(values)
        if total <= 0:
            return [extent / max(1, count)] * max(1, count)
        return [extent * value / total for value in values]

    # -- text -------------------------------------------------------------------
    def _text_block(
        self,
        canvas: _Canvas,
        obj: ShapeObject,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        paragraphs: Optional[list[TextParagraph]] = None,
        default_align: Optional[str] = None,
        default_size_pt: Optional[float] = None,
    ) -> str:
        content = obj.paragraphs if paragraphs is None else paragraphs
        if not content:
            return ""
        insets = obj.insets or DEFAULT_INSETS_EMU
        inset_l = float(insets.get("left", DEFAULT_INSETS_EMU["left"])) / EMU_PER_PIXEL
        inset_t = float(insets.get("top", DEFAULT_INSETS_EMU["top"])) / EMU_PER_PIXEL
        inset_r = float(insets.get("right", DEFAULT_INSETS_EMU["right"])) / EMU_PER_PIXEL
        inset_b = float(insets.get("bottom", DEFAULT_INSETS_EMU["bottom"])) / EMU_PER_PIXEL
        available_w = max(4.0, w - inset_l - inset_r)
        available_h = max(4.0, h - inset_t - inset_b)
        base_scale = float(obj.font_scale or 1.0)

        substitutions_before = canvas.substitutions
        layout = self._layout_text(
            canvas,
            content,
            x + inset_l,
            available_w,
            base_scale,
            default_align,
            default_size_pt,
        )
        # Auto-shrink (``a:normAutofit``/``a:spAutoFit`` behaviour): PowerPoint
        # never overflows a text box, so neither do we. V0-019 v5 adds one case:
        # when this frame's typeface had to be *substituted*, the platform's font
        # is not the author's, so its metrics are not the author's either — the
        # frame and its content are kept, but the text is shrunk to stay inside the
        # frame instead of spilling over a neighbouring block. A frame the source
        # font already fits is left at its authored size.
        substituted = canvas.substitutions > substitutions_before
        if layout["height"] > available_h and (
            obj.autofit in (None, "shrink", "resize") or substituted
        ):
            scale = base_scale
            for _ in range(6):
                if layout["height"] <= available_h or scale <= 0.4:
                    break
                scale = max(0.4, scale * (available_h / layout["height"]) * 0.98)
                layout = self._layout_text(
                    canvas,
                    content,
                    x + inset_l,
                    available_w,
                    scale,
                    default_align,
                    default_size_pt,
                )

        anchor = obj.anchor or "t"
        if anchor == "ctr":
            cursor = y + inset_t + max(0.0, (available_h - layout["height"]) / 2)
        elif anchor == "b":
            cursor = y + inset_t + max(0.0, available_h - layout["height"])
        else:
            cursor = y + inset_t

        parts: list[str] = []
        for line in layout["lines"]:
            line_top = cursor
            if line_top > canvas.height:
                # Past the bottom of the slide: nothing of this line is visible.
                # ``a:noAutofit`` means "do not shrink, do not clip" — PowerPoint
                # lets the text spill past the frame, and so do we, because a
                # silent truncation would lose content.
                break
            baseline = line_top + line["size_px"] * 0.82
            if line.get("highlight"):
                parts.append(
                    f'<rect x="{_num(line["x"])}" y="{_num(line_top)}" '
                    f'width="{_num(line["width"])}" height="{_num(line["line_height"])}" '
                    f'fill="{_attr(line["highlight"])}"/>'
                )
            if line.get("bullet"):
                parts.append(
                    f'<text x="{_num(line["x"] - line["size_px"] * 0.9)}" '
                    f'y="{_num(baseline)}" font-family="{_attr(line["family"])}" '
                    f'font-size="{_num(line["size_px"])}" fill="{_attr(line["color"])}">'
                    f"{escape(line['bullet'])}</text>"
                )
            attributes = [
                f'x="{_num(line["x"])}"',
                f'y="{_num(baseline)}"',
                f'font-family="{_attr(line["family"])}"',
                f'font-size="{_num(line["size_px"])}"',
                f'fill="{_attr(line["color"])}"',
            ]
            if line["bold"]:
                attributes.append('font-weight="bold"')
            if line["italic"]:
                attributes.append('font-style="italic"')
            if line["underline"]:
                attributes.append('text-decoration="underline"')
            if line["anchor"] != "start":
                attributes.append(f'text-anchor="{line["anchor"]}"')
            parts.append(
                f'<text {" ".join(attributes)} xml:space="preserve">{escape(line["text"])}</text>'
            )
            cursor = line_top + line["line_height"]
        return "".join(parts)

    def _layout_text(
        self,
        canvas: _Canvas,
        paragraphs: list[TextParagraph],
        origin_x: float,
        available_w: float,
        scale: float,
        default_align: Optional[str],
        default_size_pt: Optional[float],
    ) -> dict[str, Any]:
        """Wrap and position every paragraph: returns ``{\"lines\", \"height\"}``.

        Line boxes are laid out top-down; the caller turns each line into text
        (baseline = top + 0.82 em) so vertical anchoring and auto-shrink agree.
        """

        lines: list[dict[str, Any]] = []
        total = 0.0
        for para in paragraphs:
            align = para.align or default_align or "l"
            runs = para.runs or []
            size_pt = default_size_pt
            for run in runs:
                if run.size_pt:
                    size_pt = run.size_pt
                    break
            size_px = max(6.0, (size_pt or 18.0) * scale / PT_PER_PIXEL)
            bold = any(run.bold for run in runs)
            italic = any(run.italic for run in runs)
            underline = any(run.underline for run in runs)
            run_font = next((run.font for run in runs if run.font), None)
            family = self._family(canvas, run_font)
            color = self._run_color(runs)
            highlight = self._run_highlight(runs)
            bullet = self._bullet_text(para)
            margin = float(para.margin_left_emu or 0) / EMU_PER_PIXEL
            indent = margin if align in ("l", "just", "dist") else 0.0
            wrapped = _wrap(para.text, size_px, max(4.0, available_w - indent), bold)
            line_height = _line_height(para, size_px)
            total += float(para.space_before_pt or 0.0) / PT_PER_PIXEL
            for index, piece in enumerate(wrapped):
                anchor = {
                    "l": "start",
                    "just": "start",
                    "dist": "start",
                    "ctr": "middle",
                    "r": "end",
                }.get(align, "start")
                if anchor == "middle":
                    line_x = origin_x + indent + (available_w - indent) / 2
                elif anchor == "end":
                    line_x = origin_x + available_w
                else:
                    line_x = origin_x + indent
                lines.append(
                    {
                        "text": piece,
                        "x": line_x,
                        "size_px": size_px,
                        "line_height": line_height,
                        "family": family,
                        "color": color,
                        "bold": bold,
                        "italic": italic,
                        "underline": underline,
                        "anchor": anchor,
                        "highlight": highlight,
                        "bullet": bullet if index == 0 else None,
                        "width": _text_width(piece, size_px, bold),
                    }
                )
                total += line_height
            total += float(para.space_after_pt or 0.0) / PT_PER_PIXEL
        return {"lines": lines, "height": total}

    @staticmethod
    def _bullet_text(para: TextParagraph) -> Optional[str]:
        bullet = para.bullet or {}
        if not bullet or bullet.get("none"):
            return None
        if bullet.get("char"):
            return str(bullet["char"])
        if bullet.get("autonum"):
            return "•"
        return None

    def _family(self, canvas: _Canvas, family: Optional[str]) -> str:
        """The ``font-family`` for a run (V0-019: the app's font, in place).

        An unavailable source family is *substituted* with the platform's type
        stack rather than merely listed first, so the asset does not depend on
        which fonts the client happens to have — one deck, one render. The
        substitution is recorded as ``FONT_SUBSTITUTED:<family>``.
        """

        if not family:
            return self.theme.font_stack
        if family in canvas.config.available_fonts:
            return f"{family}, {self.theme.font_stack}"
        canvas.substitutions += 1
        warning = f"{FONT_SUBSTITUTED_PREFIX}{family}"
        if warning not in canvas.warnings:
            canvas.warnings.append(warning)
        return self.theme.font_stack

    @staticmethod
    def _run_color(runs: list) -> str:
        for run in runs:
            color = run.color or {}
            if color.get("value"):
                return str(color["value"])
        return DEFAULT_TEXT_COLOR

    @staticmethod
    def _run_highlight(runs: list) -> Optional[str]:
        for run in runs:
            highlight = run.highlight or {}
            if highlight.get("value"):
                return str(highlight["value"])
        return None


# -- pure geometry helpers ---------------------------------------------------------
def _regular_polygon(cx: float, cy: float, rx: float, ry: float, sides: int, start_deg: float) -> str:
    points = []
    for index in range(sides):
        angle = math.radians(start_deg + index * 360.0 / sides)
        points.append(f"{_num(cx + rx * math.cos(angle))},{_num(cy + ry * math.sin(angle))}")
    return " ".join(points)


def _star_points(cx: float, cy: float, rx: float, ry: float, points_count: int) -> str:
    points = []
    for index in range(points_count * 2):
        radius = 1.0 if index % 2 == 0 else 0.382
        angle = math.radians(-90 + index * 180.0 / points_count)
        points.append(f"{_num(cx + rx * radius * math.cos(angle))},{_num(cy + ry * radius * math.sin(angle))}")
    return " ".join(points)


def _arrow_points(preset: str, x: float, y: float, w: float, h: float) -> str:
    """A block arrow as a 7-point polygon, rotated to the requested direction."""

    def point(px: float, py: float) -> str:
        if preset == "leftArrow":
            px, py = 1.0 - px, py
        elif preset == "upArrow":
            px, py = py, 1.0 - px
        elif preset == "downArrow":
            px, py = 1.0 - py, px
        return f"{_num(x + px * w)},{_num(y + py * h)}"

    return " ".join(
        [
            point(0.0, 0.30),
            point(0.60, 0.30),
            point(0.60, 0.0),
            point(1.0, 0.5),
            point(0.60, 1.0),
            point(0.60, 0.70),
            point(0.0, 0.70),
        ]
    )


def _line_height(para: TextParagraph, size_px: float) -> float:
    """Line box height in px.

    ``a:lnSpc/a:spcPts`` is an absolute leading in points, so it wins over the
    multiple form; otherwise 1.2 em (PowerPoint's default single spacing).
    """

    if para.line_spacing_pt:
        return max(1.0, float(para.line_spacing_pt) / PT_PER_PIXEL)
    return size_px * 1.2 * float(para.line_spacing or 1.0)


def _text_width(text: str, size_px: float, bold: bool) -> float:
    total = 0.0
    for char in text:
        if char in _NARROW:
            total += 0.33
        elif char in _WIDE:
            total += 0.95
        elif char in _UPPER:
            total += 0.68
        elif char in _DIGITS:
            total += 0.58
        elif char == " ":
            total += 0.30
        else:
            total += 0.55
    return total * size_px * (1.04 if bold else 1.0)


def _wrap(text: str, size_px: float, max_width: float, bold: bool) -> list[str]:
    """Greedy word wrap using estimated advances (deterministic, font-free)."""

    lines: list[str] = []
    for raw_line in text.split("\n"):
        if not raw_line:
            lines.append("")
            continue
        current = ""
        for word in raw_line.split(" "):
            trial = word if not current else f"{current} {word}"
            if current and _text_width(trial, size_px, bold) > max_width:
                lines.append(current)
                current = word
            else:
                current = trial
        lines.append(current)
    return lines or [""]
