"""Compiler: source documents -> Content IR, deterministic and provider-neutral.

Layout:
* ``models/``      internal Content IR (never served raw to clients)
* ``extractors/``  source format -> Content IR
* ``renderers/``   Content IR -> fallback render + fidelity (V0-005)
* ``package_builder/`` Content IR + renders -> validated CTF package (V0-006)
* ``validators/``  scene/package invariants and publication gate (V0-005/V0-006)
"""

from app.compiler.extractors import PptxExtractor
from app.compiler.package_builder.service import (
    BUILDING_BASELINE_STAGE,
    PackageBuildResult,
    PackageBuildService,
)
from app.compiler.package_builder import PackageBuilder, PackageMetadata
from app.compiler.models import (
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
from app.compiler.render_service import CompileResult, RenderingService
from app.compiler.renderers import (
    CancelToken,
    DocumentRenderer,
    RenderConfig,
    RenderErrorCode,
    RenderStatus,
    StructuralSvgRenderer,
)
from app.compiler.service import ExtractionService
from app.compiler.validators import (
    PackageValidationReport,
    ValidationReport,
    assert_package_ok,
    assert_publishable,
    validate_package,
    validate_render,
)

__all__ = [
    "BUILDING_BASELINE_STAGE",
    "Bounds",
    "CONTENT_IR_SCHEMA_VERSION",
    "CancelToken",
    "CompileResult",
    "ContentIRDocument",
    "DocumentRenderer",
    "EXTRACTOR_NAME",
    "EXTRACTOR_VERSION",
    "ExtractionService",
    "FIDELITY_COMPATIBLE",
    "FIDELITY_DEGRADED",
    "FIDELITY_NATIVE",
    "FIDELITY_REQUIRES_REVIEW",
    "FIDELITY_STRUCTURAL",
    "FIDELITY_VALUES",
    "PackageBuildResult",
    "PackageBuildService",
    "PackageBuilder",
    "PackageMetadata",
    "PackageValidationReport",
    "PptxExtractor",
    "RenderConfig",
    "RenderErrorCode",
    "RenderStatus",
    "RenderingService",
    "ShapeObject",
    "SlideScene",
    "StructuralSvgRenderer",
    "TextParagraph",
    "TextRun",
    "ValidationReport",
    "assert_package_ok",
    "assert_publishable",
    "validate_package",
    "validate_render",
]
