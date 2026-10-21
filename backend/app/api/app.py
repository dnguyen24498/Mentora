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
* ``POST /course-versions/{versionId}/publish`` — seal, index and commit an approved
  version (V0-008; idempotent, returns the publication)
* ``GET  /course-versions/{versionId}/publication`` — the newest publication of a version
  (``?verify=true`` re-checks the pinned package against its seal)
* ``GET  /publications/{publicationId}`` — one publication by identity (superseded included)
* ``GET  /courses/{courseId}/publications`` — a course's publication history
* ``POST /classes`` — schedule a class against a course (V0-009)
* ``GET  /classes`` — the tenant's classes
* ``GET  /classes/{classId}`` — the class, its session and its pinned version tuple
* ``POST /classes/{classId}/start`` — resolve and pin the exact runtime tuple, then
  ``ACTIVE`` (idempotent; ``409`` ``CLASS_NOT_READY`` + ``issue_code`` on a refusal)
* ``GET  /classes/{classId}/snapshot`` — the durable, checksum-validated snapshot
* ``POST /classes/{classId}/enrollments`` — enroll a student (idempotent)
* ``GET  /classes/{classId}/enrollments`` — the class roster
* ``POST /classes/{classId}/bootstrap-token`` — short-lived join credential, issued
  only to an enrolled student of a running class (``403`` ``NOT_ENROLLED`` otherwise)
* ``GET  /renderer`` — renderer capability and health
* ``POST /auth/login`` — sign in; a short-lived session token, returned once (V0-021)
* ``POST /auth/logout`` — revoke the presented session (idempotent)
* ``POST /auth/password`` — change the presented account's own password (V0-023)
* ``GET  /auth/me`` — the principal the presented session authorizes
* ``GET  /health``

Authentication (V0-021). V0-023 makes **every route require a real session**: a
request resolves a principal and the tenant is derived from it, so the tenant can no
longer be named by the caller (``app/api/security.py``), and the pre-auth
``X-Institution-Id`` development shortcut is off by default (an explicit
``MENTORA_DEV_TENANT_HEADER=1`` opts a development deployment in). The credential
*mechanism* is not decided — the canonical architecture names institutional
federation and no ADR accepts an implementation — so what is wired is a labelled
development mock behind ``app.identity.port.Authenticator``; V0-023 makes the
credential it manages a password an administrator sets. The one-shot
first-administrator bootstrap is gated by its own switch (``Settings.admin_bootstrap``)
so a locked deployment can still create its first account.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Header, UploadFile
from fastapi.responses import JSONResponse, Response

