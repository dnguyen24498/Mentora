"""Course-domain models (DDD aggregate: Course / CourseVersion / SourceArtifact / CompilerJob).

Ownership: ``docs/architecture/03_DOMAIN_OWNERSHIP_AND_VERSIONING.md``.
Every model is tenant-owned via ``institution_id``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum


class CourseVersionStatus(str, Enum):
    DRAFT = "DRAFT"
    PROCESSING = "PROCESSING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class CompilerJobStatus(str, Enum):
    PENDING = "PENDING"
    EXTRACTED = "EXTRACTED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class Course:
    course_id: str
    institution_id: str
    title: str
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Course":
        return cls(row["course_id"], row["institution_id"], row["title"], row["created_at"])


@dataclass(frozen=True)
class CourseVersion:
    version_id: str
    course_id: str
    institution_id: str
    version: int
    status: str
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "CourseVersion":
        return cls(
            row["version_id"],
            row["course_id"],
            row["institution_id"],
            row["version"],
            row["status"],
            row["created_at"],
        )


@dataclass(frozen=True)
class SourceArtifact:
    artifact_id: str
    institution_id: str
    course_id: str
    version_id: str
    filename: str
    media_type: str
    sha256: str
    byte_size: int
    object_key: str
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "SourceArtifact":
        return cls(
            row["artifact_id"],
            row["institution_id"],
            row["course_id"],
            row["version_id"],
            row["filename"],
            row["media_type"],
            row["sha256"],
            row["byte_size"],
            row["object_key"],
            row["created_at"],
        )


@dataclass(frozen=True)
class CompilerJob:
    job_id: str
    institution_id: str
    artifact_id: str
    status: str
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "CompilerJob":
        return cls(
            row["job_id"],
            row["institution_id"],
            row["artifact_id"],
            row["status"],
            row["created_at"],
            row["updated_at"],
        )


@dataclass(frozen=True)
class UploadRecord:
    """Result of persisting an upload: version + artifact + job created atomically."""

    version: CourseVersion
    artifact: SourceArtifact
    job: CompilerJob
    existing: bool = False


@dataclass(frozen=True)
class Material:
    """An uploaded source file, joined with its course version and compiler job.

    Read model for listing what a course already contains (``GET
    /courses/{courseId}/materials``); it never writes.
    """

    artifact: SourceArtifact
    version_number: int
    job_id: str
    job_status: str
    updated_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Material":
        return cls(
            artifact=SourceArtifact.from_row(row),
            version_number=row["version_number"],
            job_id=row["job_id"],
            job_status=row["job_status"],
            updated_at=row["updated_at"],
        )
