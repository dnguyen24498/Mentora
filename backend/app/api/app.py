"""FastAPI application factory.

Endpoints (see ``contracts/openapi/openapi.yaml``):
* ``POST /courses`` — create a course
* ``GET  /courses`` — list the tenant's courses
* ``GET  /courses/{courseId}/materials`` — list uploaded materials of a course
* ``POST /courses/{courseId}/materials`` — secure PPTX upload (V0-002)
* ``GET  /artifacts/{artifactId}`` — artifact metadata
* ``POST /artifacts/{artifactId}/extract`` — deterministic structural extraction (V0-004)
* ``POST /artifacts/{artifactId}/compile`` — extraction + per-slide render + fidelity gate (V0-005);
  ``?mode=themed|faithful`` selects the render mode (V0-019 default: ``themed``)
* ``GET  /artifacts/{artifactId}/renders/{order}`` — the fallback visual for one slide
  (``?mode=`` as above)
* ``POST /artifacts/{artifactId}/review-package`` — build the package (V0-006) and project the
  teacher review view of it (V0-007)
* ``GET  /artifacts/{artifactId}/review-package`` — the stored package's review view
* ``GET  /artifacts/{artifactId}/review-package/renders/{order}`` — one packaged slide render
* ``POST /artifacts/{artifactId}/review-package/decision`` — approve or reject (V0-007)
* ``GET  /artifacts/{artifactId}/review-package/review-state`` — decision, draft, blocking status
* ``POST /artifacts/{artifactId}/review-package/drafts`` — append a draft lesson-order revision
* ``GET  /artifacts/{artifactId}/review-package/drafts`` — draft revision history
* ``GET  /renderer`` — renderer capability and health
* ``GET  /health``

Authentication is out of scope for this slice: the authenticated tenant is read
from ``X-Institution-Id`` and every repository call is tenant-scoped. Replace
this with the OIDC/JWT dependency from ``docs/security/IDENTITY_AUTHORIZATION_AND_TOKENS.md``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Header, UploadFile
from fastapi.responses import JSONResponse, Response

from app.api.spa import SpaStaticFiles
from app.common.errors import AppError
from app.compiler.extractors.pptx import PptxExtractor
from app.compiler.package_builder.service import PackageBuildService
from app.compiler.render_service import RenderingService
from app.compiler.renderers.base import RenderConfig
from app.compiler.renderers.factory import (
    DEFAULT_RENDER_MODE,
    RENDER_MODE_LABELS,
    RENDER_MODES,
    build_renderers,
)
from app.compiler.service import ExtractionService
from app.config import Settings
from app.courses.repository import CourseRepository
from app.courses.upload_service import UploadService
from app.db.database import Database, init_db
from app.publication.repository import ReviewRepository
from app.publication.review import ReviewService
from app.publication.router import build_review_router
from app.publication.workflow import ReviewWorkflow
from app.storage.object_store import LocalObjectStore


def create_app(
    settings: Optional[Settings] = None,
    *,
    renderer_factory=None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    init_db(settings.database_path)

    # Thread-scoped connections: a request's transaction must never share a
    # connection with another request (the endpoints run in a worker threadpool).
    database = Database(settings.database_path)
    repository = CourseRepository(database)
    object_store = LocalObjectStore(settings.object_root)
    upload_service = UploadService(repository, object_store, settings)
    extractor = PptxExtractor(
        max_entries=settings.max_archive_entries,
        max_uncompressed_bytes=settings.max_uncompressed_bytes,
    )
    extraction_service = ExtractionService(repository, object_store, extractor)
    # The renderer is replaceable infrastructure: DEC-TECH-005 (native
    # PowerPoint rendering) is OPEN, so local implementations sit behind the
    # DocumentRenderer interface. V0-019 makes ``themed`` (re-author the content
    # in the platform theme) the default and keeps ``faithful`` (reproduce the
    # source slide's own styling) as an explicit mode. Tests inject their own
    # factory, which then serves every mode.
    render_config = RenderConfig()
    if renderer_factory:
        renderers = {mode: renderer_factory(object_store, render_config) for mode in RENDER_MODES}
    else:
        renderers = build_renderers(object_store, render_config)
    renderer = renderers[DEFAULT_RENDER_MODE]
    rendering_service = RenderingService(
        repository,
        object_store,
        extractor,
        renderer,
        renderers=renderers,
        default_mode=DEFAULT_RENDER_MODE,
        config=render_config,
    )
    package_build_service = PackageBuildService(repository, object_store, rendering_service)
    review_service = ReviewService(repository, object_store, package_build_service)
    # Review decisions and draft revisions are durable *state*, so they live in
    # the relational store — never in the immutable object store (DEC-DATA-001).
    review_workflow = ReviewWorkflow(
        review_service, ReviewRepository(database), repository
    )

    app = FastAPI(title="Mentora API", version="1.0.0")
    app.state.settings = settings
    app.state.repository = repository
    app.state.upload_service = upload_service
    app.state.extraction_service = extraction_service
    app.state.renderer = renderer
    app.state.rendering_service = rendering_service
    app.state.package_build_service = package_build_service
    app.state.review_service = review_service
    app.state.review_workflow = review_workflow

    @app.exception_handler(AppError)
    async def _handle_app_error(_request, exc: AppError) -> JSONResponse:
        body: dict = {"code": exc.code.value, "message": exc.message}
        # Validators carry their precise classification in `issue_code`
        # (package/fidelity/draft errors); expose it so clients can branch
        # without parsing prose.
        issue_code = getattr(exc, "issue_code", None)
        if issue_code:
            body["issue_code"] = issue_code
        return JSONResponse(status_code=exc.http_status, content={"error": body})

    def tenant(institution_id: str = Header(..., alias="X-Institution-Id")) -> str:
        return institution_id

    # Teacher review (V0-007): read-only projection of a built package plus the
    # approve/reject decision and draft lesson-order revisions.
    app.include_router(build_review_router(review_service, review_workflow, tenant))

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/courses", status_code=201)
    def create_course(
        title: str,
        institution_id: str = Depends(tenant),
        course_id: Optional[str] = None,
    ) -> dict[str, str]:
        repository.ensure_institution(institution_id)
        course = repository.create_course(institution_id, title, course_id)
        return {"course_id": course.course_id, "institution_id": course.institution_id}

    @app.get("/courses")
    def list_courses(institution_id: str = Depends(tenant)) -> list[dict[str, str]]:
        return [
            {"course_id": course.course_id, "title": course.title}
            for course in repository.list_courses(institution_id)
        ]

    @app.get("/courses/{course_id}/materials")
    def list_materials(course_id: str, institution_id: str = Depends(tenant)) -> list[dict]:
        """Materials already stored for a course (drives the file picker in the UI)."""

        return [
            {
                "artifact_id": material.artifact.artifact_id,
                "version_id": material.artifact.version_id,
                "version": material.version_number,
                "filename": material.artifact.filename,
                "media_type": material.artifact.media_type,
                "sha256": material.artifact.sha256,
                "byte_size": material.artifact.byte_size,
                "created_at": material.artifact.created_at,
                "job_id": material.job_id,
                "job_status": material.job_status,
                "job_updated_at": material.updated_at,
            }
            for material in repository.list_materials(institution_id, course_id)
        ]

    @app.post("/courses/{course_id}/materials", status_code=202)
    async def upload_material(
        course_id: str,
        file: UploadFile = File(...),
        institution_id: str = Depends(tenant),
        idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    ) -> dict:
        data = await file.read()
        result = upload_service.upload(
            institution_id=institution_id,
            course_id=course_id,
            filename=file.filename or "upload.pptx",
            data=data,
            idempotency_key=idempotency_key,
        )
        return {
            "artifact_id": result.artifact.artifact_id,
            "job_id": result.job.job_id,
            "version_id": result.version.version_id,
            "course_id": result.artifact.course_id,
            "filename": result.artifact.filename,
            "media_type": result.artifact.media_type,
            "sha256": result.artifact.sha256,
            "byte_size": result.artifact.byte_size,
            "job_status": result.job.status,
            "created": result.created,
        }

    @app.get("/artifacts/{artifact_id}")
    def get_artifact(artifact_id: str, institution_id: str = Depends(tenant)) -> dict:
        artifact = repository.get_artifact(institution_id, artifact_id)
        return {
            "artifact_id": artifact.artifact_id,
            "course_id": artifact.course_id,
            "version_id": artifact.version_id,
            "filename": artifact.filename,
            "media_type": artifact.media_type,
            "sha256": artifact.sha256,
            "byte_size": artifact.byte_size,
            "object_key": artifact.object_key,
            "created_at": artifact.created_at,
        }

    @app.post("/artifacts/{artifact_id}/extract")
    def extract_artifact(artifact_id: str, institution_id: str = Depends(tenant)) -> dict:
        document = extraction_service.extract(institution_id, artifact_id)
        return document.to_dict()

    @app.post("/artifacts/{artifact_id}/compile")
    def compile_artifact(
        artifact_id: str,
        institution_id: str = Depends(tenant),
        mode: Optional[str] = None,
    ) -> dict:
        """Extract, render every slide, and run the fidelity gate (V0-005).

        ``mode`` selects the render mode (V0-019): ``themed`` (default) re-authors
        the content in the platform theme, ``faithful`` reproduces the source
        slide's own styling.
        """

        return rendering_service.compile(institution_id, artifact_id, mode=mode).to_dict()

    @app.get("/artifacts/{artifact_id}/renders/{order}")
    def get_artifact_render(
        artifact_id: str,
        order: int,
        institution_id: str = Depends(tenant),
        mode: Optional[str] = None,
    ) -> Response:
        payload, _scene = rendering_service.render_scene_svg(
            institution_id, artifact_id, order, mode=mode
        )
        return Response(
            content=payload,
            media_type="image/svg+xml",
            headers={"Cache-Control": "private, max-age=60"},
        )

    @app.get("/renderer")
    def renderer_status(
        institution_id: str = Depends(tenant), mode: Optional[str] = None
    ) -> dict:
        """Capability and circuit-breaker state; drives admission decisions.

        Reports the *default* render mode, the available modes, and the
        capability of the requested one (``themed`` unless asked otherwise).
        """

        target = rendering_service.renderer_for(mode)
        theme = getattr(target, "theme", None)
        return {
            "default_mode": rendering_service.default_mode,
            "mode": mode or rendering_service.default_mode,
            "modes": [
                {"mode": name, "label": RENDER_MODE_LABELS.get(name, name)}
                for name in rendering_service.modes
            ],
            "identity": target.identity().to_dict(),
            "support": target.inspect_support().to_dict(),
            "health": target.health().to_dict(),
            "theme": theme.to_dict() if theme is not None else None,
        }

    # Serve the built frontend at "/" so the whole app runs on one origin
    # (localhost:8000). Mounted last so API routes above take precedence, and it
    # answers the SPA shell for client-side routes (/studio/{artifactId}) so a
    # deep link or a refresh works.
    if Path(settings.frontend_dist).is_dir():
        app.mount(
            "/",
            SpaStaticFiles(directory=str(settings.frontend_dist), html=True),
            name="frontend",
        )

    return app
