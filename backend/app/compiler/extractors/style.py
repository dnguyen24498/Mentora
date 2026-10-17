"""Text/layout formatting resolution for OOXML (V0-018).

PowerPoint stores formatting across four levels — slide shape, slide layout
placeholder, slide master placeholder, and the master's ``p:txStyles`` — each
only overriding what it needs. This module parses each level into small immutable
formats and merges them, so the IR ends up with *effective* values a renderer can
use directly (a title really is 40 pt and centred, without the renderer knowing
anything about inheritance).

Missing/unmodelled attributes stay ``None`` (= "not specified here"), which is
what makes the merge order meaningful.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Optional
import xml.etree.ElementTree as ET

from app.compiler.extractors.ooxml import (
    A,
    P,
    bool_attr,
    child,
    children,
    fraction_attr,
    int_attr,
)
from app.compiler.extractors.theme import Theme, fill_from, first_color, line_from
from app.compiler.models.ir import Bounds

#: Placeholder types that take their text style from the master's title style.
TITLE_PLACEHOLDERS = frozenset({"title", "ctrTitle"})
#: ...; the rest of the text-bearing placeholders take the body style.
BODY_PLACEHOLDERS = frozenset(
    {"body", "subTitle", "obj", "dt", "ftr", "sldNum", "chart", "tbl", "dgm", "clipArt", "media"}
)

#: ``a:bodyPr`` spec defaults (EMU) used when an inset attribute is absent.
DEFAULT_INSETS = {"left": 91440, "top": 45720, "right": 91440, "bottom": 45720}

#: 1/60000 degree -> degree.
ROTATION_SCALE = 60000.0


@dataclass(frozen=True)
class RunFormat:
    font: Optional[str] = None
    size_pt: Optional[float] = None
    bold: Optional[bool] = None
    italic: Optional[bool] = None
    underline: Optional[bool] = None
    color: Optional[dict[str, Any]] = None
    highlight: Optional[dict[str, Any]] = None


@dataclass(frozen=True)
class ParaFormat:
    align: Optional[str] = None
    bullet: Optional[dict[str, Any]] = None
    margin_left_emu: Optional[int] = None
    indent_emu: Optional[int] = None
    space_before_pt: Optional[float] = None
    space_after_pt: Optional[float] = None
    line_spacing: Optional[float] = None
    line_spacing_pt: Optional[float] = None


@dataclass(frozen=True)
class BodyFormat:
    anchor: Optional[str] = None
    insets: Optional[dict[str, int]] = None
    autofit: Optional[str] = None
    font_scale: Optional[float] = None


@dataclass(frozen=True)
class LevelFormat:
    """Per-outline-level paragraph and run defaults (9 levels, 0-based)."""

    para: ParaFormat = field(default_factory=ParaFormat)
    run: RunFormat = field(default_factory=RunFormat)


# -- merging ---------------------------------------------------------------------
def _merge(base: Optional[dict], over: Optional[dict], keys: Iterable[str]) -> Optional[dict]:
    if base is None and over is None:
        return None
    merged = dict(base or {})
    for key in keys:
        value = (over or {}).get(key)
        if value is not None:
            merged[key] = value
    return merged


def merge_run(base: RunFormat, over: RunFormat) -> RunFormat:
    return replace(
        base,
        font=over.font or base.font,
        size_pt=over.size_pt if over.size_pt is not None else base.size_pt,
        bold=over.bold if over.bold is not None else base.bold,
        italic=over.italic if over.italic is not None else base.italic,
        underline=over.underline if over.underline is not None else base.underline,
        color=over.color or base.color,
        highlight=over.highlight or base.highlight,
    )


def merge_para(base: ParaFormat, over: ParaFormat) -> ParaFormat:
    return replace(
        base,
        align=over.align or base.align,
        bullet=over.bullet if over.bullet is not None else base.bullet,
        margin_left_emu=(
            over.margin_left_emu if over.margin_left_emu is not None else base.margin_left_emu
        ),
        indent_emu=over.indent_emu if over.indent_emu is not None else base.indent_emu,
        space_before_pt=(
            over.space_before_pt if over.space_before_pt is not None else base.space_before_pt
        ),
        space_after_pt=(
            over.space_after_pt if over.space_after_pt is not None else base.space_after_pt
        ),
        line_spacing=(
            over.line_spacing if over.line_spacing is not None else base.line_spacing
        ),
        line_spacing_pt=(
            over.line_spacing_pt if over.line_spacing_pt is not None else base.line_spacing_pt
        ),
    )


def merge_body(base: BodyFormat, over: BodyFormat) -> BodyFormat:
    return replace(
        base,
        anchor=over.anchor or base.anchor,
        insets=over.insets or base.insets,
        autofit=over.autofit or base.autofit,
        font_scale=over.font_scale if over.font_scale is not None else base.font_scale,
    )


def merge_levels(base: list[LevelFormat], over: list[LevelFormat]) -> list[LevelFormat]:
    """Element-wise merge: ``over`` wins per level, per field."""

    merged: list[LevelFormat] = []
    for index in range(9):
        parent = base[index] if index < len(base) else LevelFormat()
        child_format = over[index] if index < len(over) else LevelFormat()
        merged.append(
            LevelFormat(
                para=merge_para(parent.para, child_format.para),
                run=merge_run(parent.run, child_format.run),
            )
        )
    return merged


def empty_levels() -> list[LevelFormat]:
    return [LevelFormat() for _ in range(9)]


# -- parsing ---------------------------------------------------------------------
def run_format(rpr: Optional[ET.Element], theme: Theme) -> RunFormat:
    if rpr is None:
        return RunFormat()
    size = int_attr(rpr, "sz")
    underline: Optional[bool]
    raw_underline = rpr.get("u")
    if raw_underline is None:
        underline = None
    else:
        underline = raw_underline not in ("none", "0", "false")
    return RunFormat(
        font=_typeface(rpr, theme),
        size_pt=size / 100 if size is not None else None,
        bold=bool_attr(rpr, "b"),
        italic=bool_attr(rpr, "i"),
        underline=underline,
        color=first_color(child(rpr, A, "solidFill"), theme),
        highlight=first_color(child(rpr, A, "highlight"), theme),
    )


def _typeface(rpr: Optional[ET.Element], theme: Theme) -> Optional[str]:
    """Effective typeface (latin, else east-asian, else complex script)."""

    if rpr is None:
        return None
    for tag in ("latin", "ea", "cs"):
        node = child(rpr, A, tag)
        if node is None:
            continue
        resolved = theme.resolve_font_ref(node.get("typeface"))
        if resolved:
            return resolved
    return None


def para_format(ppr: Optional[ET.Element], theme: Theme) -> ParaFormat:
    del theme  # paragraph formatting carries no colour in this model
    if ppr is None:
        return ParaFormat()
    bullet: Optional[dict[str, Any]]
    if child(ppr, A, "buNone") is not None:
        bullet = {"none": True}
    elif child(ppr, A, "buChar") is not None:
        bullet = {"char": child(ppr, A, "buChar").get("char") or "•"}
    elif child(ppr, A, "buAutoNum") is not None:
        bullet = {"autonum": child(ppr, A, "buAutoNum").get("type") or "arabicPeriod"}
    else:
        bullet = None

    line_spacing: Optional[float] = None
    line_spacing_pt: Optional[float] = None
    ln_spc = child(ppr, A, "lnSpc")
    if ln_spc is not None:
        # ``spcPct/@val`` is 1/1000 of a percent (100000 == 100% == 1.0 spacing).
        percent = fraction_attr(child(ln_spc, A, "spcPct"), "val")
        if percent is not None:
            line_spacing = percent
        else:
            # ``spcPts`` is an *absolute* leading in 1/100 pt; it is not a
            # multiple of the font size, so it is kept in points.
            points = int_attr(child(ln_spc, A, "spcPts"), "val")
            if points is not None:
                line_spacing_pt = points / 100
    return ParaFormat(
        align=ppr.get("algn"),
        bullet=bullet,
        margin_left_emu=int_attr(ppr, "marL"),
        indent_emu=int_attr(ppr, "indent"),
        space_before_pt=_space_pt(child(ppr, A, "spcBef")),
        space_after_pt=_space_pt(child(ppr, A, "spcAft")),
        line_spacing=line_spacing,
        line_spacing_pt=line_spacing_pt,
    )


def _space_pt(spacing: Optional[ET.Element]) -> Optional[float]:
    points = int_attr(child(spacing, A, "spcPts"), "val")
    return points / 100 if points is not None else None


def body_format(body_pr: Optional[ET.Element]) -> BodyFormat:
    if body_pr is None:
        return BodyFormat()
    insets: Optional[dict[str, int]] = None
    raw = {
        "left": int_attr(body_pr, "lIns"),
        "top": int_attr(body_pr, "tIns"),
        "right": int_attr(body_pr, "rIns"),
        "bottom": int_attr(body_pr, "bIns"),
    }
    if any(value is not None for value in raw.values()):
        insets = {
            key: (value if value is not None else DEFAULT_INSETS[key])
            for key, value in raw.items()
        }
    norm = child(body_pr, A, "normAutofit")
    if norm is not None:
        autofit = "shrink"
    elif child(body_pr, A, "spAutoFit") is not None:
        autofit = "resize"
    elif child(body_pr, A, "noAutofit") is not None:
        autofit = "none"
    else:
        autofit = None
    return BodyFormat(
        anchor=body_pr.get("anchor"),
        insets=insets,
        autofit=autofit,
        font_scale=(
            fraction_attr(norm, "fontScale", scale=100000) if norm is not None else None
        ),
    )


def level_formats(style_el: Optional[ET.Element], theme: Theme) -> list[LevelFormat]:
    """``a:lstStyle`` / ``p:titleStyle`` / ``p:bodyStyle`` / ``p:otherStyle``.

    These all share the same ``a:lvlNpPr`` shape, so one parser covers them.
    """

    levels = empty_levels()
    if style_el is None:
        return levels
    for index in range(9):
        ppr = child(style_el, A, f"lvl{index + 1}pPr")
        if ppr is None:
            continue
        levels[index] = LevelFormat(
            para=para_format(ppr, theme),
            run=run_format(child(ppr, A, "defRPr"), theme),
        )
    return levels


def text_style_family(placeholder: Optional[str]) -> str:
    """Which master text style a placeholder uses: title | body | other."""

    if not placeholder:
        return "other"
    if placeholder in TITLE_PLACEHOLDERS:
        return "title"
    if placeholder in BODY_PLACEHOLDERS:
        return "body"
    return "other"


@dataclass(frozen=True)
class MasterStyles:
    """``p:sldMaster/p:txStyles`` plus the master's placeholder definitions."""

    title: list[LevelFormat] = field(default_factory=empty_levels)
    body: list[LevelFormat] = field(default_factory=empty_levels)
    other: list[LevelFormat] = field(default_factory=empty_levels)

    def levels_for(self, placeholder: Optional[str]) -> list[LevelFormat]:
        return getattr(self, text_style_family(placeholder))


