"""Render-mode registry (V0-019).

The renderer is replaceable infrastructure (``docs/providers/DOCUMENT_RENDERER.md``)
and ``DEC-TECH-005`` (native PowerPoint rendering) is OPEN, so the platform ships
two *local* implementations behind the one ``DocumentRenderer`` interface and
selects between them by mode:

``faithful`` (default)
    Reproduces the source deck's own styling and placement as a structural SVG
    (``renderers/structural.py``, V0-018). Where a component cannot be reproduced
    (an unavailable source font, a chart/SmartArt, an un-inlinable picture) it is
    drawn in the platform look *in place* (``renderers/mentora_theme.py``) and
    recorded as a warning — V0-019 v5.
``themed``
    Recovers the extracted content's grouping and re-lays it out in the platform
    theme (``renderers/themed.py`` + ``renderers/flow.py``). The grouping and the
    content are the author's; the arrangement within each group and the
    appearance are the platform's. Opt-in.

Nothing is accepted about engine technology — neither mode needs any.

The mode is part of the renderer *identity*, and the package cache key binds that
identity, so a themed package can never be mistaken for a faithful one.
"""

from __future__ import annotations

from typing import Optional

from app.common.errors import AppError, ErrorCode
from app.compiler.renderers.base import DocumentRenderer, RenderConfig
from app.compiler.renderers.structural import StructuralSvgRenderer
from app.compiler.renderers.themed import ThemedSvgRenderer

MODE_THEMED = "themed"
MODE_FAITHFUL = "faithful"
#: Newest first; ``DEFAULT_RENDER_MODE`` is the product default (V0-019 v5:
#: the source layout, with the platform look for anything we cannot reproduce).
RENDER_MODES: tuple[str, ...] = (MODE_FAITHFUL, MODE_THEMED)
DEFAULT_RENDER_MODE = MODE_FAITHFUL

RENDER_MODE_LABELS: dict[str, str] = {
    MODE_FAITHFUL: "The deck's own layout, in the platform look where it cannot be reproduced",
    MODE_THEMED: "Grouping kept, re-laid out in the platform theme",
}


class UnknownRenderModeError(AppError):
    """An unsupported render mode was requested (fail fast, never a 500)."""

    code = ErrorCode.INVALID_REQUEST
    http_status = 400
    issue_code = "UNKNOWN_RENDER_MODE"

    def __init__(self, mode: object) -> None:
        super().__init__(
            f"unknown render mode {mode!r}; expected one of {', '.join(RENDER_MODES)}"
        )


def create_renderer(
    mode: str = DEFAULT_RENDER_MODE,
    object_store=None,
    config: Optional[RenderConfig] = None,
) -> DocumentRenderer:
    """Build the renderer for ``mode`` (the source layout unless asked otherwise)."""

    if mode == MODE_THEMED:
        return ThemedSvgRenderer(object_store, config)
    if mode == MODE_FAITHFUL:
        return StructuralSvgRenderer(object_store, config)
    raise UnknownRenderModeError(mode)


def build_renderers(
    object_store, config: Optional[RenderConfig] = None
) -> dict[str, DocumentRenderer]:
    """One renderer per mode, sharing the object store and render config."""

    return {mode: create_renderer(mode, object_store, config) for mode in RENDER_MODES}


__all__ = [
    "DEFAULT_RENDER_MODE",
    "MODE_FAITHFUL",
    "MODE_THEMED",
    "RENDER_MODE_LABELS",
    "RENDER_MODES",
    "UnknownRenderModeError",
    "build_renderers",
    "create_renderer",
]
