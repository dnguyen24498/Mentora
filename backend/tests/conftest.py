from __future__ import annotations

import pytest

from app.compiler.extractors.pptx import PptxExtractor
from app.compiler.render_service import RenderingService
from app.compiler.renderers.base import RenderConfig
from app.compiler.renderers.factory import MODE_FAITHFUL, MODE_THEMED
from app.compiler.renderers.structural import StructuralSvgRenderer
from app.compiler.renderers.themed import ThemedSvgRenderer
from app.compiler.service import ExtractionService
from app.config import Settings
from app.courses.repository import CourseRepository
from app.courses.upload_service import UploadService
from app.db.database import connect, init_db
from app.storage.object_store import LocalObjectStore


@pytest.fixture
def settings(tmp_path) -> Settings:
    s = Settings(database_path=tmp_path / "mentora.db", object_root=tmp_path / "objects")
    init_db(s.database_path)
    return s


@pytest.fixture
def conn(settings):
    connection = connect(settings.database_path)
    yield connection
    connection.close()


@pytest.fixture
def repository(conn) -> CourseRepository:
    return CourseRepository(conn)


@pytest.fixture
def object_store(settings) -> LocalObjectStore:
    return LocalObjectStore(settings.object_root)


@pytest.fixture
def upload_service(repository, object_store, settings) -> UploadService:
    return UploadService(repository, object_store, settings)


@pytest.fixture
def extractor(settings) -> PptxExtractor:
    return PptxExtractor(
        max_entries=settings.max_archive_entries,
        max_uncompressed_bytes=settings.max_uncompressed_bytes,
    )


@pytest.fixture
def extraction_service(repository, object_store, extractor) -> ExtractionService:
    return ExtractionService(repository, object_store, extractor)


@pytest.fixture
def render_config() -> RenderConfig:
    return RenderConfig()


@pytest.fixture
def renderer(object_store, render_config) -> StructuralSvgRenderer:
    """The *faithful* (structural) renderer — the application default since v5.

    ``tests/test_renderers.py`` and ``tests/test_renderer_fidelity.py`` assert
    structural-renderer behaviour (font substitution, the structural ceiling); the
    renderer the application uses by default is :func:`default_renderer`, which is
    this same mode (V0-019 v5).
    """

    return StructuralSvgRenderer(object_store, render_config)


@pytest.fixture
def faithful_renderer(renderer) -> StructuralSvgRenderer:
    return renderer


@pytest.fixture
def themed_renderer(object_store, render_config) -> ThemedSvgRenderer:
    return ThemedSvgRenderer(object_store, render_config)


@pytest.fixture
def default_renderer(renderer) -> StructuralSvgRenderer:
    """The renderer the application uses by default (V0-019 v5: faithful mode)."""

    return renderer


@pytest.fixture
def rendering_service(
    repository, object_store, extractor, renderer, render_config
) -> RenderingService:
    return RenderingService(
        repository, object_store, extractor, renderer, config=render_config
    )


@pytest.fixture
def default_rendering_service(
    repository, object_store, extractor, themed_renderer, render_config
) -> RenderingService:
    """A rendering service wired like ``create_app``: themed by default."""

    return RenderingService(
        repository,
        object_store,
        extractor,
        themed_renderer,
        renderers={
            MODE_THEMED: themed_renderer,
            MODE_FAITHFUL: StructuralSvgRenderer(object_store, render_config),
        },
        default_mode=MODE_THEMED,
        config=render_config,
    )


@pytest.fixture
def stored_artifact(upload_service, course):
    """Upload one small deck and return ``(artifact, course)``."""

    from tests.fixtures import simple_pptx

    result = upload_service.upload(
        institution_id="inst-1",
        course_id=course.course_id,
        filename="deck.pptx",
        data=simple_pptx(),
    )
    return result.artifact, course


@pytest.fixture
def course(repository):
    repository.ensure_institution("inst-1")
    return repository.create_course("inst-1", "Intro to AI")
