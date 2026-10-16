"""The teacher-review write path: record a decision, propose a draft (V0-007).

Pipeline position: after ``docs/architecture/04_CONTENT_COMPILER.md``'s
validation stage and before publication. It answers "may this built content go
on?", which ``docs/architecture/07_PUBLICATION_AND_REVIEW.md`` splits into
auto-allowed / human-required / blocked:

* the V0-005 fidelity gate already refuses to *build* a blocked document, so a
  blocked failure never reaches a review at all;
* a human-required outcome is resolved here — a teacher approves or rejects;
* approving moves the course version to ``APPROVED``
  (``docs/state-machines/PUBLICATION_STATE_MACHINE.md``). ``APPROVED`` →
  ``SEALING`` → … → ``PUBLISHED`` is V0-008.

Nothing in this module writes to the package. A draft is an appended *revision*
of the lesson order; the immutable package under review is byte-identical before
and after (``DEC-CONTENT-005``), so an edit can be reviewed, kept or discarded
without ever having changed what students would receive.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

from app.common.errors import NotFoundError, PublicationBlockedError, ValidationError
from app.courses.models import CourseVersionStatus
from app.courses.repository import CourseRepository
from app.publication.draft import DraftDiff, SectionInput, resolve_draft_sections
from app.publication.models import (
    DECISION_APPROVE,
    DECISION_REJECT,
    ReviewDecision,
    ReviewDecisionKind,
    ReviewDraft,
)
from app.publication.repository import ReviewRepository
from app.publication.review import STATE_BLOCKED, ReviewPackage, ReviewService
from app.publication.telemetry import ReviewTelemetry

#: Version status each outcome lands on. A rejection deliberately returns the
#: version to the queue rather than inventing a "rejected" lifecycle state that
#: the publication state machine does not have.
STATUS_FOR_DECISION = {
    DECISION_APPROVE: CourseVersionStatus.APPROVED,
    DECISION_REJECT: CourseVersionStatus.REVIEW_REQUIRED,
}


@dataclass(frozen=True)
class ReviewState:
    """The review *state* of one artifact: decision, draft, and blocking picture.

    Distinct from :class:`~app.publication.review.ReviewPackage`, which projects
    the package itself. This is the mutable-overlay half of the review page and
    is what the Teacher Studio polls after acting.
    """

    artifact_id: str
    version_id: str
    version_status: str
    package_id: str
    content_package_version: str
    state: str
    publishable: bool
    requires_review: bool
    stale: bool
    blocking_scene_orders: tuple[int, ...]
    decision: Optional[ReviewDecision]
    draft: Optional[ReviewDraft]
    draft_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "version_id": self.version_id,
            "version_status": self.version_status,
            "package_id": self.package_id,
            "content_package_version": self.content_package_version,
            "state": self.state,
            "publishable": self.publishable,
            "requires_review": self.requires_review,
            "stale": self.stale,
            "blocking_scene_orders": list(self.blocking_scene_orders),
            "decision": self.decision.to_dict() if self.decision else None,
            "draft": self.draft.to_dict() if self.draft else None,
            "draft_count": self.draft_count,
        }


class ReviewWorkflow:
    """Records review outcomes and draft revisions for built packages."""

    def __init__(
        self,
        review_service: ReviewService,
        repository: ReviewRepository,
        course_repository: CourseRepository,
        telemetry: Optional[ReviewTelemetry] = None,
    ) -> None:
        self._review = review_service
        self._repository = repository
        self._courses = course_repository
        self._telemetry = telemetry or ReviewTelemetry()

    @property
    def telemetry(self) -> ReviewTelemetry:
        return self._telemetry

    # -- reads ----------------------------------------------------------------------
    def review_state(self, institution_id: str, artifact_id: str) -> ReviewState:
        """The current decision and newest draft for the artifact's built package."""

        review = self._require_package(institution_id, artifact_id)
        return self._state(institution_id, artifact_id, review)

    def list_drafts(self, institution_id: str, artifact_id: str) -> list[ReviewDraft]:
        # Authorize through the package read before touching the draft table.
        self._require_package(institution_id, artifact_id)
        return self._repository.list_drafts(institution_id, artifact_id)

    # -- writes ---------------------------------------------------------------------
    def decide(
        self,
        institution_id: str,
        artifact_id: str,
        *,
        decision: str,
        reason: Optional[str] = None,
        reviewer: Optional[str] = None,
    ) -> ReviewState:
        """Approve or reject the built package. Idempotent for a repeated click."""

        kind = ReviewDecisionKind.parse(decision)
        review = self._require_package(institution_id, artifact_id)
        artifact = self._courses.get_artifact(institution_id, artifact_id)

        if kind is ReviewDecisionKind.APPROVE and not review.publishable:
            # Defense in depth: a blocked document is normally never built, but an
            # approval must be impossible for one that somehow is.
            self._telemetry.record_blocked_approval(
                institution_id=institution_id,
                artifact_id=artifact_id,
                package_id=review.package_id,
                content_package_version=review.content_package_version,
                state=review.state or STATE_BLOCKED,
            )
            raise PublicationBlockedError(
                f"package {review.package_id} is not publishable (state {review.state}); "
                "a blocking fidelity failure must be fixed and re-rendered before review"
            )

        cleaned_reason = (reason or "").strip() or None
        if kind is ReviewDecisionKind.REJECT and not cleaned_reason:
            raise ValidationError("a rejection must record a reason")
        reviewer_id = (reviewer or "").strip() or institution_id

        current = self._repository.latest_decision(institution_id, artifact_id)
        replayed = bool(
            current
            and current.decision == kind.value
            and current.reason == cleaned_reason
            and current.reviewer == reviewer_id
            and current.content_package_version == review.content_package_version
        )
        if not replayed:
            current = self._repository.record_decision(
                institution_id=institution_id,
                artifact_id=artifact_id,
                version_id=artifact.version_id,
                package_id=review.package_id,
                content_package_version=review.content_package_version,
                decision=kind.value,
                reason=cleaned_reason,
                reviewer=reviewer_id,
            )
            # Review state only: `APPROVED -> SEALING -> … -> PUBLISHED` is V0-008.
            self._courses.set_version_status(
                institution_id, artifact.version_id, STATUS_FOR_DECISION[kind.value]
            )

        self._telemetry.record_decision(
            institution_id=institution_id,
            artifact_id=artifact_id,
            version_id=artifact.version_id,
            package_id=review.package_id,
            content_package_version=review.content_package_version,
            decision=kind.value,
            reason=cleaned_reason,
            reviewer=reviewer_id,
            requires_review=review.requires_review,
            replayed=replayed,
        )
        return self._state(institution_id, artifact_id, review)

    def save_draft(
        self,
        institution_id: str,
        artifact_id: str,
        *,
        sections: Iterable[SectionInput],
        edited_by: Optional[str] = None,
    ) -> ReviewDraft:
        """Append a new draft revision of the lesson order (never mutates the package)."""

        review = self._require_package(institution_id, artifact_id)
        artifact = self._courses.get_artifact(institution_id, artifact_id)

        resolved, diff = resolve_draft_sections(review.lesson_order, sections)
        draft = self._repository.create_draft(
            institution_id=institution_id,
            artifact_id=artifact_id,
            version_id=artifact.version_id,
            package_id=review.package_id,
            content_package_version=review.content_package_version,
            lesson_plan_version=review.lesson_plan_version,
            sections=resolved,
            edited_by=(edited_by or "").strip() or institution_id,
        )
        self._record_draft_telemetry(institution_id, artifact_id, artifact.version_id, review, draft, diff)
        return draft

    # -- internals ------------------------------------------------------------------
    def _record_draft_telemetry(
        self,
        institution_id: str,
        artifact_id: str,
        version_id: str,
        review: ReviewPackage,
        draft: ReviewDraft,
        diff: DraftDiff,
    ) -> None:
        self._telemetry.record_draft(
            institution_id=institution_id,
            artifact_id=artifact_id,
            version_id=version_id,
            package_id=review.package_id,
            content_package_version=review.content_package_version,
            revision=draft.revision,
            sections=diff.sections,
            reordered=diff.reordered,
            scripts_edited=diff.scripts_edited,
        )

    def _require_package(self, institution_id: str, artifact_id: str) -> ReviewPackage:
        review = self._review.load_review(institution_id, artifact_id)
        if review is None:
            raise NotFoundError(
                f"no package has been built for artifact {artifact_id}; "
                "POST to the review-package path before reviewing it"
            )
        return review

    def _state(
        self, institution_id: str, artifact_id: str, review: ReviewPackage
    ) -> ReviewState:
        artifact = self._courses.get_artifact(institution_id, artifact_id)
        version = self._courses.get_version(institution_id, artifact.version_id)
        decision = self._repository.latest_decision(institution_id, artifact_id)
        draft = self._repository.latest_draft(institution_id, artifact_id)
        # A decision is only current for the content it actually reviewed.
        stale = bool(
            decision and decision.content_package_version != review.content_package_version
        )
        return ReviewState(
            artifact_id=artifact_id,
            version_id=artifact.version_id,
            version_status=version.status,
            package_id=review.package_id,
            content_package_version=review.content_package_version,
            state=review.state,
            publishable=review.publishable,
            requires_review=review.requires_review,
            stale=stale,
            blocking_scene_orders=tuple(
                scene.order for scene in review.scenes if scene.render_status != "RENDERED"
            ),
            decision=decision,
            draft=draft,
            draft_count=self._repository.draft_count(institution_id, artifact_id),
        )


__all__ = ["STATUS_FOR_DECISION", "ReviewState", "ReviewWorkflow"]
