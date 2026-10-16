"""Package build orchestration: artifact -> renders -> baseline package (V0-006).

Pipeline position is the *baseline builder* stage of
``docs/architecture/04_CONTENT_COMPILER.md``
(``… → Content IR → baseline builder → … → validation``). It runs after the
render stage (V0-005) whose fidelity gate must have passed.

Like every other compiler stage in V0, this is a deterministic, re-runnable
stage function: no job claiming, no lease, no checkpoint persistence. Those
belong to the job runner (V0-003) and are deliberately not implemented here.

Re-running is safe: rendering is content-addressed and the package paths are
derived from content, so an unchanged document rebuilds byte-identical files and
overwrites them in place.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Optional
from uuid import uuid4

from app.compiler.models.ir import EXTRACTOR_VERSION
from app.compiler.package_builder.builder import (
    PackageBuilder,
    content_package_version,
    lesson_plan_version_for,
    resolve_assets,
)
from app.compiler.package_builder.models import BaselinePackage, PackageMetadata
from app.compiler.validators.fidelity import ValidationReport, assert_publishable
from app.compiler.validators.package import (
    PackageValidationReport,
    assert_package_ok,
    validate_package,
)
from app.courses.repository import CourseRepository
from app.storage.object_store import ObjectStore

if TYPE_CHECKING:  # import-time only: render_service imports the validators
    from app.compiler.render_service import CompileResult, RenderingService
    from app.compiler.renderers.base import RenderReport

#: Compiler job stage this service implements. ``CompilerJobStatus`` has no
#: ``BUILDING_BASELINE`` member and ``app/courses/`` is outside this task's
#: writable area, so the stage is reported in telemetry instead of being written
#: to the job row (the state machine and its persistence are V0-003's).
BUILDING_BASELINE_STAGE = "BUILDING_BASELINE"


@dataclass(frozen=True)
class PackageBuildResult:
    """A built, validated, stored package plus the reports that justify it."""

    package: BaselinePackage
    render: RenderReport
    render_validation: ValidationReport
    validation: PackageValidationReport
    prefix: str
    stage: str = BUILDING_BASELINE_STAGE

    @property
    def requires_review(self) -> bool:
        return self.validation.requires_review

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "prefix": self.prefix,
            "package": self.package.to_dict(),
            "package_validation": self.validation.to_dict(),
            "render_validation": self.render_validation.to_dict(),
            "job_status": "EXTRACTED" if self.validation.ok else "FAILED",
        }


class PackageBuildService:
    """Builds a Baseline Content Package from a stored artifact."""

    def __init__(
        self,
        repository: CourseRepository,
        object_store: ObjectStore,
        rendering_service: RenderingService,
        *,
        builder: Optional[PackageBuilder] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._repository = repository
        self._object_store = object_store
        self._rendering = rendering_service
        self._builder = builder or PackageBuilder()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def build(
        self,
        institution_id: str,
        artifact_id: str,
        *,
        package_id: Optional[str] = None,
        created_at: Optional[str] = None,
        write: bool = True,
    ) -> PackageBuildResult:
        """Extract, render, gate, package, validate, and store. Tenant-scoped.

        ``package_id``/``created_at`` are injectable so tests can assert
        byte-stable output; production callers omit them.
        """

        # 1. Render (V0-005). ``compile`` is tenant-scoped: another institution's
        #    artifact raises before any work happens.
        compiled: CompileResult = self._rendering.compile(institution_id, artifact_id)

        # 2. The fidelity gate is authoritative: a FAILED render, a cancelled
        #    pass, or a missing render must never enter a package.
        assert_publishable(compiled.validation)

        artifact = self._repository.get_artifact(institution_id, artifact_id)
        version = self._repository.get_version(institution_id, artifact.version_id)

        identity = compiled.report.renderer or self._rendering.renderer.identity()
        content_version = content_package_version(
            artifact.sha256,
            config_hash=identity.config_hash,
            compiler_version=EXTRACTOR_VERSION,
        )
        metadata = PackageMetadata(
            tenant_id=artifact.institution_id,
            course_id=artifact.course_id,
            course_version=str(version.version),
            content_package_version=content_version,
            lesson_plan_version=lesson_plan_version_for(content_version),
            lesson_id=f"baseline:{artifact.course_id}",
            package_id=package_id or str(uuid4()),
            created_at=created_at or self._clock().isoformat(),
            # Indexing is V0-014; a baseline package is usable without it
            # (DEC-CONTENT-002), so it declares itself unindexed.
            knowledge_index_version="unindexed",
            # No Teaching Graph: the baseline path is deliberately AI-free.
            teaching_graph_version=None,
            compiler_version=EXTRACTOR_VERSION,
            source_sha256=artifact.sha256,
        )

        # 3. Copy every referenced asset out of the compiler's store so the
        #    package is self-contained.
        assets = resolve_assets(compiled.document, get=self._object_store.get)

        # 4. Build, then validate against the contracts and re-check the gate.
        package = self._builder.build(
            compiled.document, metadata=metadata, assets=assets
        )
        validation = validate_package(package, render_validation=compiled.validation)
        assert_package_ok(validation)

        prefix = package.write_to(self._object_store) if write else ""
        self._telemetry.emit(
            "compiler.package.built",
            artifact_id=artifact_id,
            institution_id=institution_id,
            package_id=metadata.package_id,
            stage=BUILDING_BASELINE_STAGE,
            content_package_version=content_version,
            scenes=validation.scene_count,
            files=validation.file_count,
            bytes=sum(f.byte_size for f in package.files) + len(package.manifest_bytes),
            renderer=identity.to_dict(),
            requires_review=validation.requires_review,
            teaching_graph_version=metadata.teaching_graph_version,
            knowledge_index_version=metadata.knowledge_index_version,
        )
        return PackageBuildResult(
            package=package,
            render=compiled.report,
            render_validation=compiled.validation,
            validation=validation,
            prefix=prefix,
        )

    @property
    def _telemetry(self):
        telemetry = getattr(self._rendering, "telemetry", None)
        if telemetry is None:  # a rendering service double without telemetry
            from app.compiler.renderers.telemetry import RenderTelemetry

            self._rendering.telemetry = RenderTelemetry()  # type: ignore[attr-defined]
            telemetry = self._rendering.telemetry
        return telemetry


__all__ = [
    "BUILDING_BASELINE_STAGE",
    "PackageBuildResult",
    "PackageBuildService",
]
