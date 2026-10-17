"""Transactional outbox for publication events (V0-008).

``docs/architecture/16_DATA_STORAGE_AND_EVENTS.md``: *"Use transactional outbox to
avoid database/event dual write. Delivery may be at-least-once; logical effects
are idempotent."* ``docs/data/OUTBOX_SNAPSHOT_AND_RETENTION.md``: *"Outbox delivers
at least once, consumers deduplicate event ID."*

The row is written **inside the same transaction** as the publication metadata, so
the two can never disagree: a visible publication always has its event, and a
refused one has neither. ``event_id`` is the identity a consumer deduplicates on.

Delivery is deliberately **not** implemented. ``DEC-TECH-001`` (ordered
command/event technology) is ``OPEN`` and the task's out-of-scope list excludes LMS
notification, so adding a broker, a relay worker or a delivery guarantee here would
be presenting an open decision as accepted architecture. The row is durable and
pull-readable (``dispatched_at`` is ``NULL`` and nobody claims it yet); a later
task adds the sender without changing this contract.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Optional

#: Event emitted once a publication is visible. Versioned like the other event
#: payloads: changing the shape is a contract change, not an implementation detail.
PUBLICATION_EVENT_TYPE = "course.version.published"

#: ``contracts/events/course-version-published.schema.json`` aggregate.
PUBLICATION_AGGREGATE_TYPE = "CourseVersion"


@dataclass(frozen=True)
class OutboxEvent:
    """One durable, not-yet-dispatched publication event."""

    event_id: str
    event_type: str
    institution_id: str
    aggregate_type: str
    aggregate_id: str
    payload: dict[str, Any]
    created_at: str
    dispatched_at: Optional[str] = None

    @property
    def dispatched(self) -> bool:
        return self.dispatched_at is not None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "OutboxEvent":
        import json

        return cls(
            event_id=row["event_id"],
            event_type=row["event_type"],
            institution_id=row["institution_id"],
            aggregate_type=row["aggregate_type"],
            aggregate_id=row["aggregate_id"],
            payload=json.loads(row["payload"]),
            created_at=row["created_at"],
            dispatched_at=row["dispatched_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "payload": self.payload,
            "created_at": self.created_at,
            "dispatched_at": self.dispatched_at,
        }


def publication_event_payload(
    *,
    event_id: str,
    occurred_at: str,
    institution_id: str,
    course_id: str,
    version_id: str,
    course_version: int,
    artifact_id: str,
    publication_id: str,
    package_id: str,
    content_package_version: str,
    lesson_plan_versions: tuple[str, ...],
    knowledge_index_version: str,
    teaching_graph_version: Optional[str],
) -> dict[str, Any]:
    """The event body: the **whole pinned version tuple**, and nothing sensitive.

    A consumer (a notification, an analytics projector) needs to know exactly which
    content/lesson/knowledge versions a session may pin (``DEC-CONTENT-005``), so
    the tuple travels with the event. No slide text, notes or reviewer identity —
    those are not the event's business.
    """

    return {
        "event_id": event_id,
        "event_type": PUBLICATION_EVENT_TYPE,
        "occurred_at": occurred_at,
        "institution_id": institution_id,
        "course_id": course_id,
        "version_id": version_id,
        "course_version": course_version,
        "artifact_id": artifact_id,
        "publication_id": publication_id,
        "package_id": package_id,
        "content_package_version": content_package_version,
        "lesson_plan_versions": list(lesson_plan_versions),
        "knowledge_index_version": knowledge_index_version,
        "teaching_graph_version": teaching_graph_version,
    }


__all__ = [
    "PUBLICATION_AGGREGATE_TYPE",
    "PUBLICATION_EVENT_TYPE",
    "OutboxEvent",
    "publication_event_payload",
]
