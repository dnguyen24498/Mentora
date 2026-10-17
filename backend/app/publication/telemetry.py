"""Structured telemetry for the teacher-review write path (V0-007).

Follows the render-stage telemetry (``compiler/renderers/telemetry.py``) and
``docs/architecture/20_OBSERVABILITY_COST_AND_CAPACITY.md``: carry tenant,
artifact, version and package identity, and **redact sensitive text**. A review
reason and an edited script are authored text, so only their presence and length
are recorded — never their content.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("mentora.publication.review")


@dataclass
class ReviewMetrics:
    decisions_recorded: int = 0
    approvals_recorded: int = 0
    rejections_recorded: int = 0
    approvals_blocked: int = 0
    decisions_replayed: int = 0
    drafts_saved: int = 0
    sections_reordered: int = 0
    scripts_edited: int = 0

    def to_dict(self) -> dict[str, int]:
        return dict(self.__dict__)


@dataclass
class ReviewTelemetry:
    """Emits one structured record per review write and keeps counters."""

    metrics: ReviewMetrics = field(default_factory=ReviewMetrics)
    _logger: logging.Logger = field(default=logger, repr=False)

    def emit(self, event: str, **fields: Any) -> dict[str, Any]:
        record = {"event": event, **fields}
        try:
            self._logger.info(json.dumps(record, sort_keys=True, default=str))
        except (TypeError, ValueError):  # pragma: no cover - telemetry must never break a review
            self._logger.info("event=%s", event)
        return record

    def record_decision(
        self,
        *,
        institution_id: str,
        artifact_id: str,
        version_id: str,
        package_id: str,
        content_package_version: str,
        decision: str,
        reason: Optional[str],
        reviewer: str,
        requires_review: bool,
        replayed: bool = False,
    ) -> dict[str, Any]:
        if replayed:
            self.metrics.decisions_replayed += 1
        else:
            self.metrics.decisions_recorded += 1
            if decision == "APPROVE":
                self.metrics.approvals_recorded += 1
            else:
                self.metrics.rejections_recorded += 1
        return self.emit(
            "publication.review.decided",
            institution_id=institution_id,
            artifact_id=artifact_id,
            version_id=version_id,
            package_id=package_id,
            content_package_version=content_package_version,
            decision=decision,
            # Redacted: presence and length, never the text itself.
            reason_present=bool(reason),
            reason_chars=len(reason or ""),
            reviewer_present=bool(reviewer),
            requires_review=requires_review,
            replayed=replayed,
        )

    def record_blocked_approval(
        self,
        *,
        institution_id: str,
        artifact_id: str,
        package_id: str,
        content_package_version: str,
        state: str,
    ) -> dict[str, Any]:
        self.metrics.approvals_blocked += 1
        return self.emit(
            "publication.review.approval_blocked",
            institution_id=institution_id,
            artifact_id=artifact_id,
            package_id=package_id,
            content_package_version=content_package_version,
            state=state,
        )

    def record_draft(
        self,
        *,
        institution_id: str,
        artifact_id: str,
        version_id: str,
        package_id: str,
        content_package_version: str,
        revision: int,
        sections: int,
        reordered: int,
        scripts_edited: int,
    ) -> dict[str, Any]:
        self.metrics.drafts_saved += 1
        self.metrics.sections_reordered += reordered
        self.metrics.scripts_edited += scripts_edited
        return self.emit(
            "publication.review.draft_saved",
            institution_id=institution_id,
            artifact_id=artifact_id,
            version_id=version_id,
            package_id=package_id,
            content_package_version=content_package_version,
            revision=revision,
            sections=sections,
            reordered=reordered,
            scripts_edited=scripts_edited,
        )


# -- the publication transition (V0-008) ------------------------------------------

publication_logger = logging.getLogger("mentora.publication.publish")


@dataclass
class PublicationMetrics:
    """Counters for the seal/index/commit flow.

    One counter per outcome the flow can have, plus one per stage, so an operator
    can see *where* publications stop and how often one is replayed rather than
    created (``DEC-RUNTIME-003`` idempotency is a designed outcome, not an error).
    """

    stages_sealed: int = 0
    stages_indexed: int = 0
    stages_committed: int = 0
    publications_created: int = 0
    publications_replayed: int = 0
    publications_blocked: int = 0
    seal_failures: int = 0
    index_failures: int = 0
    commit_conflicts: int = 0
    supersessions: int = 0
    integrity_checks: int = 0
    integrity_failures: int = 0

    def to_dict(self) -> dict[str, int]:
        return dict(self.__dict__)


@dataclass
class PublicationTelemetry:
    """Emits one structured record per stage/outcome and keeps counters.

    Follows :class:`ReviewTelemetry` and
    ``docs/architecture/20_OBSERVABILITY_COST_AND_CAPACITY.md``: tenant, artifact,
    version, package and the version *tuple* — identities and counts only. Slide
    text, notes and reviewer prose are not part of the publication transition and
    are never recorded.
    """

    metrics: PublicationMetrics = field(default_factory=PublicationMetrics)
    _logger: logging.Logger = field(default=publication_logger, repr=False)

    def emit(self, event: str, **fields: Any) -> dict[str, Any]:
        record = {"event": event, **fields}
        try:
            self._logger.info(json.dumps(record, sort_keys=True, default=str))
        except (TypeError, ValueError):  # pragma: no cover - telemetry must never break publishing
            self._logger.info("event=%s", event)
        return record

    def record_stage(
        self,
        *,
        stage: str,
        outcome: str,
        institution_id: str,
        version_id: str,
        artifact_id: str,
        package_id: str,
        content_package_version: str,
        detail: Optional[str] = None,
    ) -> dict[str, Any]:
        """One stage of the flow, whether it succeeded or refused."""

        return self.emit(
            "publication.stage",
            stage=stage,
            outcome=outcome,
            institution_id=institution_id,
            version_id=version_id,
            artifact_id=artifact_id,
            package_id=package_id,
            content_package_version=content_package_version,
            detail=detail,
        )

    def record_publish(
        self,
        *,
        publication_id: str,
        institution_id: str,
        course_id: str,
        version_id: str,
        course_version: int,
        artifact_id: str,
        package_id: str,
        content_package_version: str,
        knowledge_index_version: str,
        teaching_graph_version: Optional[str],
        file_count: int,
        total_bytes: int,
        scene_count: Optional[int],
        created: bool,
        superseded: int = 0,
    ) -> dict[str, Any]:
        if created:
            self.metrics.publications_created += 1
        else:
            self.metrics.publications_replayed += 1
        self.metrics.supersessions += superseded
        return self.emit(
            "publication.published",
            publication_id=publication_id,
            institution_id=institution_id,
            course_id=course_id,
            version_id=version_id,
            course_version=course_version,
            artifact_id=artifact_id,
            package_id=package_id,
            content_package_version=content_package_version,
            knowledge_index_version=knowledge_index_version,
            teaching_graph_version=teaching_graph_version,
            files=file_count,
            bytes=total_bytes,
            scenes=scene_count,
            created=created,
            superseded=superseded,
        )

    def record_blocked(
        self,
        *,
        stage: str,
        issue_code: str,
        institution_id: str,
        version_id: str,
        artifact_id: str,
        package_id: str,
        content_package_version: str,
    ) -> dict[str, Any]:
        self.metrics.publications_blocked += 1
        if stage == "SEALING":
            self.metrics.seal_failures += 1
        elif stage == "INDEXING":
            self.metrics.index_failures += 1
        elif stage == "COMMITTING":
            self.metrics.commit_conflicts += 1
        return self.emit(
            "publication.blocked",
            stage=stage,
            issue_code=issue_code,
            institution_id=institution_id,
            version_id=version_id,
            artifact_id=artifact_id,
            package_id=package_id,
            content_package_version=content_package_version,
        )

    def record_integrity(
        self,
        *,
        institution_id: str,
        publication_id: str,
        package_id: str,
        state: str,
        file_count: int,
    ) -> dict[str, Any]:
        self.metrics.integrity_checks += 1
        if state != "VERIFIED":
            self.metrics.integrity_failures += 1
        return self.emit(
            "publication.integrity_checked",
            institution_id=institution_id,
            publication_id=publication_id,
            package_id=package_id,
            state=state,
            files=file_count,
        )


__all__ = [
    "PublicationMetrics",
    "PublicationTelemetry",
    "ReviewMetrics",
    "ReviewTelemetry",
]
