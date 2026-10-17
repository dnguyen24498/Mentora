"""Class and runtime session plan (V0-009).

Owning the terminology's ``RuntimeSessionPlan`` (owner: Class Management), this
package schedules classes, starts sessions by resolving and pinning the exact
runtime version tuple once, commits the initial durable snapshot with that session,
and authorizes joins against the class enrollment.

Nothing here re-renders, re-parses a source document, or asks for a "latest"
version: a session reads its own pinned plan (``DEC-CONTENT-005``).
"""

from __future__ import annotations

from app.classroom.catalog import (
    BASELINE_POLICY_VERSION,
    SUPPORTED_CTF_SCHEMA_VERSIONS,
    BaselineRuntimeCatalog,
    RuntimeCatalog,
    RuntimeDefaults,
    capability_version,
)
from app.classroom.errors import (
    ISSUE_COMMIT_CONFLICT,
    ISSUE_CONTENT_DIGEST_MISMATCH,
    ISSUE_INCOMPATIBLE_CONTENT,
    ISSUE_INCOMPATIBLE_INDEX,
    ISSUE_NOT_ENROLLED,
    ISSUE_NOT_STARTED,
    ISSUE_SNAPSHOT_INVALID,
    ISSUE_STALE_EPOCH,
    ISSUE_TOKEN_EXPIRED,
    ISSUE_TOKEN_REVOKED,
    ISSUE_TOKEN_UNKNOWN,
    ISSUE_VERSION_NOT_PUBLISHED,
    ISSUE_WRONG_STATE,
    ClassStartError,
    JoinDeniedError,
    SnapshotIntegrityError,
)
from app.classroom.models import (
    BOOTSTRAP_SCOPE_SUBSCRIBE,
    BOOTSTRAP_TOKEN_SCOPES,
    BOOTSTRAP_TOKEN_TTL_SECONDS,
    CLASSROOM_STATE_ACTIVE,
    CLASSROOM_STATE_SCHEDULED,
    CLASS_START_STAGE_PREPARING,
    INITIAL_ACTOR_EPOCH,
    INITIAL_EVENT_SEQUENCE,
    INITIAL_STATE_VERSION,
    SNAPSHOT_SCHEMA_VERSION,
    BootstrapToken,
    Class,
    ClassroomSession,
    ClassroomState,
    Enrollment,
    IssuedBootstrapToken,
    RuntimeSessionPlan,
    SessionSnapshot,
)
from app.classroom.repository import ClassRepository, CommitConflict
from app.classroom.router import build_class_router
from app.classroom.service import ClassroomService, SessionStartResult
from app.classroom.snapshot import (
    REQUIRED_REGIONS,
    canonical_json,
    first_lesson_position,
    initial_snapshot,
    snapshot_checksum,
    validate_snapshot,
)
from app.classroom.telemetry import ClassroomMetrics, ClassroomTelemetry

__all__ = [
    "BASELINE_POLICY_VERSION",
    "BOOTSTRAP_SCOPE_SUBSCRIBE",
    "BOOTSTRAP_TOKEN_SCOPES",
    "BOOTSTRAP_TOKEN_TTL_SECONDS",
    "CLASSROOM_STATE_ACTIVE",
    "CLASSROOM_STATE_SCHEDULED",
    "CLASS_START_STAGE_PREPARING",
    "INITIAL_ACTOR_EPOCH",
    "INITIAL_EVENT_SEQUENCE",
    "INITIAL_STATE_VERSION",
    "ISSUE_COMMIT_CONFLICT",
    "ISSUE_CONTENT_DIGEST_MISMATCH",
    "ISSUE_INCOMPATIBLE_CONTENT",
    "ISSUE_INCOMPATIBLE_INDEX",
    "ISSUE_NOT_ENROLLED",
    "ISSUE_NOT_STARTED",
    "ISSUE_SNAPSHOT_INVALID",
    "ISSUE_STALE_EPOCH",
    "ISSUE_TOKEN_EXPIRED",
    "ISSUE_TOKEN_REVOKED",
    "ISSUE_TOKEN_UNKNOWN",
    "ISSUE_VERSION_NOT_PUBLISHED",
    "ISSUE_WRONG_STATE",
    "REQUIRED_REGIONS",
    "SNAPSHOT_SCHEMA_VERSION",
    "SUPPORTED_CTF_SCHEMA_VERSIONS",
    "BaselineRuntimeCatalog",
    "BootstrapToken",
    "Class",
    "ClassRepository",
    "ClassStartError",
    "ClassroomMetrics",
    "ClassroomService",
    "ClassroomSession",
    "ClassroomState",
    "ClassroomTelemetry",
    "CommitConflict",
    "Enrollment",
    "IssuedBootstrapToken",
    "JoinDeniedError",
    "RuntimeCatalog",
    "RuntimeDefaults",
    "RuntimeSessionPlan",
    "SessionSnapshot",
    "SessionStartResult",
    "SnapshotIntegrityError",
    "build_class_router",
    "canonical_json",
    "capability_version",
    "first_lesson_position",
    "initial_snapshot",
    "snapshot_checksum",
    "validate_snapshot",
]