from app.api.spa import SpaStaticFiles
from app.api.identity_router import build_identity_router
from app.api.accounts_router import build_accounts_router
from app.api.security import build_api_security
from app.classroom.catalog import BaselineRuntimeCatalog
from app.classroom.repository import ClassRepository
from app.classroom.router import build_class_router
from app.classroom.service import ClassroomService
from app.classroom.timeline.router import build_timeline_router
from app.classroom.timeline.service import TimelineService
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
from app.identity.models import Principal, Scope
from app.publication.index import BaselineIndexBuilder
from app.publication.repository import PublicationRepository, ReviewRepository
from app.publication.review import ReviewService
from app.publication.router import build_publication_router, build_review_router
from app.publication.service import PublicationService
from app.publication.workflow import ReviewWorkflow
from app.providers.factory import build_identity_service, build_speech_service
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
    # DocumentRenderer interface. V0-019 v5 makes ``faithful`` (the deck's own
    # layout; anything not reproducible is drawn in the platform look in place)
    # the default and keeps ``themed`` (re-lay the content out in the platform
    # theme) as an explicit mode. Tests inject their own factory, which then
    # serves every mode.
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
    review_repository = ReviewRepository(database)
    review_workflow = ReviewWorkflow(review_service, review_repository, repository)
    # The atomic publication transition (V0-008). The index builder is replaceable
    # infrastructure: DEC-TECH-008 (search/vector technology) is OPEN, so the local
    # baseline only establishes the index-version *identity* a publication pins and
    # builds no index content (V0-014 does).
    publication_service = PublicationService(
        repository,
        review_repository,
        PublicationRepository(database),
        object_store,
        package_build_service,
        index_builder=BaselineIndexBuilder(),
    )
    # Class start (V0-009). The runtime catalog is replaceable infrastructure:
    # DEC-TECH-009 (cloud/provider/regions) is OPEN, so the home region comes from
    # configuration and the policy version names the LOCKED default policy set. The
    # capability probe reports the *default* renderer's identity, which the session
    # pins — a later renderer upgrade cannot change what a running session warmed.
    classroom_service = ClassroomService(
        repository,
        ClassRepository(database),
        object_store,
        catalog=BaselineRuntimeCatalog(region=settings.home_region),
        capability_probe=lambda: {
            "identity": renderer.identity().to_dict(),
            "support": renderer.inspect_support().to_dict(),
        },
    )

    # Timeline narration (V0-013). DEC-TECH-007 (TTS/OmniVoice) is OPEN, so the
    # speech service wires the provider-neutral port to its deterministic local
    # adapter; a decided provider is one registry entry in app/providers/factory.py.
    speech_service = build_speech_service(settings.tts_provider)
    timeline_service = TimelineService(classroom_service, speech_service)

    app = FastAPI(title="Mentora API", version="1.0.0")
    app.state.speech_service = speech_service
    app.state.timeline_service = timeline_service
    app.state.settings = settings
    app.state.repository = repository
    app.state.upload_service = upload_service
    app.state.extraction_service = extraction_service
    app.state.renderer = renderer
    app.state.rendering_service = rendering_service
    app.state.package_build_service = package_build_service
    app.state.review_service = review_service
    app.state.review_repository = review_repository
    app.state.review_workflow = review_workflow
    app.state.publication_service = publication_service
    app.state.classroom_service = classroom_service

    # Identity (V0-021). The credential *mechanism* is not a decided technology —
    # the canonical architecture names institutional federation (OIDC/OAuth) and no
    # ADR accepts an implementation — so the registered adapter is a labelled
    # development mock behind the provider-neutral Authenticator port
    # (app/providers/local_credentials.py), the same shape ADR-P007 gives the TTS
    # mock while DEC-TECH-007 is OPEN.
    identity_service = build_identity_service(
        database, session_ttl_seconds=settings.session_ttl_seconds
    )
    security = build_api_security(
        identity_service,
        allow_dev_header=settings.dev_tenant_header,
        allow_admin_bootstrap=settings.admin_bootstrap,
        telemetry=identity_service.telemetry,
    )
    app.state.identity_service = identity_service
    app.state.security = security

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

    # The tenant every repository call is scoped by comes from the authenticated
    # principal now (app/api/security.py), not from a caller-supplied header.
    tenant = security.tenant
    # Capability guards: a student token is refused on every teacher verb here.
    require = security.require

    # Identity (V0-021): sign in, sign out, and who the presented session is.
    app.include_router(build_identity_router(security))
    # The directory (V0-022): an institution administrator creates, reads, changes
    # and removes teacher and student accounts. Composed with the classroom service
    # so that removing an account a class references is refused.
    app.include_router(build_accounts_router(security, classroom_service))
    # Teacher review (V0-007): read-only projection of a built package plus the
    # approve/reject decision and draft lesson-order revisions.
    app.include_router(build_review_router(review_service, review_workflow, security))
    # Atomic publication (V0-008): seal/index/commit an approved version and serve
    # published versions, including superseded ones.
    app.include_router(build_publication_router(publication_service, security))
    # Class and runtime session plan (V0-009): schedule a class, start it by
    # pinning the exact runtime tuple once, serve the durable snapshot, serve the
    # pinned scene, and authorize joins against the class enrollment.
    app.include_router(build_class_router(classroom_service, security))
    # Timeline narration (V0-013): the teacher's narrated presentation stream.
    app.include_router(build_timeline_router(timeline_service, security))

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/courses", status_code=201)
    def create_course(
        title: str,
        principal: Principal = Depends(require(Scope.CONTENT_WRITE)),
        course_id: Optional[str] = None,
    ) -> dict[str, str]:
        repository.ensure_institution(principal.institution_id)
        course = repository.create_course(principal.institution_id, title, course_id)
        return {"course_id": course.course_id, "institution_id": course.institution_id}

    @app.get("/courses")
    def list_courses(
        principal: Principal = Depends(require(Scope.CONTENT_READ)),
    ) -> list[dict[str, str]]:
        return [
            {"course_id": course.course_id, "title": course.title}
            for course in repository.list_courses(principal.institution_id)
        ]

    @app.get("/courses/{course_id}/materials")
    def list_materials(
        course_id: str, principal: Principal = Depends(require(Scope.CONTENT_READ))
    ) -> list[dict]:
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
            for material in repository.list_materials(principal.institution_id, course_id)
        ]

    @app.post("/courses/{course_id}/materials", status_code=202)
    async def upload_material(
        course_id: str,
        file: UploadFile = File(...),
        principal: Principal = Depends(require(Scope.CONTENT_WRITE)),
        idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    ) -> dict:
        data = await file.read()
        result = upload_service.upload(
            institution_id=principal.institution_id,
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
    def get_artifact(
        artifact_id: str, principal: Principal = Depends(require(Scope.CONTENT_READ))
    ) -> dict:
        artifact = repository.get_artifact(principal.institution_id, artifact_id)
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
    def extract_artifact(
        artifact_id: str, principal: Principal = Depends(require(Scope.CONTENT_WRITE))
    ) -> dict:
        document = extraction_service.extract(principal.institution_id, artifact_id)
        return document.to_dict()

    @app.post("/artifacts/{artifact_id}/compile")
    def compile_artifact(
        artifact_id: str,
        principal: Principal = Depends(require(Scope.CONTENT_WRITE)),
        mode: Optional[str] = None,
    ) -> dict:
        """Extract, render every slide, and run the fidelity gate (V0-005).

        ``mode`` selects the render mode (V0-019 v5): ``faithful`` (default)
        reproduces the source slide's own layout and draws anything it cannot
        reproduce in the platform look, in place; ``themed`` recovers the author's
        grouping and re-lays the content out in the platform theme.
        """

        return rendering_service.compile(
            principal.institution_id, artifact_id, mode=mode
        ).to_dict()

    @app.get("/artifacts/{artifact_id}/renders/{order}")
    def get_artifact_render(
        artifact_id: str,
        order: int,
        principal: Principal = Depends(require(Scope.CONTENT_READ)),
        mode: Optional[str] = None,
    ) -> Response:
        payload, _scene = rendering_service.render_scene_svg(
            principal.institution_id, artifact_id, order, mode=mode
        )
        return Response(
            content=payload,
            media_type="image/svg+xml",
            # Not versioned by the caller (the URL is per artifact/order/mode) and the
            # bytes change whenever the deck is recompiled, so this must revalidate
            # rather than serve a superseded slide from the browser's cache.
            headers={"Cache-Control": "private, no-cache"},
        )

    @app.get("/renderer")
    def renderer_status(
        principal: Principal = Depends(require(Scope.CONTENT_READ)),
        mode: Optional[str] = None,
    ) -> dict:
        """Capability and circuit-breaker state; drives admission decisions.

        Reports the *default* render mode, the available modes, and the
        capability of the requested one (``faithful`` unless asked otherwise).
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
