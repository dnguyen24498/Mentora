"""The platform slide theme (V0-019).

The default ``themed`` render mode keeps the author's **layout** and replaces the
author's **styling** (``renderers/themed.py``). Two consequences matter:

* **The font problem disappears.** The theme owns its typefaces, so a deck that
  names ``Be Vietnam Pro`` — or any font this build cannot embed — no longer
  degrades the render. Themed scenes report no missing fonts by construction.
* **Contrast is auditable.** Source colours are mapped *by role*, not copied:
  ``map_text``/``map_fill``/``map_line`` send a light-on-dark pair in the source
  to a light-on-dark pair in the theme, so re-colouring cannot hide text
  (``docs/architecture/18_ACCESSIBILITY_AND_INCLUSION.md``).

The theme is a pure value object: versioned, ``to_dict``-able, and part of the
renderer's config identity, so a theme change is a new content-package version
rather than a silent re-render (``DEC-CONTENT-006``).

The font stack names families the local build declares as available
(``DEFAULT_AVAILABLE_FONTS``). No font file is bundled or licensed here; the
stack falls through to a system sans-serif, which is deliberate and honest.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Optional

#: Typeface stack the theme renders with. These names are declared available by
#: the themed renderer, so using them can never raise a missing-font degradation.
DEFAULT_FONT_STACK = "Noto Sans, DejaVu Sans, Segoe UI, Helvetica, Arial, sans-serif"

#: Families the theme's stack may resolve to on a host that has them.
THEME_FONT_FAMILIES = frozenset(
    {
        "Noto Sans",
        "DejaVu Sans",
        "Segoe UI",
        "Helvetica",
        "Arial",
    }
)

#: Palette-mapping thresholds, in WCAG relative luminance / HSV saturation.
#: They are chosen so the two dominant authoring patterns land on a readable
#: theme pair: near-white surfaces with dark text stay light-on-dark after
#: mapping, and dark surfaces with light text stay dark-on-light.
_LIGHT_FILL = 0.88
_DARK_FILL = 0.28
_LIGHT_TEXT = 0.90
_DARK_TEXT = 0.45
_SATURATED = 0.35


def parse_color(value: Optional[str]) -> Optional[tuple[float, float, float]]:
    """``#rgb``/``#rrggbb`` (optional alpha) -> sRGB components in ``0..1``.

    Returns ``None`` for anything the compiler does not emit as a literal hex
    colour (``none``, ``auto``, a scheme name), which the mappers treat as
    "no author intent" and resolve to a theme default.
    """

    if not isinstance(value, str):
        return None
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(character * 2 for character in text)
    if len(text) not in (6, 8):
        return None
    try:
        channels = [int(text[index : index + 2], 16) / 255.0 for index in range(0, len(text), 2)]
    except ValueError:
        return None
    return channels[0], channels[1], channels[2]


def relative_luminance(rgb: tuple[float, float, float]) -> float:
    """WCAG relative luminance of an sRGB triple (0 = black, 1 = white)."""

    def linear(channel: float) -> float:
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    red, green, blue = (linear(channel) for channel in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def saturation(rgb: tuple[float, float, float]) -> float:
    """HSV saturation: 0 for greys, 1 for a fully saturated hue."""

    highest = max(rgb)
    if highest <= 0.0:
        return 0.0
    return (highest - min(rgb)) / highest


@dataclass(frozen=True)
class MentoraTheme:
    """Palette, typeface stack, and chrome for the platform look."""

    name: str = "mentora-default"
    version: str = "1.1.0"

    # -- palette (sRGB, no alpha: the theme paints flat, opaque surfaces) ------
    background: str = "#FFFFFF"
    surface: str = "#F4F7FB"
    surface_alt: str = "#E9EFF8"
    ink: str = "#0F172A"
    muted: str = "#5B6B84"
    primary: str = "#1B3A8C"
    primary_ink: str = "#FFFFFF"
    accent: str = "#0A6EBD"
    border: str = "#DCE4EE"
    #: Tint painted behind source-highlighted runs (teacher emphasis survives,
    #: restyled).
    highlight: str = "#FCEFC7"

    # -- typography ------------------------------------------------------------
    #: The theme's typefaces. Text *sizes* are the author's: themed mode keeps the
    #: source layout, so the author's hierarchy — and its fit — is preserved.
    font_stack: str = DEFAULT_FONT_STACK
    footer_pt: float = 11.0

    # -- grid and chrome -------------------------------------------------------
    margin_px: float = 72.0
    #: Radius applied to image and placeholder frames.
    radius_px: float = 12.0
    #: Full-bleed accent band at the top of a slide, when that strip is free.
    accent_bar_px: float = 8.0
    #: Height of the bottom strip the footer is drawn in, when that strip is free.
    footer_px: float = 56.0

    #: Text painted on the footer's left; the slide number is painted right.
    footer_label: str = "Mentora"

    #: Families this theme can resolve to (reported by ``inspect_support``).
    available_fonts: frozenset[str] = field(default_factory=lambda: THEME_FONT_FAMILIES)

    # -- palette mapping -------------------------------------------------------
    #: Map an author's shape fill onto the theme's surfaces. ``None``/``none``
    #: stays "no fill"; the mappers never invent a fill where there was none.
    def map_fill(self, value: Optional[str]) -> str:
        rgb = parse_color(value)
        if rgb is None:
            return self.surface_alt
        luminance = relative_luminance(rgb)
        if luminance >= _LIGHT_FILL:
            return self.surface
        if luminance <= _DARK_FILL:
            return self.primary
        if saturation(rgb) >= _SATURATED:
            return self.accent
        return self.surface_alt

    def map_text(self, value: Optional[str]) -> str:
        """Map an author's text colour, preserving its polarity.

        Near-white text means "text that sits on a dark band" and becomes
        ``primary_ink``; near-black text becomes ``ink``; anything greyish
        becomes ``muted`` rather than a pale colour that could vanish on a light
        surface.
        """

        rgb = parse_color(value)
        if rgb is None:
            return self.ink
        luminance = relative_luminance(rgb)
        if luminance >= _LIGHT_TEXT:
            return self.primary_ink
        if luminance <= _DARK_TEXT:
            return self.ink
        if saturation(rgb) >= _SATURATED:
            return self.primary
        return self.muted

    def map_line(self, value: Optional[str]) -> str:
        """Map an author's stroke/outline colour onto the theme's lines."""

        rgb = parse_color(value)
        if rgb is None:
            return self.border
        luminance = relative_luminance(rgb)
        if luminance >= _LIGHT_FILL:
            return self.border
        if luminance <= 0.35:
            return self.primary
        if saturation(rgb) >= _SATURATED:
            return self.accent
        return self.muted

    def map_highlight(self, value: Optional[str]) -> str:
        """Re-tint a source text highlight; the theme owns the tint."""

        del value
        return self.highlight

    def canonical(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "background": self.background,
            "surface": self.surface,
            "surface_alt": self.surface_alt,
            "ink": self.ink,
            "muted": self.muted,
            "primary": self.primary,
            "primary_ink": self.primary_ink,
            "accent": self.accent,
            "border": self.border,
            "highlight": self.highlight,
            "font_stack": self.font_stack,
            "footer_pt": self.footer_pt,
            "margin_px": self.margin_px,
            "radius_px": self.radius_px,
            "accent_bar_px": self.accent_bar_px,
            "footer_px": self.footer_px,
            "footer_label": self.footer_label,
            "available_fonts": sorted(self.available_fonts),
        }

    def to_dict(self) -> dict[str, Any]:
        return self.canonical()

    def identity(self) -> dict[str, str]:
        return {"name": self.name, "version": self.version}

    def with_version(self, version: str) -> "MentoraTheme":
        return replace(self, version=version)


#: The shipped default theme. A theme change must bump ``version`` so the
#: content-package cache key changes with it.
DEFAULT_THEME = MentoraTheme()

__all__ = [
    "DEFAULT_FONT_STACK",
    "DEFAULT_THEME",
    "MentoraTheme",
    "THEME_FONT_FAMILIES",
    "parse_color",
    "relative_luminance",
    "saturation",
]