@dataclass(frozen=True)
class PlaceholderDef:
    """One ``p:ph`` on a layout or master: geometry and text defaults."""

    type: str
    idx: Optional[str]
    bounds: Optional[Bounds] = None
    geometry: Optional[str] = None
    fill: Optional[dict[str, Any]] = None
    line: Optional[dict[str, Any]] = None
    body: BodyFormat = field(default_factory=BodyFormat)
    levels: list[LevelFormat] = field(default_factory=empty_levels)


def parse_tx_styles(master_root: Optional[ET.Element], theme: Theme) -> MasterStyles:
    styles = child(master_root, P, "txStyles") if master_root is not None else None
    return MasterStyles(
        title=level_formats(child(styles, P, "titleStyle"), theme),
        body=level_formats(child(styles, P, "bodyStyle"), theme),
        other=level_formats(child(styles, P, "otherStyle"), theme),
    )


def placeholder_defs(sp_tree: Optional[ET.Element], theme: Theme) -> list[PlaceholderDef]:
    """Placeholder shapes (``p:sp`` with ``p:ph``) declared on a layout/master."""

    found: list[PlaceholderDef] = []
    for shape in children(sp_tree, P, "sp"):
        nv = child(shape, P, "nvSpPr")
        ph = child(child(nv, P, "nvPr"), P, "ph")
        if ph is None:
            continue
        sp_pr = child(shape, P, "spPr")
        tx_body = child(shape, P, "txBody")
        xform = xform_from(sp_pr)
        found.append(
            PlaceholderDef(
                type=ph.get("type") or "body",
                idx=ph.get("idx"),
                bounds=xform.bounds() if xform is not None else None,
                geometry=geometry_from(sp_pr),
                fill=fill_from(sp_pr, theme),
                line=line_from(sp_pr, theme),
                body=body_format(child(tx_body, A, "bodyPr")),
                levels=level_formats(child(tx_body, A, "lstStyle"), theme),
            )
        )
    return found


