"""The platform slide theme (V0-019).

A slide in *themed* mode is a **re-authoring** of the extracted content in a
theme the platform controls, not a reproduction of the source deck's own
geometry (``renderers/themed.py``). Two consequences matter:

* **The font problem disappears.** The theme owns its typefaces, so a deck that
  names ``Be Vietnam Pro`` — or any font this build cannot embed — no longer
  degrades the render. Themed scenes report no missing fonts by construction.
* **Accessibility is auditable.** Palette contrast and the type scale are ours
  (``docs/architecture/18_ACCESSIBILITY_AND_INCLUSION.md``), so contrast does not
  depend on an arbitrary author's colour choices.

The theme is a pure value object: versioned, ``to_dict``-able, and part of the
renderer's config identity, so a theme change is a new content-package version
rather than a silent re-render (``DEC-CONTENT-006``).

The font stacks name families the local build declares as available
(``DEFAULT_AVAILABLE_FONTS``). No font file is bundled or licensed here; the
stack falls through to a system sans-serif, which is deliberate and honest.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

#: Typeface stack the theme renders with. These names are declared available by
#: the themed renderer, so using them can never raise a missing-font degradation.
DEFAULT_FONT_STACK = "Noto Sans, DejaVu Sans, Segoe UI, Helvetica, Arial, sans-serif"
DEFAULT_HEADING_STACK = "Noto Sans, DejaVu Sans, Segoe UI, Helvetica, Arial, sans-serif"
DEFAULT_MONO_STACK = "DejaVu Sans Mono, Courier New, monospace"

#: Families the theme's stacks may resolve to on a host that has them.
THEME_FONT_FAMILIES = frozenset(
    {
        "Noto Sans",
        "DejaVu Sans",
        "DejaVu Sans Mono",
        "Segoe UI",
        "Helvetica",
        "Arial",
        "Courier New",
    }
)


@dataclass(frozen=True)
class MentoraTheme:
    """Palette, type scale, and grid for the platform look."""

    name: str = "mentora-default"
    version: str = "1.0.0"

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

    # -- type scale (points, resolved at the renderer's 96 dpi canvas) ---------
    font_stack: str = DEFAULT_FONT_STACK
    heading_stack: str = DEFAULT_HEADING_STACK
    title_pt: float = 36.0
    heading_pt: float = 24.0
    body_pt: float = 18.0
    caption_pt: float = 13.0
    footer_pt: float = 11.0

    # -- grid -----------------------------------------------------------------
    margin_px: float = 72.0
    gutter_px: float = 28.0
    #: Radius applied to cards, images, and table headers.
    radius_px: float = 12.0
    #: Full-bleed accent band at the top of every slide.
    accent_bar_px: float = 8.0
    #: Floor for content auto-shrink; below this the scene reports overflow
    #: rather than shrinking text into illegibility.
    min_scale: float = 0.72

    #: Text painted on the footer's left; the slide number is painted right.
    footer_label: str = "Mentora"

    #: Families this theme can resolve to (reported by ``inspect_support``).
    available_fonts: frozenset[str] = field(default_factory=lambda: THEME_FONT_FAMILIES)

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
            "font_stack": self.font_stack,
            "heading_stack": self.heading_stack,
            "title_pt": self.title_pt,
            "heading_pt": self.heading_pt,
            "body_pt": self.body_pt,
            "caption_pt": self.caption_pt,
            "footer_pt": self.footer_pt,
            "margin_px": self.margin_px,
            "gutter_px": self.gutter_px,
            "radius_px": self.radius_px,
            "accent_bar_px": self.accent_bar_px,
            "min_scale": self.min_scale,
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
    "DEFAULT_HEADING_STACK",
    "DEFAULT_MONO_STACK",
    "DEFAULT_THEME",
    "MentoraTheme",
    "THEME_FONT_FAMILIES",
]
