"""The session snapshot: initial document, canonical form, and validation (V0-009).

``DEC-DATA-004`` ("Runtime recovers through durable snapshot plus ordered event
replay") and ``docs/architecture/02_ARCHITECTURAL_INVARIANTS.md``: *"Snapshot/checksum/
schema validated before replay."* So a snapshot is not a blob: it declares a schema
version, it has a checksum over its canonical bytes, and a reader validates both
**before** using it — a snapshot that disagrees with its own envelope is refused
rather than replayed.

V0-009 writes one snapshot: the *initial* one, in the same transaction as the
session. Its regions are the ones ``docs/architecture/09_CLASSROOM_ACTOR_AND_RECOVERY.md``
names, at their starting values: versions, lesson/scene/step, queue/floor, timeline
checkpoint, pending effects, epoch/version/sequence. The Classroom Actor (V0-010)
owns every later mutation; keeping the *shape* here means recovery has one
document to restore from rather than a growing set.

Canonical JSON (sorted keys, no incidental whitespace) is what the checksum covers,
so a re-serialisation that changes nothing keeps the same digest.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Optional

from app.classroom.errors import (
    ISSUE_INCOMPATIBLE_CONTENT,
    ISSUE_SNAPSHOT_INVALID,
    ClassStartError,
    SnapshotIntegrityError,
)
from app.classroom.models import SNAPSHOT_SCHEMA_VERSION

#: Every region a snapshot must carry. A document missing one is not replayable,
#: so its absence is a validation failure rather than a default.
REQUIRED_REGIONS: tuple[str, ...] = (
    "schema_version",
    "institution_id",
    "course_id",
    "class_id",
    "session_id",
    "state",
    "actor_epoch",
    "state_version",
    "event_sequence",
    "versions",
    "lesson",
    "turn",
    "timeline",
    "pending_effects",
)


def canonical_json(document: Mapping[str, Any]) -> bytes:
    """Deterministic bytes for a snapshot document (the checksum's input)."""

    return json.dumps(document, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def snapshot_checksum(document: Mapping[str, Any]) -> str:
    """sha256 over the canonical document."""

    return hashlib.sha256(canonical_json(document)).hexdigest()


def first_lesson_position(lesson_plan: Mapping[str, Any]) -> dict[str, Any]:
    """The lesson position a session starts at: the first section of its plan.

    ``DEC-CONTENT-007`` (instructional reveal order is preserved as discrete scene
    steps) means a section already names the scene and step it begins with, so the
    initial position is read, never recomputed. A plan with no section cannot be
    positioned, so it is an incompatible package rather than an empty start.
    """

    sections = list(lesson_plan.get("sections") or [])
    if not sections:
        raise ClassStartError(
            "the pinned lesson plan has no section to start at",
            issue_code=ISSUE_INCOMPATIBLE_CONTENT,
        )
    first = sections[0]
    return {
        "lesson_plan_version": lesson_plan.get("lesson_plan_version"),
        "lesson_id": lesson_plan.get("lesson_id"),
        "section_index": 0,
        "section_id": first.get("section_id"),
        "scene_id": first.get("scene_id"),
        "scene_step_id": first.get("scene_step_id"),
    }


def validate_snapshot(
    document: Mapping[str, Any],
    *,
    schema_version: Optional[str] = None,
    checksum: Optional[str] = None,
) -> None:
    """Validate a stored snapshot before it is used, or refuse it.

    Three independent failures, each naming what is wrong: an unsupported schema
    version (the document is not one this build can read), a missing region (the
    document is not replayable), and a checksum mismatch (the stored bytes are not
    the bytes that were written).
    """

    document_version = document.get("schema_version")
    if document_version != SNAPSHOT_SCHEMA_VERSION:
        raise SnapshotIntegrityError(
            f"snapshot schema {document_version!r} is not supported "
            f"(expected {SNAPSHOT_SCHEMA_VERSION!r})",
            issue_code=ISSUE_SNAPSHOT_INVALID,
        )
    if schema_version is not None and schema_version != document_version:
        raise SnapshotIntegrityError(
            f"snapshot row says schema {schema_version!r} but the document says "
            f"{document_version!r}",
            issue_code=ISSUE_SNAPSHOT_INVALID,
        )
    missing = [region for region in REQUIRED_REGIONS if region not in document]
    if missing:
        raise SnapshotIntegrityError(
            f"snapshot is missing region(s): {', '.join(missing)}",
            issue_code=ISSUE_SNAPSHOT_INVALID,
        )
    if checksum is not None and snapshot_checksum(document) != checksum:
        raise SnapshotIntegrityError(
            "snapshot checksum does not match its document",
            issue_code=ISSUE_SNAPSHOT_INVALID,
        )


__all__ = [
    "REQUIRED_REGIONS",
    "canonical_json",
    "first_lesson_position",
    "snapshot_checksum",
    "validate_snapshot",
]
