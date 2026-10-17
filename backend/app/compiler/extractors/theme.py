"""Theme, colour, and fill/line resolution for OOXML (V0-018).

PresentationML keeps almost all *look* information outside the slide: the colour
scheme and fonts live in ``ppt/theme/theme1.xml``, the colour mapping and the
text style cascade live in the slide master, and individual shapes only carry
overrides. This module turns that into resolved sRGB colours and concrete
fill/line descriptions the renderer can draw.

Everything here is best-effort and side-effect free: an unknown colour form or an
unmodelled modifier returns ``None`` (unresolved) rather than raising, so one
exotic element can never drop a slide.

References: ECMA-376 Part 1, §20.1.2.3 (colours), §20.1.4.1.11 (fills),
§20.1.10.13 (theme).
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
import xml.etree.ElementTree as ET

from app.compiler.extractors.ooxml import A, child, children, fraction_attr, int_attr

#: ``p:clrMap`` defaults from the spec (also what Office writes) — the format
#: scheme names on the left resolve through the theme's ``clrScheme`` on the right.
DEFAULT_CLR_MAP: dict[str, str] = {
    "bg1": "lt1",
    "tx1": "dk1",
    "bg2": "lt2",
    "tx2": "dk2",
    "accent1": "accent1",
    "accent2": "accent2",
    "accent3": "accent3",
    "accent4": "accent4",
    "accent5": "accent5",
    "accent6": "accent6",
    "hlink": "hlink",
    "folHlink": "folHlink",
    "dk1": "dk1",
    "lt1": "lt1",
    "dk2": "dk2",
    "lt2": "lt2",
}

#: A pragmatic subset of the 140 preset colours; uncommon names stay unresolved
#: rather than being guessed wrong.
_PRESET_COLORS: dict[str, str] = {
    "black": "000000", "white": "FFFFFF", "red": "FF0000", "green": "00FF00",
    "blue": "0000FF", "yellow": "FFFF00", "cyan": "00FFFF", "magenta": "FF00FF",
    "gray": "808080", "grey": "808080", "silver": "C0C0C0", "maroon": "800000",
    "olive": "808000", "navy": "000080", "purple": "800080", "teal": "008080",
    "lime": "00FF00", "aqua": "00FFFF", "fuchsia": "FF00FF", "orange": "FFA500",
    "brown": "A52A2A", "pink": "FFC0CB", "gold": "FFD700", "darkRed": "8B0000",
    "darkBlue": "00008B", "darkGreen": "006400", "darkGray": "A9A9A9",
    "lightGray": "D3D3D3", "lightGrey": "D3D3D3", "lightBlue": "ADD8E6",
    "lightGreen": "90EE90", "lightYellow": "FFFFE0", "skyBlue": "87CEEB",
    "steelBlue": "4682B4", "royalBlue": "4169E1", "indigo": "4B0082",
    "violet": "EE82EE", "crimson": "DC143C", "salmon": "FA8072",
    "coral": "FF7F50", "tomato": "FF6347", "turquoise": "40E0D0",
    "darkCyan": "008B8B", "darkMagenta": "8B008B", "darkOrange": "FF8C00",
    "darkViolet": "9400D3", "slateGray": "708090", "dimGray": "696969",
    "khaki": "F0E68C", "plum": "DDA0DD", "orchid": "DA70D6", "beige": "F5F5DC",
    "ivory": "FFFFF0", "seashell": "FFF5EE", "wheat": "F5DEB3", "tan": "D2B48C",
    "chocolate": "D2691E", "peru": "CD853F", "sienna": "A0522D", "snow": "FFFAFA",
}


def _hex(value: str) -> Optional[str]:
    value = value.strip().lstrip("#")
    if len(value) == 6:
        try:
            int(value, 16)
        except ValueError:
            return None
        return value.upper()
    return None


def _clamp(value: float, low: float = 0.0, high: float = 255.0) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class Theme:
    """Resolved colour scheme + font scheme of one theme part."""

    colors: dict[str, str] = field(default_factory=dict)
    clr_map: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_CLR_MAP))
    major_font: Optional[str] = None
    minor_font: Optional[str] = None

    def resolve_scheme(self, name: str) -> Optional[str]:
        mapped = self.clr_map.get(name, name)
        return self.colors.get(mapped) or self.colors.get(name)

    def resolve_font_ref(self, ref: Optional[str]) -> Optional[str]:
        """Resolve a theme font token (``+mj-lt``/``+mn-lt``) or pass a family through."""

        if not ref:
            return None
        if ref == "+mj-lt":
            return self.major_font
        if ref == "+mn-lt":
            return self.minor_font
        if ref.startswith("+"):
            # +mj-ea / +mn-cs etc.: a theme slot we do not model.
            return None
        return ref


def parse_theme(root: Optional[ET.Element]) -> Theme:
    """Parse ``ppt/theme/themeN.xml`` (empty :class:`Theme` when unreadable)."""

    if root is None:
        return Theme()
    scheme = child(child(root, A, "themeElements"), A, "clrScheme")
    colors: dict[str, str] = {}
    for entry in list(scheme) if scheme is not None else []:
        name = entry.tag.rsplit("}", 1)[-1]
        # A ``a:clrScheme`` child is a *slot* (``<a:accent1>``) wrapping the real
        # colour element (``<a:srgbClr>``/``<a:sysClr>``), so the value sits one
        # level down — reading ``entry`` itself would yield nothing at all.
        value = _slot_base_hex(entry)
        if value:
            colors[name] = value
    fonts = child(child(root, A, "themeElements"), A, "fontScheme")
    major = _font_latin(child(fonts, A, "majorFont"))
    minor = _font_latin(child(fonts, A, "minorFont"))
    return Theme(colors=colors, major_font=major, minor_font=minor)


def _font_latin(font_el: Optional[ET.Element]) -> Optional[str]:
    latin = child(font_el, A, "latin")
    typeface = latin.get("typeface") if latin is not None else None
    return typeface or None


def _slot_base_hex(slot: ET.Element) -> Optional[str]:
    """Base sRGB value of a colour *slot* (``<a:accent1>``) or colour element."""

    local = slot.tag.rsplit("}", 1)[-1]
    elements = [slot] if local.endswith("Clr") else [
        entry for entry in list(slot) if entry.tag.rsplit("}", 1)[-1].endswith("Clr")
    ]
    for element in elements:
        value = _base_hex(element, Theme())
        if value:
            return value
    return None


def parse_clr_map(master_root: Optional[ET.Element]) -> dict[str, str]:
    """``p:clrMap`` on the slide master, falling back to the spec default."""

    mapping = dict(DEFAULT_CLR_MAP)
    if master_root is None:
        return mapping
    # ``p:clrMap`` is a direct child of ``p:sldMaster``; search shallowly so a
    # nested look-alike can never be picked up by accident.
    for node in list(master_root):
        if node.tag.rsplit("}", 1)[-1] != "clrMap":
            continue
        for name in list(mapping):
            value = node.get(name)
            if value:
                mapping[name] = value
        break
    return mapping


def _base_hex(el: ET.Element, theme: Theme) -> Optional[str]:
    """Base sRGB value of a colour element, before modifiers."""

    local = el.tag.rsplit("}", 1)[-1]
    if local == "srgbClr":
        return _hex(el.get("val", ""))
    if local == "schemeClr":
        return _hex(theme.resolve_scheme(el.get("val", "")) or "")
    if local == "sysClr":
        return _hex(el.get("lastClr", "") or "")
    if local == "prstClr":
        return _hex(_PRESET_COLORS.get(el.get("val", ""), ""))
    if local == "scrgbClr":
        parts = [int_attr(el, name) for name in ("r", "g", "b")]
        if any(part is None for part in parts):
            return None
        return "".join(f"{round(_clamp((part or 0) / 100000 * 255)):02X}" for part in parts)
    if local == "hslClr":
        hue = int_attr(el, "hue") or 0
        sat = int_attr(el, "sat") or 0
        lum = int_attr(el, "lum") or 0
        red, green, blue = colorsys.hls_to_rgb(hue / 60000 / 360, lum / 100000, sat / 100000)
        return "".join(f"{round(_clamp(c * 255)):02X}" for c in (red, green, blue))
    return None


#: Modifiers applied to the *colour element's* children, in document order.
def resolve_color(el: Optional[ET.Element], theme: Theme) -> Optional[dict[str, Any]]:
    """Resolve an ``a:*Clr`` element to ``{"value": "#RRGGBB", "alpha": f}``."""

    if el is None:
        return None
    base = _base_hex(el, theme)
    if base is None:
        return None
    rgb = [int(base[i : i + 2], 16) for i in (0, 2, 4)]
    alpha = 1.0
    for mod in list(el):
        local = mod.tag.rsplit("}", 1)[-1]
        frac = fraction_attr(mod, "val")
        if local == "alpha" and frac is not None:
            alpha = frac
        elif local == "alphaMod" and frac is not None:
            alpha *= frac
        elif local == "alphaOff" and frac is not None:
            alpha += frac
        elif local in ("lumMod", "lumOff") and frac is not None:
            hue, lum, sat = colorsys.rgb_to_hls(*[c / 255 for c in rgb])
            lum = lum * frac if local == "lumMod" else lum + frac
            rgb = [c * 255 for c in colorsys.hls_to_rgb(hue, max(0.0, min(1.0, lum)), sat)]
        elif local == "satMod" and frac is not None:
            hue, lum, sat = colorsys.rgb_to_hls(*[c / 255 for c in rgb])
            rgb = [c * 255 for c in colorsys.hls_to_rgb(hue, lum, max(0.0, min(1.0, sat * frac)))]
        elif local == "tint" and frac is not None:
            rgb = [c + (255 - c) * (1 - frac) for c in rgb]
        elif local == "shade" and frac is not None:
            rgb = [c * frac for c in rgb]
    value = "".join(f"{round(_clamp(c)):02X}" for c in rgb)
    return {"value": f"#{value}", "alpha": round(max(0.0, min(1.0, alpha)), 4)}


def first_color(container: Optional[ET.Element], theme: Theme) -> Optional[dict[str, Any]]:
    """Resolve the first colour child of ``container``.

    ``container`` is typically an ``a:solidFill``, ``a:lnRef`` or ``a:fillRef``.
    """

    if container is None:
        return None
    for entry in list(container):
        if entry.tag.rsplit("}", 1)[-1].endswith("Clr"):
            return resolve_color(entry, theme)
    return None


def paint_color(container: Optional[ET.Element], theme: Theme) -> Optional[dict[str, Any]]:
    # ``a:ln`` is why this exists: its colour sits inside ``a:solidFill``, not
    # directly under the line, so ``first_color`` alone would report "no colour"
    # and silently drop every stroke in the deck.
    direct = first_color(container, theme)
    if direct is not None:
        return direct
    for tag in ("solidFill", "gradFill", "pattFill"):
        nested = child(container, A, tag)
        if nested is not None:
            resolved = first_color(nested, theme)
            if resolved is not None:
                return resolved
    return None


# -- fills / lines ------------------------------------------------------------------
def _gradient(fill_el: ET.Element, theme: Theme) -> Optional[dict[str, Any]]:
    stops: list[dict[str, Any]] = []
    gs_list = child(fill_el, A, "gsLst")
    for stop in children(gs_list, A, "gs"):
        position = fraction_attr(stop, "pos")
        color = first_color(stop, theme)
        if position is None or color is None:
            continue
        stops.append({"position": round(position, 4), "color": color})
    if not stops:
        return None
    linear = child(fill_el, A, "lin")
    angle = 0.0
    if linear is not None:
        raw = int_attr(linear, "ang")
        # DrawingML angle: 60000ths of a degree, clockwise from the 3 o'clock
        # axis; SVG linearGradient uses the same convention for x1/y1->x2/y2.
        angle = (raw / 60000) % 360 if raw is not None else 0.0
    elif child(fill_el, A, "path") is not None:
        angle = 90.0
    return {"type": "gradient", "angle": round(angle, 2), "stops": stops}


def fill_from(
    sp_pr: Optional[ET.Element],
    theme: Theme,
    *,
    resolve_media: Optional[Callable[[str], Optional[tuple[str, Optional[str]]]]] = None,
    style_el: Optional[ET.Element] = None,
) -> Optional[dict[str, Any]]:
    """Resolved fill of a shape's ``a:spPr`` (explicit fill, then ``p:style``).

    ``resolve_media(rel_id) -> (part, mime)`` lets a picture fill (``a:blipFill``)
    become a real image; without it a picture fill degrades to "none".
    """

    fill_el = None
    if sp_pr is not None:
        for local in ("noFill", "solidFill", "gradFill", "blipFill", "pattFill", "grpFill"):
            found = child(sp_pr, A, local)
            if found is not None:
                fill_el = found
                break
    if fill_el is not None:
        return _fill_from_element(fill_el, theme, resolve_media)
    return _fill_from_style(style_el, theme)


def _fill_from_element(
    fill_el: ET.Element,
    theme: Theme,
    resolve_media: Optional[Callable[[str], Optional[tuple[str, Optional[str]]]]],
) -> Optional[dict[str, Any]]:
    local = fill_el.tag.rsplit("}", 1)[-1]
    if local == "noFill":
        return {"type": "none"}
    if local == "solidFill":
        return {"type": "solid", "color": first_color(fill_el, theme)}
    if local == "gradFill":
        gradient = _gradient(fill_el, theme)
        return gradient or {"type": "solid", "color": first_color(fill_el, theme)}
    if local == "blipFill":
        blip = child(fill_el, A, "blip")
        rel_id = None
        if blip is not None:
            rel_id = blip.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
        resolved = resolve_media(rel_id) if (rel_id and resolve_media) else None
        if not resolved:
            return {"type": "none"}
        part, mime = resolved
        return {"type": "picture", "media_ref": part, "media_type": mime}
    if local == "pattFill":
        # Patterns are approximated by their foreground colour; the pattern
        # itself is not reproduced.
        return {"type": "solid", "color": first_color(fill_el, theme)}
    if local == "grpFill":
        return None
    return None


def _fill_from_style(style_el: Optional[ET.Element], theme: Theme) -> Optional[dict[str, Any]]:
    """``p:style/a:fillRef``: idx=0 means "no fill", otherwise a solid accent fill."""

    if style_el is None:
        return None
    ref = child(style_el, A, "fillRef")
    if ref is None:
        return None
    if (int_attr(ref, "idx") or 0) == 0:
        return {"type": "none"}
    return {"type": "solid", "color": first_color(ref, theme)}


def line_from(
    sp_pr: Optional[ET.Element],
    theme: Theme,
    *,
    style_el: Optional[ET.Element] = None,
) -> Optional[dict[str, Any]]:
    """Resolved outline of a shape (``a:ln``), or ``None`` when it has none."""

    ln = child(sp_pr, A, "ln") if sp_pr is not None else None
    if ln is not None:
        if child(ln, A, "noFill") is not None:
            return None
        color = paint_color(ln, theme)
        if color is None:
            # ``<a:ln/>`` (or a line with only a width) means "take the theme
            # line style", which would need the theme's line-style list to
            # resolve. Reporting no line is honest; inventing an outline would
            # put strokes on shapes the original has none on.
            return None
        width = int_attr(ln, "w") or 12700
        dash_el = child(ln, A, "prstDash")
        dash = dash_el.get("val") if dash_el is not None else None
        return {"color": color, "width_emu": width, "dash": dash or "solid"}
    if style_el is not None:
        ref = child(style_el, A, "lnRef")
        if ref is not None and (int_attr(ref, "idx") or 0) != 0:
            color = first_color(ref, theme)
            # A style reference without a resolvable "style colour" would need
            # the theme's line-style list to draw; report no line instead of
            # inventing one.
            if color is not None:
                return {"color": color, "width_emu": 12700, "dash": "solid"}
    return None


def geometry_from(sp_pr: Optional[ET.Element]) -> Optional[str]:
    """Preset geometry name (``a:prstGeom/@prst``); ``custGeom`` -> "custGeom"."""

    geom = child(sp_pr, A, "prstGeom")
    if geom is not None:
        preset = geom.get("prst")
        return preset or None
    if child(sp_pr, A, "custGeom") is not None:
        return "custGeom"
    return None
