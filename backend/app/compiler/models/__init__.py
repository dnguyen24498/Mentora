"""Content IR models (compiler-internal; never served raw to clients)."""

from app.compiler.models.ir import (
    Bounds,
    CONTENT_IR_SCHEMA_VERSION,
    ContentIRDocument,
    EXTRACTOR_NAME,
    EXTRACTOR_VERSION,
    FIDELITY_COMPATIBLE,
    FIDELITY_DEGRADED,
    FIDELITY_NATIVE,
    FIDELITY_REQUIRES_REVIEW,
    FIDELITY_STRUCTURAL,
    FIDELITY_VALUES,
    ShapeObject,
    SlideScene,
    TextParagraph,
    TextRun,
)

__all__ = [
    "Bounds",
    "CONTENT_IR_SCHEMA_VERSION",
    "ContentIRDocument",
    "EXTRACTOR_NAME",
    "EXTRACTOR_VERSION",
    "FIDELITY_COMPATIBLE",
    "FIDELITY_DEGRADED",
    "FIDELITY_NATIVE",
    "FIDELITY_REQUIRES_REVIEW",
    "FIDELITY_STRUCTURAL",
    "FIDELITY_VALUES",
    "ShapeObject",
    "SlideScene",
    "TextParagraph",
    "TextRun",
]
