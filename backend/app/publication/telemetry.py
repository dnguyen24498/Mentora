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


__all__ = ["ReviewMetrics", "ReviewTelemetry"]
