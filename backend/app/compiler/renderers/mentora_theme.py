"""The platform slide theme (V0-019).

A *theme* here is deliberately small: a palette, a typeface stack, a type scale,
and a spacing grid. It has no geometry and no per-deck state. The themed renderer
(``renderers/themed.py``) feeds the extracted **content** into the flow layout
(``renderers/flow.py``), which uses this theme to decide sizes, spacing, and
chrome — never to copy the author's choices.

Two consequences are load-bearing:

* **The font problem disappears.** The theme owns its typefaces, so a deck that
  names ``Be Vietnam Pro`` — or any font this build cannot embed — no longer
  degrades the render. Themed scenes report no missing fonts by construction.
* **Contrast is a property of the theme, not of the deck.** Every visible
  surface is white and every text role is one of four opaque inks from this
  palette, so readable contrast is auditable once, here, instead of depending on
  whatever an author painted (``docs/architecture/18_ACCESSIBILITY_AND_INCLUSION.md``).

The theme is a pure value object: versioned, ``to_dict``-able, and folded into the
renderer's config identity, so a theme change is a new content-package version
rather than a silent re-render (``DEC-CONTENT-006``).

All sizes are in CSS pixels on the render canvas (1280x720); the flow scales them
by a single factor when a slide is dense. The font stack names families the local
build declares as available (``THEME_FONT_FAMILIES``). No font file is
bundled or licensed here; the stack falls through to a system sans-serif, which
is deliberate and honest (the renderer technology is still OPEN, ``DEC-TECH-005``).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

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


@dataclass(frozen=True)
class MentoraTheme:
    """Palette, typeface stack, type scale, and grid for the platform look."""

    name: str = "mentora-default"
    version: str = "3.0.0"

    # -- palette (sRGB; the theme paints flat, opaque surfaces) ----------------
    background: str = "#FFFFFF"
    #: Fill of a banded table row, and of an undrawable-content panel.
    surface: str = "#F4F7FB"
    #: Fill of a table's header row.
    surface_alt: str = "#E9EFF8"
    ink: str = "#0F172A"
    muted: str = "#5B6B84"
    #: Brand anchor: the title's ink and any future chrome.
    primary: str = "#1B3A8C"
    accent: str = "#0A6EBD"
    border: str = "#DCE4EE"

    # -- typography -------------------------------------------------------------
    #: The theme's typefaces (drawn literally; never a source typeface).
    font_stack: str = DEFAULT_FONT_STACK
    title_px: float = 34.0
    kicker_px: float = 13.5
    subtitle_px: float = 20.0
    body_px: float = 19.0
    #: The three body rows. A source block is assigned a row (``lead``/``body``/
    #: ``caption``); the theme owns the sizes, so the type scale stays consistent
    #: from slide to slide while the source's own hierarchy still reads.
    body_scale: float = 1.0
    lead_scale: float = 1.35
    caption_scale: float = 0.76
    table_px: float = 15.0
    footer_px: float = 13.0
    #: Label inside the panel drawn for content the platform cannot redraw.
    panel_label_px: float = 13.0
    #: Line box height as a multiple of the font size.
    line_spacing: float = 1.32

    # -- grid -------------------------------------------------------------------
    #: Page margin (left, right, and top).
    margin_px: float = 56.0
    #: Reserved strip below the body. Only the page number is drawn in it, and the
    #: flow is never allowed to place content there.
    bottom_zone_px: float = 92.0
    #: Page-number baseline, measured up from the bottom edge.
    footer_from_bottom_px: float = 46.0
    #: Gap between the heading block and the first body block.
    header_gap_px: float = 18.0
    #: Gap between two heading lines (kicker/title/subtitle).
    heading_gap_px: float = 8.0
    #: Gap between the heading block and its hairline rule.
    rule_gap_px: float = 11.0
    #: Gap between two body blocks.
    item_gap_px: float = 14.0
    #: Gap between two paragraphs of the same text block.
    paragraph_gap_px: float = 6.0
    #: Indent step for one list level (the bullet glyph sits in this step).
    list_indent_px: float = 26.0
    table_pad_x_px: float = 10.0
    table_pad_y_px: float = 7.0
    picture_gap_px: float = 12.0
    #: Share of the body height a picture row may take when the slide mixes text
    #: and pictures. A picture-only slide may use the whole body instead.
    picture_budget: float = 0.55
    max_pictures_per_row: int = 4
    #: Height of the panel drawn for content the platform cannot redraw.
    panel_px: float = 150.0
    #: Absolute floor for the type scale; content past it overflows for review.
    min_scale: float = 0.45

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
            "accent": self.accent,
            "border": self.border,
            "font_stack": self.font_stack,
            "title_px": self.title_px,
            "kicker_px": self.kicker_px,
            "subtitle_px": self.subtitle_px,
            "body_px": self.body_px,
            "body_scale": self.body_scale,
            "lead_scale": self.lead_scale,
            "caption_scale": self.caption_scale,
            "table_px": self.table_px,
            "footer_px": self.footer_px,
            "panel_label_px": self.panel_label_px,
            "line_spacing": self.line_spacing,
            "margin_px": self.margin_px,
            "bottom_zone_px": self.bottom_zone_px,
            "footer_from_bottom_px": self.footer_from_bottom_px,
            "header_gap_px": self.header_gap_px,
            "heading_gap_px": self.heading_gap_px,
            "rule_gap_px": self.rule_gap_px,
            "item_gap_px": self.item_gap_px,
            "paragraph_gap_px": self.paragraph_gap_px,
            "list_indent_px": self.list_indent_px,
            "table_pad_x_px": self.table_pad_x_px,
            "table_pad_y_px": self.table_pad_y_px,
            "picture_gap_px": self.picture_gap_px,
            "picture_budget": self.picture_budget,
            "max_pictures_per_row": self.max_pictures_per_row,
            "panel_px": self.panel_px,
            "min_scale": self.min_scale,
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
]
