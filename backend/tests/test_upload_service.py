import pytest

from app.common.errors import AppError, ErrorCode, StorageError, TenantAccessError
from app.config import Settings
from app.courses.upload_service import UploadService
from app.storage.object_store import ObjectStore
from tests.fixtures import simple_pptx


class _FailingStore(ObjectStore):
    def put(self, key: str, data: bytes) -> str:  # pragma: no cover - trivial
        raise StorageError("simulated storage outage")

    def get(self, key: str) -> bytes:  # pragma: no cover - trivial
        raise StorageError("simulated storage outage")

    def exists(self, key: str) -> bool:  # pragma: no cover - trivial
        return False


def _artifact_count(repository) -> int:
    return repository._conn.execute("SELECT COUNT(*) AS n FROM source_artifacts").fetchone()["n"]


def test_valid_upload_persists_artifact_and_job(upload_service, repository, course, object_store):
    data = simple_pptx("Attention")
    result = upload_service.upload(
        institution_id=course.institution_id,
        course_id=course.course_id,
        filename="deck.pptx",
        data=data,
    )
    assert result.created is True
    assert result.job.status == "PENDING"
    assert result.version.version == 1
    assert result.artifact.byte_size == len(data)
    assert object_store.exists(result.artifact.object_key)


def test_duplicate_upload_is_idempotent(upload_service, repository, course):
    data = simple_pptx()
    first = upload_service.upload(
        institution_id=course.institution_id, course_id=course.course_id, filename="d.pptx", data=data
    )
    second = upload_service.upload(
        institution_id=course.institution_id, course_id=course.course_id, filename="d.pptx", data=data
    )
    assert second.created is False
    assert second.artifact.artifact_id == first.artifact.artifact_id
    assert _artifact_count(repository) == 1


def test_idempotency_key_short_circuits(upload_service, repository, course):
    data = simple_pptx()
    first = upload_service.upload(
        institution_id=course.institution_id,
        course_id=course.course_id,
        filename="d.pptx",
        data=data,
        idempotency_key="req-1",
    )
    second = upload_service.upload(
        institution_id=course.institution_id,
        course_id=course.course_id,
        filename="d.pptx",
        data=data,
        idempotency_key="req-1",
    )
    assert second.artifact.artifact_id == first.artifact.artifact_id
    assert _artifact_count(repository) == 1


def test_oversized_upload_rejected_without_persisting(repository, object_store, course, settings):
    small = Settings(
        database_path=settings.database_path, object_root=settings.object_root, max_upload_bytes=8
    )
    service = UploadService(repository, object_store, small)
    with pytest.raises(AppError) as exc:
        service.upload(
            institution_id=course.institution_id,
            course_id=course.course_id,
            filename="d.pptx",
            data=simple_pptx(),
        )
    assert exc.value.code is ErrorCode.FILE_TOO_LARGE
    assert _artifact_count(repository) == 0


def test_wrong_magic_rejected_without_persisting(upload_service, repository, course):
    with pytest.raises(AppError) as exc:
        upload_service.upload(
            institution_id=course.institution_id,
            course_id=course.course_id,
            filename="d.pptx",
            data=b"not a pptx",
        )
    assert exc.value.code is ErrorCode.INVALID_FILE_TYPE
    assert _artifact_count(repository) == 0


def test_cross_tenant_upload_rejected(upload_service, repository, course):
    with pytest.raises(TenantAccessError):
        upload_service.upload(
            institution_id="inst-2",
            course_id=course.course_id,
            filename="d.pptx",
            data=simple_pptx(),
        )
    assert _artifact_count(repository) == 0


def test_storage_failure_leaves_no_visible_artifact(upload_service, repository, course):
    upload_service._object_store = _FailingStore()
    with pytest.raises(StorageError):
        upload_service.upload(
            institution_id=course.institution_id,
            course_id=course.course_id,
            filename="d.pptx",
            data=simple_pptx(),
        )
    assert _artifact_count(repository) == 0
    assert repository._conn.execute("SELECT COUNT(*) AS n FROM compiler_jobs").fetchone()["n"] == 0
