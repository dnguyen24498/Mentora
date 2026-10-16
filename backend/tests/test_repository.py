import pytest

from app.common.errors import TenantAccessError
from app.courses.models import CompilerJobStatus


def _upload(repository, course, sha="a" * 64, filename="deck.pptx"):
    return repository.create_upload(
        institution_id=course.institution_id,
        course_id=course.course_id,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        sha256=sha,
        byte_size=123,
        object_key=f"{course.institution_id}/{course.course_id}/{sha}.pptx",
    )


def test_create_upload_sets_pending_job(repository, course):
    record = _upload(repository, course)
    assert record.existing is False
    assert record.job.status == CompilerJobStatus.PENDING.value
    assert record.version.version == 1
    assert record.artifact.sha256 == "a" * 64


def test_duplicate_content_returns_existing_without_new_rows(repository, course):
    first = _upload(repository, course)
    second = _upload(repository, course)
    assert second.existing is True
    assert second.artifact.artifact_id == first.artifact.artifact_id
    assert second.job.job_id == first.job.job_id
    count = repository._conn.execute("SELECT COUNT(*) AS n FROM course_versions").fetchone()["n"]
    assert count == 1


def test_new_content_creates_next_version(repository, course):
    first = _upload(repository, course, sha="a" * 64)
    second = _upload(repository, course, sha="b" * 64)
    assert second.version.version == first.version.version + 1


def test_cross_tenant_course_access_is_rejected(repository, course):
    repository.ensure_institution("inst-2")
    with pytest.raises(TenantAccessError):
        repository.get_course("inst-2", course.course_id)


def test_cross_tenant_artifact_access_is_rejected(repository, course):
    record = _upload(repository, course)
    repository.ensure_institution("inst-2")
    with pytest.raises(TenantAccessError):
        repository.get_artifact("inst-2", record.artifact.artifact_id)


def test_idempotency_key_resolves_to_first_artifact(repository, course):
    record = repository.create_upload(
        institution_id=course.institution_id,
        course_id=course.course_id,
        filename="deck.pptx",
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        sha256="c" * 64,
        byte_size=1,
        object_key="k",
        idempotency_key="req-1",
    )
    found = repository.find_idempotency_artifact(
        course.institution_id, f"course:{course.course_id}:material", "req-1"
    )
    assert found == record.artifact.artifact_id
