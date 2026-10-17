"""Content IR -> fallback render, with explicit fidelity and warnings.

``DocumentRenderer`` is a replaceable capability behind an interface
(``docs/providers/DOCUMENT_RENDERER.md``). Two deterministic local
implementations are shipped while ``DEC-TECH-005`` (native PowerPoint rendering)
is OPEN, selected by mode (``renderers/factory.py``):

* ``ThemedSvgRenderer`` — recovers the author's grouping and re-lays the content
  out in the platform theme (``renderers/flow.py``); the **default** mode
  (V0-019).
* ``StructuralSvgRenderer`` — reproduces the source deck's own styling and
  placement; the ``faithful`` mode (V0-018).

``FakeRenderer`` is the required test double.
"""

from app.compiler.renderers.base import (
    CancelToken,
    CapabilityReport,
    CircuitOpenError,
    DocumentRenderer,
    RenderBudget,
    RenderConfig,
    RenderErrorCode,
    RenderReport,
    RenderRequest,
    RenderStatus,
    RenderUsage,
    RendererError,
    RendererHealth,
    RendererIdentity,
    SceneRender,
)
from app.compiler.renderers.factory import (
    DEFAULT_RENDER_MODE,
    MODE_FAITHFUL,
    MODE_THEMED,
    RENDER_MODES,
    UnknownRenderModeError,
    build_renderers,
    create_renderer,
)
from app.compiler.renderers.mentora_theme import DEFAULT_THEME, MentoraTheme
from app.compiler.renderers.structural import (
    MISSING_FONT_PREFIX,
    UNSUPPORTED_OBJECT_PREFIX,
    StructuralSvgRenderer,
)
from app.compiler.renderers.telemetry import RenderMetrics, RenderTelemetry
from app.compiler.renderers.themed import (
    TEXT_OVERFLOW_PREFIX,
    ThemedSvgRenderer,
)

__all__ = [
    "CancelToken",
    "CapabilityReport",
    "CircuitOpenError",
    "DEFAULT_RENDER_MODE",
    "DEFAULT_THEME",
    "DocumentRenderer",
    "MISSING_FONT_PREFIX",
    "MODE_FAITHFUL",
    "MODE_THEMED",
    "MentoraTheme",
    "RENDER_MODES",
    "RenderBudget",
    "RenderConfig",
    "RenderErrorCode",
    "RenderMetrics",
    "RenderReport",
    "RenderRequest",
    "RenderStatus",
    "RenderTelemetry",
    "RenderUsage",
    "RendererError",
    "RendererHealth",
    "RendererIdentity",
    "SceneRender",
    "StructuralSvgRenderer",
    "TEXT_OVERFLOW_PREFIX",
    "ThemedSvgRenderer",
    "UNSUPPORTED_OBJECT_PREFIX",
    "UnknownRenderModeError",
    "build_renderers",
    "create_renderer",
]
