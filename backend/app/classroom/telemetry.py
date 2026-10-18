"""Structured telemetry for class start and join authorization (V0-009).

Follows the render-stage and publication telemetry
(``docs/architecture/20_OBSERVABILITY_COST_AND_CAPACITY.md``): carry tenant, class,
session, course/version/package identity and counts — never authored text. A class
title and a student id are the only free-form values near this flow, and the
student id is recorded as *presence* only, because it identifies a person.

``docs/sequences/CLASS_START.md`` asserts *"Every terminal path emits metrics and
user-visible state."* That is why a refused start emits ``class.start_blocked``
with its ``issue_code`` and why a refused join emits ``class.join_denied``: the
terminal failure paths are observable, not just the success path.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from app.classroom.aggregate import (
    COMMAND_CHECKPOINT,
    COMMAND_END,
    COMMAND_NAVIGATE,
)

logger = logging.getLogger("mentora.classroom")


@dataclass
class ClassroomMetrics:
    """Counters for the class-start and join flow."""

    classes_scheduled: int = 0
    enrollments_created: int = 0
    enrollments_replayed: int = 0
    sessions_started: int = 0
    starts_replayed: int = 0
    starts_blocked: int = 0
    joins_authorized: int = 0
    joins_denied: int = 0
    snapshots_read: int = 0
    snapshot_failures: int = 0
    scenes_read: int = 0
    scene_listings: int = 0
    commands_accepted: int = 0
    commands_rejected: int = 0
    commands_duplicated: int = 0
    scenes_changed: int = 0
    checkpoints_recorded: int = 0
    sessions_ended: int = 0

    def to_dict(self) -> dict[str, int]:
        return dict(self.__dict__)


@dataclass
class ClassroomTelemetry:
    """Emits one structured record per outcome and keeps counters."""

    metrics: ClassroomMetrics = field(default_factory=ClassroomMetrics)
    _logger: logging.Logger = field(default=logger, repr=False)

    def emit(self, event: str, **fields: Any) -> dict[str, Any]:
        record = {"event": event, **fields}
        try:
            self._logger.info(json.dumps(record, sort_keys=True, default=str))
        except (TypeError, ValueError):  # pragma: no cover - telemetry must never break a start
            self._logger.info("event=%s", event)
        return record

    def record_scheduled(
        self,
        *,
        institution_id: str,
        class_id: str,
        course_id: str,
        title: str,
        version_id: Optional[str],
        scheduled_for: Optional[str],
    ) -> dict[str, Any]:
        self.metrics.classes_scheduled += 1
        return self.emit(
            "class.scheduled",
            institution_id=institution_id,
            class_id=class_id,
            course_id=course_id,
            # The title is course-authored text: record its presence, not it.
            title_present=bool(title),
            title_chars=len(title or ""),
            version_pinned=version_id is not None,
            scheduled=bool(scheduled_for),
        )

    def record_started(
        self,
        *,
        institution_id: str,
        class_id: str,
        session_id: str,
        course_id: str,
        version_id: str,
        course_version: int,
        package_id: str,
        content_package_version: str,
        knowledge_index_version: str,
        policy_version: str,
        capability_version: str,
        region: str,
        actor_epoch: int,
        created: bool,
    ) -> dict[str, Any]:
        if created:
            self.metrics.sessions_started += 1
        else:
            self.metrics.starts_replayed += 1
        return self.emit(
            "class.started",
            institution_id=institution_id,
            class_id=class_id,
            session_id=session_id,
            course_id=course_id,
            version_id=version_id,
            course_version=course_version,
            package_id=package_id,
            content_package_version=content_package_version,
            knowledge_index_version=knowledge_index_version,
            policy_version=policy_version,
            capability_version=capability_version,
            region=region,
            actor_epoch=actor_epoch,
            created=created,
        )

    def record_blocked(
        self,
        *,
        institution_id: str,
        class_id: str,
        course_id: str,
        stage: str,
        issue_code: str,
        version_id: Optional[str] = None,
    ) -> dict[str, Any]:
        self.metrics.starts_blocked += 1
        return self.emit(
            "class.start_blocked",
            institution_id=institution_id,
            class_id=class_id,
            course_id=course_id,
            stage=stage,
            issue_code=issue_code,
            version_id=version_id,
        )

    def record_join(
        self,
        *,
        institution_id: str,
        class_id: str,
        session_id: Optional[str],
        authorized: bool,
        issue_code: Optional[str] = None,
    ) -> dict[str, Any]:
        if authorized:
            self.metrics.joins_authorized += 1
        else:
            self.metrics.joins_denied += 1
        return self.emit(
            "class.join",
            institution_id=institution_id,
            class_id=class_id,
            session_id=session_id,
            authorized=authorized,
            issue_code=issue_code,
            # The student id identifies a person: presence and length only.
            student_present=True,
        )

    def record_snapshot_read(
        self, *, institution_id: str, class_id: str, session_id: str, state_version: int
    ) -> dict[str, Any]:
        self.metrics.snapshots_read += 1
        return self.emit(
            "class.snapshot_read",
            institution_id=institution_id,
            class_id=class_id,
            session_id=session_id,
            state_version=state_version,
        )

    def record_snapshot_failure(
        self, *, institution_id: str, session_id: str, issue_code: str
    ) -> dict[str, Any]:
        self.metrics.snapshot_failures += 1
        return self.emit(
            "class.snapshot_invalid",
            institution_id=institution_id,
            session_id=session_id,
            issue_code=issue_code,
        )

    def record_scene_read(
        self,
        *,
        institution_id: str,
        class_id: str,
        session_id: str,
        package_id: str,
        order: int,
        scene_id: Optional[str],
        byte_size: int,
    ) -> dict[str, Any]:
        """A serving of one slide of the *pinned* package.

        The package id is recorded, not the course or a ``latest`` reference: a
        scene read that logged anything else could not be distinguished from the
        forbidden "read the newest render" path (``DEC-CONTENT-005``).
        """

        self.metrics.scenes_read += 1
        return self.emit(
            "class.scene_read",
            institution_id=institution_id,
            class_id=class_id,
            session_id=session_id,
            package_id=package_id,
            order=order,
            scene_id=scene_id,
            byte_size=byte_size,
        )

    def record_scene_listing(
        self,
        *,
        institution_id: str,
        class_id: str,
        session_id: str,
        package_id: str,
        scene_count: int,
    ) -> dict[str, Any]:
        """A read of the pinned package's slide list (identities, never the text).

        The scene *text* is deck content, so it is counted and never logged — the
        same rule the classroom telemetry already applies to transcripts.
        """

        self.metrics.scene_listings += 1
        return self.emit(
            "class.scene_listing",
            institution_id=institution_id,
            class_id=class_id,
            session_id=session_id,
            package_id=package_id,
            scene_count=scene_count,
        )

    def record_command(
        self,
        *,
        institution_id: str,
        class_id: str,
        session_id: str,
        command_id: str,
        command_type: str,
        accepted: bool,
        state_version: int,
        issue_code: Optional[str] = None,
        duplicate: bool = False,
    ) -> dict[str, Any]:
        """One command's terminal verdict (V0-010): identities and issue codes only.

        ``CLASS_START.md``'s assertion — every terminal path is observable — applies
        to the aggregate too: a refused command emits its ``issue_code``, a
        duplicate emits ``duplicate: true``, and an accepted navigation/checkpoint/
        end bumps its own counter.
        """

        if duplicate:
            self.metrics.commands_duplicated += 1
        elif accepted:
            self.metrics.commands_accepted += 1
            if command_type == COMMAND_NAVIGATE:
                self.metrics.scenes_changed += 1
            elif command_type == COMMAND_CHECKPOINT:
                self.metrics.checkpoints_recorded += 1
            elif command_type == COMMAND_END:
                self.metrics.sessions_ended += 1
        else:
            self.metrics.commands_rejected += 1
        return self.emit(
            "class.command",
            institution_id=institution_id,
            class_id=class_id,
            session_id=session_id,
            command_id=command_id,
            command_type=command_type,
            accepted=accepted,
            duplicate=duplicate,
            state_version=state_version,
            issue_code=issue_code,
        )


__all__ = ["ClassroomMetrics", "ClassroomTelemetry"]
