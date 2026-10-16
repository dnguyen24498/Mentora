"""Content IR -> fallback render, with explicit fidelity and warnings.

``DocumentRenderer`` is a replaceable capability behind an interface
(``docs/providers/DOCUMENT_RENDERER.md``). ``StructuralSvgRenderer`` is the
deterministic local implementation used while ``DEC-TECH-005`` (native
PowerPoint rendering) is OPEN; ``FakeRenderer`` is the required test double.
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
from app.compiler.renderers.structural import (
    MISSING_FONT_PREFIX,
    UNSUPPORTED_OBJECT_PREFIX,
    StructuralSvgRenderer,
)
from app.compiler.renderers.telemetry import RenderMetrics, RenderTelemetry

__all__ = [
    "CancelToken",
    "CapabilityReport",
    "CircuitOpenError",
    "DocumentRenderer",
    "MISSING_FONT_PREFIX",
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
    "UNSUPPORTED_OBJECT_PREFIX",
]
