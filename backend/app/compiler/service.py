"""Extraction orchestration: read artifact bytes -> Content IR -> job status."""

from __future__ import annotations

from app.compiler.extractors.pptx import PptxExtractor
from app.compiler.models.ir import ContentIRDocument
from app.courses.models import CompilerJobStatus
from app.courses.repository import CourseRepository
from app.storage.object_store import ObjectStore


class ExtractionService:
    def __init__(
        self,
        repository: CourseRepository,
        object_store: ObjectStore,
        extractor: PptxExtractor,
    ) -> None:
        self._repository = repository
        self._object_store = object_store
        self._extractor = extractor

    def extract(self, institution_id: str, artifact_id: str) -> ContentIRDocument:
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
        job = self._repository.get_job_for_artifact(institution_id, artifact_id)
        self._repository.set_job_status(institution_id, job.job_id, CompilerJobStatus.EXTRACTED)
        return document
