"""Classified failures of class start, join authorization, and snapshot reads (V0-009).

``docs/state-machines/CLASSROOM_SESSION_STATE_MACHINE.md`` requires an explicit
failure path per transition, and the API maps ``AppError`` to a stable ``code`` +
HTTP status while passing a subclass's ``issue_code`` through the envelope (V0-007).
So:

* a **refused start** subclasses :class:`~app.common.errors.ClassNotReadyError`
  (HTTP ``409`` ``CLASS_NOT_READY``) and adds the precise ``issue_code``:
  the exact version tuple cannot be resolved or is not usable. Every one is raised
  **before** the start transaction, so a refused start writes nothing: the class
  stays ``SCHEDULED``, and there is no plan, session or snapshot row
  (``DEC-RELIABILITY-002``, ``DEC-RUNTIME-003``).
* a **refused join** subclasses :class:`~app.common.errors.NotEnrolledError`
  (HTTP ``403`` ``NOT_ENROLLED``): the principal is inside the tenant but not
  enrolled in the class, so this is class participation, not a tenant boundary.
* a **snapshot that fails validation** is a damaged durable record, so it
  subclasses :class:`~app.common.errors.StorageError` (``502``): the stored state
  disagrees with its own schema version or checksum, and replaying it is exactly
  what ``DEC-DATA-004`` forbids.

The ``issue_code`` values are the client-visible branch points.
"""

from __future__ import annotations

from app.common.errors import ClassNotReadyError, NotEnrolledError, StorageError

#: The class's course version has no publication — a draft, or never published.
ISSUE_VERSION_NOT_PUBLISHED = "VERSION_NOT_PUBLISHED"
#: The knowledge-index pin does not match the published content (``DEC-DATA-005``).
ISSUE_INCOMPATIBLE_INDEX = "INCOMPATIBLE_INDEX"
#: The pinned content is not one this runtime can run (CTF schema/plan mismatch).
ISSUE_INCOMPATIBLE_CONTENT = "INCOMPATIBLE_CONTENT"
#: The stored package no longer matches the digest the publication sealed.
ISSUE_CONTENT_DIGEST_MISMATCH = "CONTENT_DIGEST_MISMATCH"
#: The class is not in a state a start may leave (already started elsewhere).
ISSUE_WRONG_STATE = "WRONG_STATE"
#: The start transaction lost a race and the winner could not be re-read.
ISSUE_COMMIT_CONFLICT = "COMMIT_CONFLICT"
#: A snapshot document fails its schema or checksum validation.
ISSUE_SNAPSHOT_INVALID = "SNAPSHOT_INVALID"
#: The join is refused because the principal is not enrolled in the class.
ISSUE_NOT_ENROLLED = "NOT_ENROLLED"
#: The join is refused because the class has no session yet.
ISSUE_NOT_STARTED = "NOT_STARTED"
#: The presented token is unknown to this tenant (never presented, or not ours).
ISSUE_TOKEN_UNKNOWN = "TOKEN_UNKNOWN"
#: The presented token is past its (bounded) lifetime.
ISSUE_TOKEN_EXPIRED = "TOKEN_EXPIRED"
#: The presented token was terminally revoked.
ISSUE_TOKEN_REVOKED = "TOKEN_REVOKED"
#: The presented token belongs to an epoch the session has left
#: (``DEC-RUNTIME-007``: a stale epoch cannot authorize).
ISSUE_STALE_EPOCH = "STALE_EPOCH"
#: A command names an ``expected_state_version`` the session has moved past
#: (``DEC-RUNTIME-007``: state versions fence stale commands).
ISSUE_STALE_STATE_VERSION = "STALE_STATE_VERSION"
#: A command would move a session between states the machine forbids.
ISSUE_INVALID_TRANSITION = "INVALID_TRANSITION"
#: A command's payload is malformed for its type (a bad navigation target, etc.).
ISSUE_INVALID_COMMAND = "INVALID_COMMAND"
#: The pinned package a scene read addresses is not stored, or holds no such scene.
ISSUE_SCENE_UNAVAILABLE = "SCENE_UNAVAILABLE"
#: The bytes served for a scene do not match the digest the package recorded.
ISSUE_SCENE_CHECKSUM_MISMATCH = "SCENE_CHECKSUM_MISMATCH"


class ClassStartError(ClassNotReadyError):
    """A class start refused before its commit point."""

    def __init__(self, message: str, *, issue_code: str = ISSUE_INCOMPATIBLE_CONTENT) -> None:
        super().__init__(message)
        self.issue_code = issue_code


class JoinDeniedError(NotEnrolledError):
    """A join refused because the principal is not enrolled in the class."""

    def __init__(self, message: str, *, issue_code: str = ISSUE_NOT_ENROLLED) -> None:
        super().__init__(message)
        self.issue_code = issue_code


class SnapshotIntegrityError(StorageError):
    """The stored snapshot fails validation, so it must not be replayed."""

    def __init__(self, message: str, *, issue_code: str = ISSUE_SNAPSHOT_INVALID) -> None:
        super().__init__(message)
        self.issue_code = issue_code


class PinnedSceneError(StorageError):
    """A scene of the session's pinned package cannot be served as it was sealed.

    The package a session pinned is durable state, so a missing or altered file is a
    damaged record rather than a bad request — hence ``502``, the same shape the
    snapshot uses. A scene the package simply does not have is a ``404`` instead
    (:class:`~app.common.errors.NotFoundError`, raised by the caller).
    """

    def __init__(
        self, message: str, *, issue_code: str = ISSUE_SCENE_UNAVAILABLE
    ) -> None:
        super().__init__(message)
        self.issue_code = issue_code


__all__ = [
    "ISSUE_COMMIT_CONFLICT",
    "ISSUE_CONTENT_DIGEST_MISMATCH",
    "ISSUE_INCOMPATIBLE_CONTENT",
    "ISSUE_INCOMPATIBLE_INDEX",
    "ISSUE_INVALID_COMMAND",
    "ISSUE_INVALID_TRANSITION",
    "ISSUE_NOT_ENROLLED",
    "ISSUE_NOT_STARTED",
    "ISSUE_SCENE_CHECKSUM_MISMATCH",
    "ISSUE_SCENE_UNAVAILABLE",
    "ISSUE_SNAPSHOT_INVALID",
    "ISSUE_STALE_EPOCH",
    "ISSUE_STALE_STATE_VERSION",
    "ISSUE_TOKEN_EXPIRED",
    "ISSUE_TOKEN_REVOKED",
    "ISSUE_TOKEN_UNKNOWN",
    "ISSUE_VERSION_NOT_PUBLISHED",
    "ISSUE_WRONG_STATE",
    "ClassStartError",
    "JoinDeniedError",
    "PinnedSceneError",
    "SnapshotIntegrityError",
]
