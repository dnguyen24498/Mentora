"""Tenant-scoped repository over the durable store.

All reads/writes go through this class so the tenant boundary is enforced in one
place (``docs/architecture/17_SECURITY_PRIVACY_AND_GOVERNANCE.md``): a request
for another institution's course is rejected rather than silently returning
``None``.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.common.errors import NotFoundError, TenantAccessError
from app.courses.models import (
    CompilerJob,
    CompilerJobStatus,
    Course,
    CourseVersion,
    CourseVersionStatus,
    Material,
    SourceArtifact,
    UploadRecord,
)
from app.db.database import transaction


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


class CourseRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # -- institutions / courses -------------------------------------------------
    def create_institution(self, institution_id: str, name: str) -> None:
        with transaction(self._conn):
            self._conn.execute(
                "INSERT INTO institutions (institution_id, name, created_at) VALUES (?, ?, ?)",
                (institution_id, name, _now()),
            )

    def ensure_institution(self, institution_id: str, name: Optional[str] = None) -> None:
        """Idempotently create the tenant row (dev/bootstrap convenience)."""

        with transaction(self._conn):
            self._conn.execute(
                "INSERT OR IGNORE INTO institutions (institution_id, name, created_at) VALUES (?, ?, ?)",
                (institution_id, name or institution_id, _now()),
            )


    def create_course(self, institution_id: str, title: str, course_id: Optional[str] = None) -> Course:
        course_id = course_id or _new_id()
        with transaction(self._conn):
            self._conn.execute(
                "INSERT INTO courses (course_id, institution_id, title, created_at) VALUES (?, ?, ?, ?)",
                (course_id, institution_id, title, _now()),
            )
        return self.get_course(institution_id, course_id)

    def get_course(self, institution_id: str, course_id: str) -> Course:
        row = self._conn.execute(
            "SELECT * FROM courses WHERE course_id = ?", (course_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"course {course_id!r} not found")
        if row["institution_id"] != institution_id:
            raise TenantAccessError("course belongs to another institution")
        return Course.from_row(row)

    def list_courses(self, institution_id: str) -> list[Course]:
        rows = self._conn.execute(
            "SELECT * FROM courses WHERE institution_id = ? ORDER BY created_at DESC",
            (institution_id,),
        ).fetchall()
        return [Course.from_row(row) for row in rows]

    # -- versions ---------------------------------------------------------------
    def latest_version(self, institution_id: str, course_id: str) -> Optional[CourseVersion]:
        self.get_course(institution_id, course_id)
        row = self._conn.execute(
            "SELECT * FROM course_versions WHERE institution_id = ? AND course_id = ? "
            "ORDER BY version DESC LIMIT 1",
            (institution_id, course_id),
        ).fetchone()
        return CourseVersion.from_row(row) if row else None

    def get_version(self, institution_id: str, version_id: str) -> CourseVersion:
        row = self._conn.execute(
            "SELECT * FROM course_versions WHERE version_id = ?", (version_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"course version {version_id!r} not found")
        if row["institution_id"] != institution_id:
            raise TenantAccessError("course version belongs to another institution")
        return CourseVersion.from_row(row)

    # -- source artifacts / jobs ------------------------------------------------
    def find_artifact_by_sha(
        self, institution_id: str, course_id: str, sha256: str
    ) -> Optional[SourceArtifact]:
        row = self._conn.execute(
            "SELECT * FROM source_artifacts WHERE institution_id = ? AND course_id = ? AND sha256 = ?",
            (institution_id, course_id, sha256),
        ).fetchone()
        return SourceArtifact.from_row(row) if row else None

    def list_materials(self, institution_id: str, course_id: str) -> list[Material]:
        """Every source file of a course, newest first, with its job status.

        Columns are aliased because ``course_versions`` and ``source_artifacts``
        share names (``course_id``, ``institution_id``, ``version_id``, ...).
        """

        self.get_course(institution_id, course_id)
        rows = self._conn.execute(
            "SELECT a.artifact_id    AS artifact_id,"
            "       a.institution_id AS institution_id,"
            "       a.course_id      AS course_id,"
            "       a.version_id     AS version_id,"
            "       a.filename       AS filename,"
            "       a.media_type     AS media_type,"
            "       a.sha256         AS sha256,"
            "       a.byte_size      AS byte_size,"
            "       a.object_key     AS object_key,"
            "       a.created_at     AS created_at,"
            "       v.version        AS version_number,"
            "       j.job_id         AS job_id,"
            "       j.status         AS job_status,"
            "       j.updated_at     AS updated_at "
            "FROM source_artifacts a "
            "JOIN course_versions v ON v.version_id = a.version_id "
            "JOIN compiler_jobs j ON j.artifact_id = a.artifact_id "
            "WHERE a.institution_id = ? AND a.course_id = ? "
            "ORDER BY a.created_at DESC, a.artifact_id DESC",
            (institution_id, course_id),
        ).fetchall()
        return [Material.from_row(row) for row in rows]

    def get_artifact(self, institution_id: str, artifact_id: str) -> SourceArtifact:
        row = self._conn.execute(
            "SELECT * FROM source_artifacts WHERE artifact_id = ?", (artifact_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"source artifact {artifact_id!r} not found")
        if row["institution_id"] != institution_id:
            raise TenantAccessError("source artifact belongs to another institution")
        return SourceArtifact.from_row(row)

    def get_job_for_artifact(self, institution_id: str, artifact_id: str) -> CompilerJob:
        row = self._conn.execute(
            "SELECT * FROM compiler_jobs WHERE institution_id = ? AND artifact_id = ?",
            (institution_id, artifact_id),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"no compiler job for artifact {artifact_id!r}")
        return CompilerJob.from_row(row)

    def set_job_status(self, institution_id: str, job_id: str, status: CompilerJobStatus) -> CompilerJob:
        with transaction(self._conn):
            cur = self._conn.execute(
                "UPDATE compiler_jobs SET status = ?, updated_at = ? WHERE job_id = ? AND institution_id = ?",
                (status.value, _now(), job_id, institution_id),
            )
            if cur.rowcount == 0:
                raise NotFoundError(f"compiler job {job_id!r} not found")
        row = self._conn.execute("SELECT * FROM compiler_jobs WHERE job_id = ?", (job_id,)).fetchone()
        return CompilerJob.from_row(row)

    def find_idempotency_artifact(
        self, institution_id: str, scope: str, idempotency_key: str
    ) -> Optional[str]:
        row = self._conn.execute(
            "SELECT artifact_id FROM idempotency_records "
            "WHERE institution_id = ? AND scope = ? AND idempotency_key = ?",
            (institution_id, scope, idempotency_key),
        ).fetchone()
        return row["artifact_id"] if row else None

    def create_upload(
        self,
        *,
        institution_id: str,
        course_id: str,
        filename: str,
        media_type: str,
        sha256: str,
        byte_size: int,
        object_key: str,
        idempotency_key: Optional[str] = None,
    ) -> UploadRecord:
        """Persist one version + source artifact + compiler job atomically.

        Idempotency is enforced two ways:
        * content dedupe on ``(institution_id, course_id, sha256)``;
        * an optional ``idempotency_key`` mapped to the first artifact.

        A duplicate returns the existing rows with ``existing=True`` and writes
        nothing new, so retries never create a second artifact or job.
        """

        # Authorize the tenant/course scope before writing anything.
        self.get_course(institution_id, course_id)

        existing = self._resolve_existing(institution_id, course_id, sha256, idempotency_key)
        if existing is not None:
            return existing

        now = _now()
        version_id = _new_id()
        artifact_id = _new_id()
        job_id = _new_id()
        scope = f"course:{course_id}:material"

        with transaction(self._conn):
            row = self._conn.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS next FROM course_versions "
                "WHERE institution_id = ? AND course_id = ?",
                (institution_id, course_id),
            ).fetchone()
            next_version = int(row["next"])

            self._conn.execute(
                "INSERT INTO course_versions "
                "(version_id, course_id, institution_id, version, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (version_id, course_id, institution_id, next_version, CourseVersionStatus.DRAFT.value, now),
            )
            self._conn.execute(
                "INSERT INTO source_artifacts "
                "(artifact_id, institution_id, course_id, version_id, filename, media_type, "
                " sha256, byte_size, object_key, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    artifact_id,
                    institution_id,
                    course_id,
                    version_id,
                    filename,
                    media_type,
                    sha256,
                    byte_size,
                    object_key,
                    now,
                ),
            )
            self._conn.execute(
                "INSERT INTO compiler_jobs "
                "(job_id, institution_id, artifact_id, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (job_id, institution_id, artifact_id, CompilerJobStatus.PENDING.value, now, now),
            )
            if idempotency_key:
                self._conn.execute(
                    "INSERT OR IGNORE INTO idempotency_records "
                    "(institution_id, scope, idempotency_key, artifact_id, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (institution_id, scope, idempotency_key, artifact_id, now),
                )

        return UploadRecord(
            version=self.get_version(institution_id, version_id),
            artifact=self.get_artifact(institution_id, artifact_id),
            job=self.get_job_for_artifact(institution_id, artifact_id),
            existing=False,
        )

    def _resolve_existing(
        self,
        institution_id: str,
        course_id: str,
        sha256: str,
        idempotency_key: Optional[str],
    ) -> Optional[UploadRecord]:
        artifact: Optional[SourceArtifact] = None
        if idempotency_key:
            artifact_id = self.find_idempotency_artifact(
                institution_id, f"course:{course_id}:material", idempotency_key
            )
            if artifact_id:
                artifact = self.get_artifact(institution_id, artifact_id)
        if artifact is None:
            artifact = self.find_artifact_by_sha(institution_id, course_id, sha256)
        if artifact is None:
            return None
        return UploadRecord(
            version=self.get_version(institution_id, artifact.version_id),
            artifact=artifact,
            job=self.get_job_for_artifact(institution_id, artifact.artifact_id),
            existing=True,
        )