def match_placeholder(
    definitions: list[PlaceholderDef], placeholder: Optional[str], idx: Optional[str]
) -> Optional[PlaceholderDef]:
    """Prefer an exact (type, idx) match, then a type-only match."""

    if not placeholder:
        return None
    exact = [
        definition
        for definition in definitions
        if definition.type == placeholder and (definition.idx or "0") == (idx or "0")
    ]
    if exact:
        return exact[0]
    by_type = [definition for definition in definitions if definition.type == placeholder]
    return by_type[0] if by_type else None


# -- transforms (groups) -----------------------------------------------------------
@dataclass(frozen=True)
class Xform:
    x: Optional[int] = None
    y: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    rotation: Optional[float] = None
    flip_h: bool = False
    flip_v: bool = False
    child_x: Optional[int] = None
    child_y: Optional[int] = None
    child_width: Optional[int] = None
    child_height: Optional[int] = None

    def bounds(self) -> Bounds:
        return Bounds(x=self.x, y=self.y, width=self.width, height=self.height)


def xform_from(sp_pr: Optional[ET.Element]) -> Optional[Xform]:
    xfrm = child(sp_pr, A, "xfrm")
    if xfrm is None:
        return None
    off = child(xfrm, A, "off")
    ext = child(xfrm, A, "ext")
    ch_off = child(xfrm, A, "chOff")
    ch_ext = child(xfrm, A, "chExt")
    rot = int_attr(xfrm, "rot")
    return Xform(
        x=int_attr(off, "x"),
        y=int_attr(off, "y"),
        width=int_attr(ext, "cx"),
        height=int_attr(ext, "cy"),
        rotation=(rot / ROTATION_SCALE) if rot is not None else None,
        flip_h=bool_attr(xfrm, "flipH") or False,
        flip_v=bool_attr(xfrm, "flipV") or False,
        child_x=int_attr(ch_off, "x"),
        child_y=int_attr(ch_off, "y"),
        child_width=int_attr(ch_ext, "cx"),
        child_height=int_attr(ch_ext, "cy"),
    )


