"""Platform-themed renderer (V0-019): the author's layout, the platform's look.

This is the default render mode. It shares the *geometry engine* of
``renderers/structural.py`` — every object is drawn where the author put it, at
the size the author gave it — and overrides only the **styling** decisions:
typeface, text colour, fills, strokes, slide chrome, and the background palette
(``renderers/mentora_theme.py``).

Why the layout is preserved
---------------------------
V0-019 first re-flowed the extracted content into a platform-owned layout. On a
real, art-directed deck (banded headings, kickers, rules, small logos, picture
grids) that produced collisions and unreadable slides: a re-flow must *guess*
text metrics, and every guess is a chance for one block to overrun the next.
Keeping the author's layout removes the guessing. Two objects can now only
overlap if the author drew them overlapping, and the platform's own chrome (the
accent band, the footer) is drawn only where the source left the strip empty.

Consequences
------------
* **The font problem disappears.** ``_family`` always returns the theme stack, so
  ``missing_fonts()`` is empty by construction: an unavailable source font can no
  longer degrade a themed scene.
* **The gate is content completeness, not resemblance.** Nothing is re-selected,
  re-ordered, clipped, or dropped, so no code path can lose content. A text frame
  that cannot hold its text — an ``a:noAutofit`` box where a whole line lands
  past the frame's bottom edge — still draws every line, the way PowerPoint does,
  and is reported as ``TEXT_OVERFLOW:<object>`` and degraded for review instead of
  being truncated in silence. (Text whose descenders merely dip a few pixels past
  a tight frame is normal typography and is not degraded.)
* **Contrast is preserved.** The theme maps colours by role
  (``map_text``/``map_fill``/``map_line``), so a light-on-dark pair in the source
  stays light-on-dark afterwards and re-colouring cannot hide text.

It is still **not** a native PowerPoint render and is never reported as one
(``DEC-CONTENT-006``): the only inputs are the Content IR and the picture bytes
the compiler injects (``DEC-CONTENT-001``), and ``DEC-TECH-005`` (native
rendering) stays OPEN.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Mapping, Optional
from xml.sax.saxutils import escape

from app.compiler.models.ir import (
    FIDELITY_DEGRADED,
    FIDELITY_THEMED,
    ShapeObject,
    SlideScene,
)
from app.compiler.renderers.base import (
    CancelToken,
    CapabilityReport,
    RenderBudget,
    RenderConfig,
    RenderRequest,
    RenderStatus,
    RendererIdentity,
    SceneRender,
)
from app.compiler.renderers.mentora_theme import DEFAULT_THEME, MentoraTheme
from app.compiler.renderers.structural import (
    PT_PER_PIXEL,
    StructuralSvgRenderer,
    _Canvas,
    _attr,
    _num,
)

#: ``TEXT_OVERFLOW:<object>`` — the author's text frame does not hold its text (a
#: whole line lands past the frame's bottom edge): every line is still drawn
#: (PowerPoint does not clip ``a:noAutofit`` text) and the scene degrades so a
#: teacher reviews the slide.
TEXT_OVERFLOW_PREFIX = "TEXT_OVERFLOW:"


def _basename(part: Optional[str]) -> str:
    return part.rsplit("/", 1)[-1] if part else ""


def _first_run_color(runs: list) -> Optional[str]:
    for run in runs:
        color = run.color or {}
        if color.get("value"):
            return str(color["value"])
    return None


def _stop_color(fill: Mapping) -> Mapping:
    """The colour of a gradient's first stop (a gradient is flattened when themed)."""

    stops = fill.get("stops") or []
    return (stops[0].get("color") or {}) if stops else {}


class _ThemedCanvas(_Canvas):
    """Canvas that resolves author paint in the theme palette.

    Everything else — ids, ``<defs>``, the inline-media budget, warnings — is the
    structural canvas, so themed and faithful mode share one tested implementation.
    """

    def __init__(
        self,
        width: float,
        height: float,
        scene: SlideScene,
        media: Mapping[str, bytes],
        config: RenderConfig,
        warnings: list[str],
        theme: MentoraTheme,
    ) -> None:
        super().__init__(width, height, scene, media, config, warnings)
        self.theme = theme

    def paint(self, fill: Optional[dict]) -> str:
        if not fill or fill.get("type") == "none":
            return 'fill="none"'
        kind = fill.get("type")
        if kind == "picture":
            # A picture fill is a photo/texture, not a colour choice: keep it.
            return super().paint(fill)
        colour = (fill.get("color") if kind == "solid" else _stop_color(fill)) or {}
        opacity = colour.get("alpha")
        extra = "" if opacity in (None, 1.0) else f' fill-opacity="{_num(float(opacity))}"'
        # Gradients are the author's styling and are flattened into the theme.
        return f'fill="{_attr(self.theme.map_fill(colour.get("value")))}"{extra}'


