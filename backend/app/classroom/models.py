"""Class, RuntimeSessionPlan and ClassroomSession models (V0-009).

``docs/architecture/03_DOMAIN_OWNERSHIP_AND_VERSIONING.md`` names the aggregates
``Class/RuntimeSessionPlan/ClassroomSession`` and ``Student/Enrollment/Progress``,
and fixes the runtime tuple: *"Course, CTF, content package, lesson, optional
teaching graph, assessment, knowledge index, policy, model-routing configuration,
and home region are explicit versions. ``latest`` is forbidden."*

The two facts this module exists to keep immutable:

* :class:`RuntimeSessionPlan` is the **resolved** tuple — every member is a value,
  never a pointer that a later publication could move. It is written once, by the
  same transaction that creates the session, and has no update path.
* :class:`ClassroomSession` carries the initial authoritative state
  (``docs/state-machines/CLASSROOM_SESSION_STATE_MACHINE.md``: *"Pin versions and
  epoch in PREPARING"*). ``PREPARING`` itself is in-flight only and is never
  stored, so an interrupted start is indistinguishable from one that never began.

Everything is tenant-owned via ``institution_id``.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

#: ``docs/state-machines/CLASSROOM_SESSION_STATE_MACHINE.md``:
#: ``SCHEDULED -> PREPARING -> ACTIVE <-> DEGRADED -> RECOVERING -> ACTIVE/DEGRADED
#: -> ENDING -> COMPLETED; FAILED only when no safe continuation.``
#: V0-009 writes only ``SCHEDULED -> ACTIVE`` (the initial state); the transitions
#: after ``ACTIVE`` belong to the Classroom Actor (V0-010/V0-016), which is why
#: they are named here but never written.
CLASSROOM_STATE_SCHEDULED = "SCHEDULED"
CLASSROOM_STATE_ACTIVE = "ACTIVE"
CLASSROOM_STATE_DEGRADED = "DEGRADED"
CLASSROOM_STATE_RECOVERING = "RECOVERING"
CLASSROOM_STATE_ENDING = "ENDING"
CLASSROOM_STATE_COMPLETED = "COMPLETED"
CLASSROOM_STATE_FAILED = "FAILED"

#: The class/session state vocabulary (one machine for both rows). Only
#: ``SCHEDULED`` and ``ACTIVE`` are written by V0-009; the schema's ``CHECK`` and this
#: tuple both name the full machine so the later transitions do not need a migration.
CLASSROOM_STATES: tuple[str, ...] = (
    CLASSROOM_STATE_SCHEDULED,
    CLASSROOM_STATE_DEGRADED,
    CLASSROOM_STATE_RECOVERING,
    CLASSROOM_STATE_ACTIVE,
    CLASSROOM_STATE_ENDING,
    CLASSROOM_STATE_COMPLETED,
    CLASSROOM_STATE_FAILED,
)

#: The in-flight stage between the two durable states. Never persisted: the
#: commit transaction is the only writer, so a crash here leaves ``SCHEDULED``.
CLASS_START_STAGE_PREPARING = "PREPARING"

#: ``docs/data/OUTBOX_SNAPSHOT_AND_RETENTION.md`` / ``DEC-DATA-004``: a snapshot
#: is validated before it is used, so it has to say which schema it is.
SNAPSHOT_SCHEMA_VERSION = "runtime-snapshot@1"

#: Initial authoritative counters. ``actor_epoch`` starts at 1 and an epoch is
#: never reused; moving ownership across an actor failure is V1-002's, and
#: ``DEC-RUNTIME-007`` (stale epoch cannot mutate/authorize) is honoured from the
#: first value on by binding tokens to it.
INITIAL_ACTOR_EPOCH = 1
INITIAL_STATE_VERSION = 1
INITIAL_EVENT_SEQUENCE = 1

#: ``docs/security/IDENTITY_AUTHORIZATION_AND_TOKENS.md``: *"Normal student media
#: permission is subscribe-only."* The bootstrap token is a *join* credential, so
#: it never carries publish_audio — that is the floor token's (``DEC-TURN-008``,
#: out of scope here).
BOOTSTRAP_SCOPE_SUBSCRIBE = "subscribe"
BOOTSTRAP_TOKEN_SCOPES: tuple[str, ...] = (BOOTSTRAP_SCOPE_SUBSCRIBE,)
#: Bounded lifetime (``DEC-RELIABILITY-001``): short-lived, so a leaked token is a
#: small window, and every token has a terminal path (expiry or revoke).
BOOTSTRAP_TOKEN_TTL_SECONDS = 300


class ClassroomState(str, Enum):
    """The class/session state machine (one vocabulary for both rows)."""

    SCHEDULED = CLASSROOM_STATE_SCHEDULED
    ACTIVE = CLASSROOM_STATE_ACTIVE
    DEGRADED = CLASSROOM_STATE_DEGRADED
    RECOVERING = CLASSROOM_STATE_RECOVERING
    ENDING = CLASSROOM_STATE_ENDING
    COMPLETED = CLASSROOM_STATE_COMPLETED
    FAILED = CLASSROOM_STATE_FAILED


@dataclass(frozen=True)
class Class:
    """A scheduled teaching occurrence, before and after its start.

    ``version_id`` is the version the teacher pinned when scheduling, if any. A
    ``None`` means *resolve the course's current published version once, at start*
    — a single recorded decision, never a runtime ``latest`` lookup.
    """

    class_id: str
    institution_id: str
    course_id: str
    title: str
    version_id: Optional[str]
    scheduled_for: Optional[str]
    state: str
    created_at: str
    started_at: Optional[str]

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Class":
        return cls(
            class_id=row["class_id"],
            institution_id=row["institution_id"],
            course_id=row["course_id"],
            title=row["title"],
            version_id=row["version_id"],
            scheduled_for=row["scheduled_for"],
            state=row["state"],
            created_at=row["created_at"],
            started_at=row["started_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "class_id": self.class_id,
            "institution_id": self.institution_id,
            "course_id": self.course_id,
            "title": self.title,
            "version_id": self.version_id,
            "scheduled_for": self.scheduled_for,
            "state": self.state,
            "created_at": self.created_at,
            "started_at": self.started_at,
        }


@dataclass(frozen=True)
class Enrollment:
    """One student's authorization to join one class."""

    enrollment_id: str
    institution_id: str
    class_id: str
    student_id: str
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Enrollment":
        return cls(
            enrollment_id=row["enrollment_id"],
            institution_id=row["institution_id"],
            class_id=row["class_id"],
            student_id=row["student_id"],
            created_at=row["created_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enrollment_id": self.enrollment_id,
            "institution_id": self.institution_id,
            "class_id": self.class_id,
            "student_id": self.student_id,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class RuntimeSessionPlan:
    """The class-specific immutable tuple a session runs on.

    ``capabilities`` is the warmed capability set (the renderer identity the
    session admitted through); the version members are what a later reader must
    agree on, and none of them is a pointer to "current".
    """

    session_plan_id: str
    institution_id: str
    class_id: str
    course_id: str
    version_id: str
    course_version: int
    publication_id: str
    package_id: str
    content_package_version: str
    content_digest: str
    lesson_plan_version: str
    knowledge_index_version: str
    index_version_id: str
    index_source_digest: str
    teaching_graph_version: Optional[str]
    assessment_version: Optional[str]
    model_routing_version: Optional[str]
    policy_version: str
    capability_version: str
    capabilities: dict[str, Any]
    region: str
    created_at: str

    @property
    def versions(self) -> dict[str, Any]:
        """The pinned runtime tuple (the members ``03_…`` enumerates)."""

        return {
            "course_id": self.course_id,
            "course_version": self.course_version,
            "version_id": self.version_id,
            "publication_id": self.publication_id,
            "package_id": self.package_id,
            "content_package_version": self.content_package_version,
            "content_digest": self.content_digest,
            "lesson_plan_version": self.lesson_plan_version,
            "knowledge_index_version": self.knowledge_index_version,
            "index_version_id": self.index_version_id,
            "index_source_digest": self.index_source_digest,
            "teaching_graph_version": self.teaching_graph_version,
            "assessment_version": self.assessment_version,
            "model_routing_version": self.model_routing_version,
            "policy_version": self.policy_version,
            "capability_version": self.capability_version,
            "region": self.region,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "RuntimeSessionPlan":
        return cls(
            session_plan_id=row["session_plan_id"],
            institution_id=row["institution_id"],
            class_id=row["class_id"],
            course_id=row["course_id"],
            version_id=row["version_id"],
            course_version=int(row["course_version"]),
            publication_id=row["publication_id"],
            package_id=row["package_id"],
            content_package_version=row["content_package_version"],
            content_digest=row["content_digest"],
            lesson_plan_version=row["lesson_plan_version"],
            knowledge_index_version=row["knowledge_index_version"],
            index_version_id=row["index_version_id"],
            index_source_digest=row["index_source_digest"],
            teaching_graph_version=row["teaching_graph_version"],
            assessment_version=row["assessment_version"],
            model_routing_version=row["model_routing_version"],
            policy_version=row["policy_version"],
            capability_version=row["capability_version"],
            capabilities=json.loads(row["capabilities"]),
            region=row["region"],
            created_at=row["created_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_plan_id": self.session_plan_id,
            "class_id": self.class_id,
            "versions": self.versions,
            "capabilities": self.capabilities,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class ClassroomSession:
    """The durable session created at start, with its initial state."""

    session_id: str
    institution_id: str
    class_id: str
    course_id: str
    session_plan_id: str
    state: str
    actor_epoch: int
    state_version: int
    event_sequence: int
    snapshot_id: Optional[str]
    created_at: str
    started_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ClassroomSession":
        return cls(
            session_id=row["session_id"],
            institution_id=row["institution_id"],
            class_id=row["class_id"],
            course_id=row["course_id"],
            session_plan_id=row["session_plan_id"],
            state=row["state"],
            actor_epoch=int(row["actor_epoch"]),
            state_version=int(row["state_version"]),
            event_sequence=int(row["event_sequence"]),
            snapshot_id=row["snapshot_id"],
            created_at=row["created_at"],
            started_at=row["started_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "class_id": self.class_id,
            "course_id": self.course_id,
            "session_plan_id": self.session_plan_id,
            "state": self.state,
            "actor_epoch": self.actor_epoch,
            "state_version": self.state_version,
            "event_sequence": self.event_sequence,
            "snapshot_id": self.snapshot_id,
            "created_at": self.created_at,
            "started_at": self.started_at,
        }


@dataclass(frozen=True)
class SessionSnapshot:
    """A durable snapshot document plus the checksum that validates it."""

    snapshot_id: str
    institution_id: str
    session_id: str
    class_id: str
    schema_version: str
    state: str
    state_version: int
    event_sequence: int
    actor_epoch: int
    document: dict[str, Any]
    checksum: str
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "SessionSnapshot":
        return cls(
            snapshot_id=row["snapshot_id"],
            institution_id=row["institution_id"],
            session_id=row["session_id"],
            class_id=row["class_id"],
            schema_version=row["schema_version"],
            state=row["state"],
            state_version=int(row["state_version"]),
            event_sequence=int(row["event_sequence"]),
            actor_epoch=int(row["actor_epoch"]),
            document=json.loads(row["document"]),
            checksum=row["checksum"],
            created_at=row["created_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "class_id": self.class_id,
            "session_id": self.session_id,
            "schema_version": self.schema_version,
            "state": self.state,
            "state_version": self.state_version,
            "event_sequence": self.event_sequence,
            "actor_epoch": self.actor_epoch,
            "checksum": self.checksum,
            "created_at": self.created_at,
            "document": self.document,
        }


@dataclass(frozen=True)
class BootstrapToken:
    """A stored join credential. The raw token is **not** in this record.

    Only ``token_sha256`` is persisted: a token is a credential, so reading the
    database must not yield a usable one.
    """

    token_sha256: str
    institution_id: str
    class_id: str
    session_id: str
    student_id: str
    actor_epoch: int
    nonce: str
    scopes: tuple[str, ...]
    issued_at: str
    expires_at: str
    revoked_at: Optional[str]

    @property
    def revoked(self) -> bool:
        return self.revoked_at is not None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "BootstrapToken":
        return cls(
            token_sha256=row["token_sha256"],
            institution_id=row["institution_id"],
            class_id=row["class_id"],
            session_id=row["session_id"],
            student_id=row["student_id"],
            actor_epoch=int(row["actor_epoch"]),
            nonce=row["nonce"],
            scopes=tuple(str(scope) for scope in json.loads(row["scopes"])),
            issued_at=row["issued_at"],
            expires_at=row["expires_at"],
            revoked_at=row["revoked_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "class_id": self.class_id,
            "session_id": self.session_id,
            "student_id": self.student_id,
            "actor_epoch": self.actor_epoch,
            "nonce": self.nonce,
            "scopes": list(self.scopes),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True)
class IssuedBootstrapToken:
    """The one-time view of a freshly issued token: raw value plus its record."""

    token: str
    record: BootstrapToken

    def to_dict(self) -> dict[str, Any]:
        return {"token": self.token, **self.record.to_dict()}


__all__ = [
    "BOOTSTRAP_SCOPE_SUBSCRIBE",
    "BOOTSTRAP_TOKEN_SCOPES",
    "BOOTSTRAP_TOKEN_TTL_SECONDS",
    "CLASSROOM_STATE_ACTIVE",
    "CLASSROOM_STATE_COMPLETED",
    "CLASSROOM_STATE_DEGRADED",
    "CLASSROOM_STATE_ENDING",
    "CLASSROOM_STATE_FAILED",
    "CLASSROOM_STATE_RECOVERING",
    "CLASSROOM_STATE_SCHEDULED",
    "CLASSROOM_STATES",
    "CLASS_START_STAGE_PREPARING",
    "INITIAL_ACTOR_EPOCH",
    "INITIAL_EVENT_SEQUENCE",
    "INITIAL_STATE_VERSION",
    "SNAPSHOT_SCHEMA_VERSION",
    "BootstrapToken",
    "Class",
    "ClassroomSession",
    "ClassroomState",
    "Enrollment",
    "IssuedBootstrapToken",
    "RuntimeSessionPlan",
    "SessionSnapshot",
]
