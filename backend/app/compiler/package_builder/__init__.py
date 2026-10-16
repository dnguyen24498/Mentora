"""Baseline Content Package builder (V0-006).

Turns a rendered Content IR document into the immutable, validated runtime
package described by ``contracts/ctf/*.schema.json``:

* ``layout.py``  — package path conventions.
* ``models.py``  — package/metadata/lesson-plan models.
* ``builder.py`` — the pure IR -> package mapping.
* ``service.py`` — the stage entry point (render, gate, build, validate, store).

Validation lives in :mod:`app.compiler.validators.package`.

``service`` is exported lazily (PEP 562) because it imports the validators, which
in turn import this package's ``layout``/``models`` for the contract field lists.
Resolving that edge at attribute access instead of at import time keeps
``import app.compiler`` order-independent.
"""

from typing import TYPE_CHECKING, Any

from app.compiler.package_builder.builder import (
    PackageBuildError,
    PackageBuilder,
    content_package_version,
    lesson_plan_version_for,
    resolve_assets,
)
from app.compiler.package_builder.layout import MANIFEST_FILENAME, package_prefix
from app.compiler.package_builder.models import (
    BaselinePackage,
    LessonPlan,
    LessonSection,
    PackageFile,
    PackageMetadata,
    SceneStep,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.compiler.package_builder.service import (
        BUILDING_BASELINE_STAGE,
        PackageBuildResult,
        PackageBuildService,
    )

_LAZY_SERVICE_EXPORTS = {
    "BUILDING_BASELINE_STAGE",
    "PackageBuildResult",
    "PackageBuildService",
}

__all__ = [
    "BUILDING_BASELINE_STAGE",
    "MANIFEST_FILENAME",
    "BaselinePackage",
    "LessonPlan",
    "LessonSection",
    "PackageBuildError",
    "PackageBuildResult",
    "PackageBuildService",
    "PackageBuilder",
    "PackageFile",
    "PackageMetadata",
    "SceneStep",
    "content_package_version",
    "lesson_plan_version_for",
    "package_prefix",
    "resolve_assets",
]


def __getattr__(name: str) -> Any:
    if name in _LAZY_SERVICE_EXPORTS:
        from app.compiler.package_builder import service

        return getattr(service, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
