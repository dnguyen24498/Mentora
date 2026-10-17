"""Render stage orchestration: artifact -> Content IR -> fallback renders -> gate.

Pipeline position is ``EXTRACTING -> RENDERING -> VALIDATING`` from
``docs/state-machines/COMPILER_JOB_STATE_MACHINE.md``. Job claiming, leases,
checkpoints and retry persistence belong to the job runner (V0-003) and are
deliberately **not** implemented here: this service is a deterministic,
re-runnable stage function.

Re-running is safe and idempotent — renders are content-addressed, so an
unchanged document reuses the same assets, and nothing but the job status row is
written.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping, Optional

from app.common.errors import RendererUnavailableError
from app.compiler.media import document_media_refs, read_media_parts
from app.compiler.models.ir import ContentIRDocument, SlideScene
from app.compiler.renderers.base import (
    CancelToken,
    DocumentRenderer,
    RenderBudget,
    RenderConfig,
    RenderErrorCode,
    RenderReport,
    RenderRequest,
    RenderStatus,
    RendererError,
    SceneRender,
)
from app.compiler.renderers.factory import DEFAULT_RENDER_MODE, UnknownRenderModeError
from app.compiler.renderers.telemetry import RenderTelemetry
from app.compiler.validators.fidelity import ValidationReport, validate_render
from app.courses.models import CompilerJobStatus
from app.courses.repository import CourseRepository
from app.storage.object_store import ObjectStore


@dataclass(frozen=True)
class CompileResult:
    """The rendered document plus its render and validation reports."""

    document: ContentIRDocument
    report: RenderReport
    validation: ValidationReport

    def to_dict(self) -> dict:
        return {
            "content_ir": self.document.to_dict(),
            "render": self.report.to_dict(),
            "validation": self.validation.to_dict(),
            "job_status": _job_status(self.validation).value,
        }


def _job_status(validation: ValidationReport) -> CompilerJobStatus:
    return CompilerJobStatus.EXTRACTED if validation.publishable else CompilerJobStatus.FAILED


def apply_render(document: ContentIRDocument, report: RenderReport) -> ContentIRDocument:
    """Project the render report onto the scenes.

    ``DEC-CONTENT-006``: after this step every scene carries explicit fidelity,
    renderer identity, a fallback asset, and warnings.
    """

    scenes: list[SlideScene] = []
    for scene in document.slides:
        result = report.scene(scene.order)
        if result is None:
            scenes.append(scene)
            continue
        scenes.append(
            replace(
                scene,
                fidelity=result.fidelity or scene.fidelity,
                fallback_asset=result.asset_ref,
                renderer=result.renderer.to_dict() if result.renderer else None,
                warnings=[*scene.warnings, *result.warnings, *_error_warnings(result)],
            )
        )
    return replace(document, slides=scenes)


def _error_warnings(result: SceneRender) -> list[str]:
    if result.status is RenderStatus.RENDERED or result.error_code is None:
        return []
    return [f"RENDER_{result.status.value}:{result.error_code.value}"]


class RenderingService:
    def __init__(
        self,
        repository: CourseRepository,
        object_store: ObjectStore,
        extractor: object,
        renderer: object,
        *,
        renderers: Optional[Mapping[str, DocumentRenderer]] = None,
        default_mode: str = DEFAULT_RENDER_MODE,
        config: Optional[RenderConfig] = None,
        telemetry: Optional[RenderTelemetry] = None,
    ) -> None:
        self._repository = repository
        self._object_store = object_store
        self._extractor = extractor
        self._renderer = renderer
        self._renderers: dict[str, DocumentRenderer] = dict(
            renderers or {default_mode: renderer}
        )
        self._default_mode = default_mode
        self._config = config or getattr(renderer, "config", None) or RenderConfig()
        self.telemetry = telemetry or RenderTelemetry()

    @property
    def renderer(self):
        """The default renderer; kept for callers that need one identity."""

        return self._renderer

    @property
    def default_mode(self) -> str:
        return self._default_mode

    @property
    def modes(self) -> tuple[str, ...]:
        return tuple(self._renderers)

    def renderer_for(self, mode: Optional[str] = None) -> DocumentRenderer:
        """The renderer for ``mode`` (the default when omitted).

        An unknown mode is a client error, not a fallback: silently rendering a
        different appearance than the caller asked for would be misleading.
        """

        resolved = mode or self._default_mode
        try:
            return self._renderers[resolved]
        except KeyError:
            raise UnknownRenderModeError(resolved) from None

    def compile(
        self,
        institution_id: str,
        artifact_id: str,
        *,
        cancel: Optional[CancelToken] = None,
        mode: Optional[str] = None,
    ) -> CompileResult:
        """Extract, render every slide, and validate. Tenant-scoped throughout."""

        renderer = self.renderer_for(mode)

        # Tenant-scoped read: raises for another institution's artifact.
        artifact = self._repository.get_artifact(institution_id, artifact_id)
        data = self._object_store.get(artifact.object_key)
        document = self._extractor.extract(
            data,
            source_ref={
                "artifact_id": artifact.artifact_id,
                "course_id": artifact.course_id,
                "version_id": artifact.version_id,
                "filename": artifact.filename,
            },
            source_sha256=artifact.sha256,
        )

        identity = renderer.identity()
        self.telemetry.record_render_started(
            artifact_id=artifact_id,
            scene_count=document.slide_count,
            renderer={**identity.to_dict(), "mode": mode or self._default_mode},
        )

        # Pictures travel with the request: the compiler (which already holds the
        # package bytes) resolves them, so the renderer never reads the source
        # (``DEC-CONTENT-001``).
        media = read_media_parts(data, document_media_refs(document))

        budget = RenderBudget(
            self._config.deadline_seconds,
            max_attempts=self._config.max_attempts,
        )
        try:
            report = renderer.render(
                RenderRequest(
                    document=document,
                    identity=identity,
                    trace_id=artifact.sha256[:12],
                    correlation_id=artifact_id,
                    media=media,
                ),
                budget=budget,
                cancel=cancel,
            )
        except RendererError as exc:
            # Admission control: the capability is unusable, so the stage fails
            # with a stable code instead of pretending each slide failed.
            self.telemetry.emit(
                "compiler.render.unavailable",
                artifact_id=artifact_id,
                institution_id=institution_id,
                code=exc.code.value,
                message=exc.message,
            )
            self._set_job_status(institution_id, artifact_id, CompilerJobStatus.FAILED)
            raise RendererUnavailableError(f"renderer unavailable: {exc.message}") from exc

        rendered = apply_render(document, report)
        validation = validate_render(rendered, report)
        self.telemetry.record_render_report(
            artifact_id=artifact_id,
            report=report,
            institution_id=institution_id,
            trace_id=artifact.sha256[:12],
            publishable=validation.publishable,
            requires_review=validation.requires_review,
        )
        self._set_job_status(
            institution_id,
            artifact_id,
            _job_status(validation),
        )
        return CompileResult(document=rendered, report=report, validation=validation)

    def render_scene_svg(
        self, institution_id: str, artifact_id: str, order: int, *, mode: Optional[str] = None
    ) -> tuple[bytes, SceneRender]:
        """Deterministic per-slide visual, re-derived from the stored artifact.

        Re-rendering (rather than persisting a lookup table) keeps this stage
        stateless; content-addressed assets make the repeat write a no-op.
        """

        result = self.compile(institution_id, artifact_id, mode=mode)
        scene = result.report.scene(order)
        if scene is None or scene.asset_ref is None:
            raise RendererUnavailableError(
                f"scene {order} has no render "
                f"({scene.error_code.value if scene and scene.error_code else 'unknown'})"
            )
        return self._object_store.get(scene.asset_ref), scene

    def _set_job_status(
        self, institution_id: str, artifact_id: str, status: CompilerJobStatus
    ) -> None:
        job = self._repository.get_job_for_artifact(institution_id, artifact_id)
        self._repository.set_job_status(institution_id, job.job_id, status)


__all__ = [
    "CompileResult",
    "RenderingService",
    "apply_render",
    "RenderErrorCode",
]
