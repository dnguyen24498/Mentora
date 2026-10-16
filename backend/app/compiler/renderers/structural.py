"""Deterministic local renderer: Content IR -> SVG fallback asset per slide.

This is the *local/dev* implementation of the ``DocumentRenderer`` interface
used while ``DEC-TECH-005`` (native PowerPoint rendering) is OPEN. It is
dependency-free (``xml.sax.saxutils`` + the object store) and pure: the same
document and the same config always produce byte-identical output, which is what
"same engine/config gives stable logical output" means for the fidelity gate.

It never reads the original package and never executes active content
(``DEC-CONTENT-001``): the only input is the Content IR.
"""

from __future__ import annotations

import time
from typing import Optional
from xml.sax.saxutils import escape

from app.compiler.models.ir import (
    FIDELITY_STRUCTURAL,
    ContentIRDocument,
    ShapeObject,
    SlideScene,
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

#: Emitted as ``MISSING_FONT:<family>`` so warnings stay greppable/metricable.
MISSING_FONT_PREFIX = "MISSING_FONT:"
#: Emitted as ``UNSUPPORTED_OBJECT:<kind>``.
UNSUPPORTED_OBJECT_PREFIX = "UNSUPPORTED_OBJECT:"


def _attr(value: str) -> str:
    """Escape text for an XML attribute (``escape`` alone leaves quotes)."""

    return escape(value, {'"': "&quot;", "'": "&apos;"})


class StructuralSvgRenderer(DocumentRenderer):
    """Draws boxes/text/tables from IR geometry as an SVG per slide."""

    renderer_id = "local-structural-svg"
    renderer_version = "1.0.0"
    engine = "stdlib-svg"
    fidelity_ceiling = FIDELITY_STRUCTURAL

    def __init__(self, object_store=None, config: Optional[RenderConfig] = None) -> None:
        super().__init__(config=config, object_store=object_store)

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
                "structural renderer: layout fidelity is approximate by design",
                "native PowerPoint rendering is an OPEN decision (DEC-TECH-005)",
            ),
        )

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
        warnings: list[str] = [f"{MISSING_FONT_PREFIX}{f}" for f in missing]
        warnings += [f"{UNSUPPORTED_OBJECT_PREFIX}{kind}" for kind in unsupported]

        try:
            payload = self._svg(request.document, scene)
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
    def _svg(self, document: ContentIRDocument, scene: SlideScene) -> bytes:
        width, height = self.config.width_px, self.config.height_px
        parts: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img">',
            f'<title>{escape(scene.scene_id)}</title>',
            f'<rect x="0" y="0" width="{width}" height="{height}" '
            f'fill="{_attr(self.config.background)}"/>',
        ]
        for obj in sorted(scene.objects, key=lambda o: o.reading_order):
            parts.append(self._svg_object(obj, scene))
        parts.append("</svg>")
        return "".join(parts).encode("utf-8")

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
        # off-canvas geometry.
        x = max(0.0, min(x, width))
        y = max(0.0, min(y, height))
        box_w = max(1.0, min(box_w, width - x))
        box_h = max(1.0, min(box_h, height - y))
        return x, y, box_w, box_h

    def _svg_object(self, obj: ShapeObject, scene: SlideScene) -> str:
        x, y, box_w, box_h = self._px_bounds(obj, scene)
        out: list[str] = []

        if obj.kind == "picture":
            out.append(self._rect(x, y, box_w, box_h, stroke="#94a3b8", fill="#f1f5f9"))
            out.append(self._label(x, y, self._basename(obj.media_ref) or obj.name or "image", 11))
        elif obj.kind == "chart":
            out.append(self._rect(x, y, box_w, box_h, stroke="#7c3aed", fill="#f5f3ff"))
            out.append(self._label(x + 6, y + 14, f"chart: {self._basename(obj.media_ref) or obj.name}", 12))
        elif obj.kind == "table":
            out.append(self._table(obj, x, y, box_w, box_h))
        elif obj.kind == "connector":
            out.append(
                f'<line x1="{x:.2f}" y1="{y:.2f}" x2="{x + box_w:.2f}" y2="{y + box_h:.2f}" '
                f'stroke="#475569" stroke-width="1.5"/>'
            )
        elif obj.kind == "group":
            out.append(
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{box_w:.2f}" height="{box_h:.2f}" '
                f'fill="none" stroke="#cbd5e1" stroke-width="1" stroke-dasharray="4 3"/>'
            )
        else:
            out.append(self._rect(x, y, box_w, box_h, stroke="#e2e8f0", fill="none"))

        out.extend(self._svg_paragraphs(obj, x, y, box_w, box_h))
        return "".join(out)

    def _svg_paragraphs(
        self, obj: ShapeObject, x: float, y: float, box_w: float, box_h: float
    ) -> list[str]:
        parts: list[str] = []
        # Line height scales with the object so text stays inside its box.
        line_height = 18.0
        available = max(1, int(box_h // line_height))
        for index, para in enumerate(obj.paragraphs[:available]):
            size = max(10, 16 - 2 * para.level)
            family = (para.runs[0].font if para.runs and para.runs[0].font else None) or (
                self.config.font_family
            )
            text_x = x + 6 + 12 * para.level
            text_y = y + line_height * (index + 1)
            parts.append(
                f'<text x="{text_x:.2f}" y="{text_y:.2f}" '
                f'font-family="{_attr(family)}" font-size="{size}">{escape(para.text)}</text>'
            )
        return parts

    def _table(self, obj: ShapeObject, x: float, y: float, box_w: float, box_h: float) -> str:
        rows = obj.table or []
        if not rows:
            return self._rect(x, y, box_w, box_h, stroke="#0f766e", fill="#f0fdfa")
        computed = min(len(rows), 12)  # bounded: do not emit a huge document
        row_h = box_h / computed
        parts = [self._rect(x, y, box_w, box_h, stroke="#0f766e", fill="#ffffff")]
        for row_index, row in enumerate(rows[:computed]):
            row_y = y + row_h * row_index
            parts.append(self._rect(x, row_y, box_w, row_h, stroke="#99f6e4", fill="none"))
            cell_w = box_w / max(1, len(row))
            for cell_index, cell in enumerate(row):
                parts.append(
                    f'<text x="{x + cell_w * cell_index + 4:.2f}" y="{row_y + row_h - 4:.2f}" '
                    f'font-family="{_attr(self.config.font_family)}" font-size="11">'
                    f"{escape(str(cell))}</text>"
                )
        return "".join(parts)

    def _rect(self, x: float, y: float, width: float, height: float, *, stroke: str, fill: str) -> str:
        return (
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{width:.2f}" height="{height:.2f}" '
            f'fill="{_attr(fill)}" stroke="{_attr(stroke)}" stroke-width="1"/>'
        )

    def _label(self, x: float, y: float, text: str, size: int) -> str:
        return (
            f'<text x="{x + 4:.2f}" y="{y + 14:.2f}" '
            f'font-family="{_attr(self.config.font_family)}" font-size="{size}">{escape(text)}</text>'
        )

    @staticmethod
    def _basename(part: str | None) -> str:
        return part.rsplit("/", 1)[-1] if part else ""