@dataclass(frozen=True)
class Transform:
    """Affine scale+offset mapping child EMU space to slide EMU space."""

    sx: float = 1.0
    sy: float = 1.0
    ox: float = 0.0
    oy: float = 0.0

    def apply(self, bounds: Optional[Bounds]) -> Optional[Bounds]:
        if bounds is None:
            return None
        return Bounds(
            x=_scale(bounds.x, self.sx, self.ox),
            y=_scale(bounds.y, self.sy, self.oy),
            width=_scale(bounds.width, self.sx),
            height=_scale(bounds.height, self.sy),
        )

    def compose(self, outer: "Transform") -> "Transform":
        """``self`` applied first, then ``outer`` (group-nesting order)."""

        return Transform(
            sx=self.sx * outer.sx,
            sy=self.sy * outer.sy,
            ox=self.ox * outer.sx + outer.ox,
            oy=self.oy * outer.sy + outer.oy,
        )


def _scale(value: Optional[int], factor: float, offset: float = 0.0) -> Optional[int]:
    if value is None:
        return None
    return int(round(value * factor + offset))


def group_transform(xform: Optional[Xform]) -> Transform:
    """Map a group's child coordinate space to its parent space.

    ``x' = off + (x - chOff) * ext / chExt``. A group with no child extent
    (present in some authoring tools) is treated as an identity mapping, which
    places children by their raw coordinates rather than dropping them.
    """

    if xform is None:
        return Transform()
    if not xform.child_width or not xform.child_height or not xform.width or not xform.height:
        return Transform()
    sx = xform.width / xform.child_width
    sy = xform.height / xform.child_height
    ox = (xform.x or 0) - (xform.child_x or 0) * sx
    oy = (xform.y or 0) - (xform.child_y or 0) * sy
    return Transform(sx=sx, sy=sy, ox=ox, oy=oy)


def geometry_from(sp_pr: Optional[ET.Element]) -> Optional[str]:
    from app.compiler.extractors.theme import geometry_from as _geometry_from

    return _geometry_from(sp_pr)


