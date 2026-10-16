"""Upload orchestration: validate -> store -> persist artifact + job idempotently."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

from app.config import Settings
from app.courses.models import CompilerJob, CourseVersion, SourceArtifact
from app.courses.repository import CourseRepository
from app.security.validation import validate_upload
from app.storage.object_store import ObjectStore


@dataclass(frozen=True)
class UploadResult:
    version: CourseVersion
    artifact: SourceArtifact
    job: CompilerJob
    created: bool


def _scope(course_id: str) -> str:
    return f"course:{course_id}:material"


class UploadService:
    def __init__(
        self,
        repository: CourseRepository,
        object_store: ObjectStore,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._object_store = object_store
        self._settings = settings

    def upload(
        self,
        *,
        institution_id: str,
        course_id: str,
        filename: str,
        data: bytes,
        idempotency_key: Optional[str] = None,
    ) -> UploadResult:
        # 1. Authorize tenant/course scope before any side effect.
        self._repository.get_course(institution_id, course_id)

        # 2. Explicit idempotency key short-circuits a retried request.
        if idempotency_key:
            existing_id = self._repository.find_idempotency_artifact(
                institution_id, _scope(course_id), idempotency_key
            )
            if existing_id:
                return self._result(self._repository.get_artifact(institution_id, existing_id))

        # 3. Deterministic validation (size, extension, magic bytes).
        validated = validate_upload(filename, data, max_bytes=self._settings.max_upload_bytes)

        # 4. Content dedupe: identical bytes in a course resolve to one artifact.
        sha256 = hashlib.sha256(data).hexdigest()
        existing = self._repository.find_artifact_by_sha(institution_id, course_id, sha256)
        if existing is not None:
            return self._result(existing)

        # 5. Persist the immutable binary first (atomic, content-addressed). If the
        #    store fails, no durable row is written, so nothing corrupt is visible.
        object_key = f"{institution_id}/{course_id}/{sha256}.pptx"
        self._object_store.put(object_key, data)

        # 6. Persist version + artifact + job atomically.
        record = self._repository.create_upload(
            institution_id=institution_id,
            course_id=course_id,
            filename=validated.filename,
            media_type=validated.media_type,
            sha256=sha256,
            byte_size=validated.size,
            object_key=object_key,
            idempotency_key=idempotency_key,
        )
        return UploadResult(record.version, record.artifact, record.job, created=not record.existing)

    def _result(self, artifact: SourceArtifact) -> UploadResult:
        version = self._repository.get_version(artifact.institution_id, artifact.version_id)
        job = self._repository.get_job_for_artifact(artifact.institution_id, artifact.artifact_id)
        return UploadResult(version, artifact, job, created=False)