class ThemedSvgRenderer(StructuralSvgRenderer):
    """Draws the author's layout in the platform theme (the default render mode)."""

    renderer_id = "mentora-themed-svg"
    renderer_version = "2.0.0"
    engine = "mentora-theme-svg"
    fidelity_ceiling = FIDELITY_THEMED
    degraded_fidelity = FIDELITY_DEGRADED
    #: A chart/SmartArt frame cannot be re-themed without destroying its meaning,
    #: so those kinds stay unsupported and pull the scene into review.
    supported_kinds = ("text", "shape", "picture", "table", "connector", "group")

    def __init__(
        self,
        object_store=None,
        config: Optional[RenderConfig] = None,
        *,
        theme: Optional[MentoraTheme] = None,
    ) -> None:
        super().__init__(object_store=object_store, config=config)
        self.theme = theme or DEFAULT_THEME

    # -- interface --------------------------------------------------------------
    def inspect_support(self) -> CapabilityReport:
        return CapabilityReport(
            supports=True,
            engine=self.engine,
            version=self.renderer_version,
            fidelity_ceiling=self.fidelity_ceiling,
            supported_kinds=self.supported_kinds,
            available_fonts=tuple(sorted(self.theme.available_fonts)),
            reasons=(
                f"themed renderer: the author's layout is kept and re-styled in the "
                f"platform theme '{self.theme.name}' v{self.theme.version}",
                "the theme owns its typefaces, so unavailable source fonts do not "
                "degrade a themed scene",
                "charts and SmartArt cannot be re-themed and require review",
                "native PowerPoint rendering is an OPEN decision (DEC-TECH-005)",
            ),
        )

    def missing_fonts(self, scene: SlideScene) -> tuple[str, ...]:
        """Always empty: the theme owns the typefaces, so the source font is moot."""

        del scene
        return ()

    def identity(self) -> RendererIdentity:
        """Provenance, with the theme folded into the config hash.

        A theme change alters every rendered slide, so it must change the content
        package version. ``RenderConfig`` is theme-agnostic (``base.py``), so the
        theme's canonical form is hashed in here rather than in the shared config.
        """

        base = super().identity()
        payload = json.dumps(
            {"config_hash": base.config_hash, "theme": self.theme.canonical()},
            sort_keys=True,
            separators=(",", ":"),
        )
        return replace(base, config_hash=hashlib.sha256(payload.encode("utf-8")).hexdigest())

    def theme_identity(self) -> dict[str, str]:
        return self.theme.identity()

    # -- per scene --------------------------------------------------------------
    def _attempt_scene(
        self,
        request: RenderRequest,
        scene: SlideScene,
        token: CancelToken,
        budget: RenderBudget,
    ) -> SceneRender:
        """Structural's scene pipeline, with the themed gate on top.

        The layout is structural's, so the fidelity decision is too; what this
        adds is (a) ``fonts_used`` reports the theme's stack, which is what was
        actually drawn, and (b) a frame that cannot hold its text degrades the
        scene.
        """

        result = super()._attempt_scene(request, scene, token, budget)
        if result.status is not RenderStatus.RENDERED:
            return result

        overflow = any(w.startswith(TEXT_OVERFLOW_PREFIX) for w in result.warnings)
        warnings = result.warnings
        if overflow and result.fidelity != FIDELITY_DEGRADED:
            warnings = warnings + ("fidelity degraded; meaning requires review",)
        return replace(
            result,
            fidelity=FIDELITY_DEGRADED if overflow else result.fidelity,
            fonts_used=tuple(sorted(self.fonts())),
            warnings=warnings,
        )

    # -- theming seams ----------------------------------------------------------
    def _make_canvas(
        self,
        width: float,
        height: float,
        scene: SlideScene,
        media: Mapping[str, bytes],
        warnings: list[str],
    ) -> _Canvas:
        return _ThemedCanvas(width, height, scene, media, self.config, warnings, self.theme)

    def _base_background(self, canvas: _Canvas) -> str:
        return (
            f'<rect x="0" y="0" width="{_num(canvas.width)}" height="{_num(canvas.height)}" '
            f'fill="{_attr(self.theme.background)}"/>'
        )

    def _family(self, canvas: _Canvas, family: Optional[str]) -> str:
        """The theme owns the typeface: the author's font name is ignored."""

        del canvas, family
        return self.theme.font_stack

    def _run_color(self, runs: list) -> str:
        return self.theme.map_text(_first_run_color(runs))

    def _run_highlight(self, runs: list) -> Optional[str]:
        for run in runs:
            value = (run.highlight or {}).get("value")
            if value:
                return self.theme.map_highlight(str(value))
        return None

    def _stroke_attrs(self, canvas: _Canvas, line: Optional[dict]) -> str:
        if not line:
            return ""
        color = line.get("color") or {}
        mapped = {**line, "color": {**color, "value": self.theme.map_line(color.get("value"))}}
        return super()._stroke_attrs(canvas, mapped)

    # -- chrome -----------------------------------------------------------------
    def _scene_header(self, canvas: _Canvas) -> list[str]:
        theme = self.theme
        if theme.accent_bar_px <= 0 or not self._strip_is_free(canvas, 0.0, theme.accent_bar_px):
            return []
        return [
            f'<rect x="0" y="0" width="{_num(canvas.width)}" '
            f'height="{_num(theme.accent_bar_px)}" fill="{_attr(theme.primary)}"/>'
        ]

    def _scene_footer(self, canvas: _Canvas) -> list[str]:
        theme = self.theme
        for source_id in canvas.overflowed:
            # The author's frame does not hold this text. We drew it PowerPoint
            # style (no clipping), and the scene is degraded for review below.
            canvas.warnings.append(f"{TEXT_OVERFLOW_PREFIX}{source_id}")
        if theme.footer_px <= 0:
            return []
        background = canvas.scene.background or {}
        if background.get("type") == "picture":
            # A photographic background: the footer would sit on the photo.
            return []
        top = canvas.height - theme.footer_px
        if not self._strip_is_free(canvas, top, theme.footer_px):
            return []
        baseline = top + 26.0
        ink = self._footer_ink(canvas)
        return [
            f'<line x1="{_num(theme.margin_px)}" y1="{_num(top)}" '
            f'x2="{_num(canvas.width - theme.margin_px)}" y2="{_num(top)}" '
            f'stroke="{_attr(theme.border)}"/>',
            f'<text x="{_num(theme.margin_px)}" y="{_num(baseline)}" '
            f'font-family="{_attr(theme.font_stack)}" '
            f'font-size="{_num(theme.footer_pt / PT_PER_PIXEL)}" fill="{_attr(ink)}">'
            f"{escape(theme.footer_label)}</text>",
            f'<text x="{_num(canvas.width - theme.margin_px)}" y="{_num(baseline)}" '
            f'text-anchor="end" font-family="{_attr(theme.font_stack)}" '
            f'font-size="{_num(theme.footer_pt / PT_PER_PIXEL)}" fill="{_attr(ink)}">'
            f"{canvas.scene.order + 1}</text>",
        ]

    def _footer_ink(self, canvas: _Canvas) -> str:
        """Footer colour that stays readable over the slide's base fill."""

        background = canvas.scene.background or {}
        if background.get("type") == "solid":
            value = (background.get("color") or {}).get("value")
            if self.theme.map_fill(value) == self.theme.primary:
                return self.theme.primary_ink
        return self.theme.muted

    def _strip_is_free(self, canvas: _Canvas, top: float, height: float) -> bool:
        """True when no scene object overlaps the horizontal strip.

        This is what keeps the platform's own chrome from painting over an
        author's content: the freeze is computed from the *author's* geometry.
        """

        bottom = top + height
        for obj in canvas.scene.objects:
            if obj.kind == "group":
                continue
            _x, y, _w, h = self._px_bounds(obj, canvas.scene)
            if y < bottom and y + h > top:
                return False
        return True

    # -- themed placeholders ----------------------------------------------------
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
        theme = self.theme
        label = f"{obj.kind}: {obj.name or _basename(obj.media_ref)}"
        body = (
            f'<rect x="{_num(x)}" y="{_num(y)}" width="{_num(w)}" height="{_num(h)}" '
            f'fill="{_attr(theme.surface)}" stroke="{_attr(theme.accent)}" '
            f'stroke-width="1" stroke-dasharray="6 4"/>'
            f'<text x="{_num(x + 8)}" y="{_num(y + 18)}" '
            f'font-family="{_attr(theme.font_stack)}" font-size="12" '
            f'fill="{_attr(theme.muted)}">{escape(label)}</text>'
        )
        return f'<g{transform}>{body}</g>' if transform else body

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
        theme = self.theme
        label = _basename(obj.media_ref) or obj.name or "image"
        body = (
            f'<rect x="{_num(x)}" y="{_num(y)}" width="{_num(w)}" height="{_num(h)}" '
            f'fill="{_attr(theme.surface)}" stroke="{_attr(theme.border)}" '
            f'stroke-width="1" stroke-dasharray="5 4"/>'
            f'<text x="{_num(x + w / 2)}" y="{_num(y + h / 2)}" text-anchor="middle" '
            f'font-family="{_attr(theme.font_stack)}" font-size="12" '
            f'fill="{_attr(theme.muted)}">{escape(label)}</text>'
        )
        return f'<g{transform}>{body}</g>' if transform else body


__all__ = [
    "TEXT_OVERFLOW_PREFIX",
    "ThemedSvgRenderer",
]