# -- custom geometry ---------------------------------------------------------------
def _raw_point(el: Optional[ET.Element]) -> Optional[tuple[float, float]]:
    if el is None:
        return None
    try:
        return float(el.get("x", "0")), float(el.get("y", "0"))
    except ValueError:
        # Formula references (``x="*/2"``) need the guide list to evaluate; a
        # path we cannot resolve is reported as not-custom rather than guessed.
        return None


def _fmt(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".") or "0"


def custom_path_from(sp_pr: Optional[ET.Element]) -> Optional[str]:
    """``a:custGeom`` as an SVG path in the unit square, or ``None``.

    Only the shape outline is converted (``moveTo``/``lnTo``/``cubicBezTo``/
    ``quadBezTo``/``arcTo``/``close``); guide formulas and connection sites are
    not needed to draw it. Any construct we cannot resolve makes the whole path
    fall back to the preset geometry instead of drawing something wrong.
    """

    custom = child(sp_pr, A, "custGeom")
    if custom is None:
        return None
    path_list = child(custom, A, "pathLst")
    if path_list is None:
        return None
    segments: list[str] = []
    for path in children(path_list, A, "path"):
        width = int_attr(path, "w")
        height = int_attr(path, "h")
        if not width or not height:
            continue
        cx = cy = 0.0
        for node in list(path):
            local = node.tag.rsplit("}", 1)[-1]
            if local == "moveTo":
                point = _raw_point(child(node, A, "pt"))
                if point is None:
                    return None
                cx, cy = point
                segments.append(f"M{_fmt(cx / width)} {_fmt(cy / height)}")
            elif local == "lnTo":
                point = _raw_point(child(node, A, "pt"))
                if point is None:
                    return None
                cx, cy = point
                segments.append(f"L{_fmt(cx / width)} {_fmt(cy / height)}")
            elif local == "cubicBezTo":
                points = [_raw_point(pt) for pt in children(node, A, "pt")]
                if len(points) != 3 or any(pt is None for pt in points):
                    return None
                (x1, y1), (x2, y2), (end_x, end_y) = points  # type: ignore[misc]
                segments.append(
                    "C"
                    + " ".join(
                        f"{_fmt(px / width)} {_fmt(py / height)}"
                        for px, py in ((x1, y1), (x2, y2), (end_x, end_y))
                    )
                )
                cx, cy = end_x, end_y
            elif local == "quadBezTo":
                points = [_raw_point(pt) for pt in children(node, A, "pt")]
                if len(points) != 2 or any(pt is None for pt in points):
                    return None
                (x1, y1), (end_x, end_y) = points  # type: ignore[misc]
                segments.append(
                    "Q"
                    + " ".join(
                        f"{_fmt(px / width)} {_fmt(py / height)}"
                        for px, py in ((x1, y1), (end_x, end_y))
                    )
                )
                cx, cy = end_x, end_y
            elif local == "arcTo":
                arc = _arc_segment(node, width, height, cx, cy)
                if arc is None:
                    return None
                segments.append(arc[0])
                cx, cy = arc[1], arc[2]
            elif local == "close":
                segments.append("Z")
    if not segments:
        return None
    return " ".join(segments)


def _arc_segment(
    node: ET.Element, width: int, height: int, cx: float, cy: float
) -> Optional[tuple[str, float, float]]:
    """Convert a DrawingML ``a:arcTo`` to an SVG elliptical arc command."""

    radius_w = int_attr(node, "wR")
    radius_h = int_attr(node, "hR")
    start = int_attr(node, "stAng")
    swing = int_attr(node, "swAng")
    if None in (radius_w, radius_h, start, swing):
        return None
    start_rad = math.radians((start or 0) / 60000.0)
    swing_rad = math.radians((swing or 0) / 60000.0)
    centre_x = cx - (radius_w or 0) * math.cos(start_rad)
    centre_y = cy - (radius_h or 0) * math.sin(start_rad)
    end_rad = start_rad + swing_rad
    end_x = centre_x + (radius_w or 0) * math.cos(end_rad)
    end_y = centre_y + (radius_h or 0) * math.sin(end_rad)
    large_arc = 1 if abs(swing_rad) > math.pi else 0
    sweep = 1 if swing_rad > 0 else 0
    command = (
        f"A{_fmt((radius_w or 0) / width)} {_fmt((radius_h or 0) / height)} 0 "
        f"{large_arc} {sweep} {_fmt(end_x / width)} {_fmt(end_y / height)}"
    )
    return command, end_x, end_y
