"""Namespace/attribute plumbing shared by the OOXML extractor modules.

Dependency-free: only ``xml.etree``. Kept separate from ``pptx.py`` so the theme
and style resolvers can use it without importing the extractor (avoids a cycle).
"""

from __future__ import annotations

import posixpath
from typing import Optional
import xml.etree.ElementTree as ET

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CHART = "http://schemas.openxmlformats.org/drawingml/2006/chart"

#: Local units (``a:off``/``a:ext``/``a:sz`` are EMU: 914400 per inch).
EMU_PER_INCH = 914400
EMU_PER_POINT = 12700
#: The slide SVG is drawn at 96 dpi, so one EMU is 1/9525 px.
EMU_PER_PIXEL = 9525


def qn(ns: str, local: str) -> str:
    return f"{{{ns}}}{local}"


def child(el: Optional[ET.Element], ns: str, local: str) -> Optional[ET.Element]:
    return el.find(qn(ns, local)) if el is not None else None


def children(el: Optional[ET.Element], ns: str, local: str) -> list[ET.Element]:
    return el.findall(qn(ns, local)) if el is not None else []


def int_attr(el: Optional[ET.Element], name: str) -> Optional[int]:
    """Integer attribute, tolerating OOXML's optional-sign/whitespace forms."""

    if el is None:
        return None
    raw = el.get(name)
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        try:
            return int(float(raw))
        except ValueError:
            return None


def bool_attr(el: Optional[ET.Element], name: str) -> Optional[bool]:
    """OOXML boolean: "1"/"true" are true, "0"/"false" are false."""

    if el is None:
        return None
    raw = el.get(name)
    if raw is None:
        return None
    if raw in ("1", "true", "on"):
        return True
    if raw in ("0", "false", "off"):
        return False
    return None


def fraction_attr(el: Optional[ET.Element], name: str, *, scale: int = 100000) -> Optional[float]:
    """A 1/``scale`` percentage attribute as a fraction (0.5 for "50000")."""

    value = int_attr(el, name)
    if value is None:
        return None
    return value / scale


def emu_to_pt(value: Optional[int]) -> Optional[float]:
    return None if value is None else value / EMU_PER_POINT


def rels_part_for(part: str) -> str:
    directory, base = posixpath.split(part)
    return posixpath.join(directory, "_rels", f"{base}.rels")


def resolve_target(part: str, target: str) -> str:
    return posixpath.normpath(posixpath.join(posixpath.dirname(part), target))


#: Relationship type suffixes (the full URI ends with these).
REL_SLIDE_LAYOUT = "/slideLayout"
REL_SLIDE_MASTER = "/slideMaster"
REL_THEME = "/theme"
REL_IMAGE = "/image"
REL_NOTES_SLIDE = "/notesSlide"
