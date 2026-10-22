"""Auto-publication of an uploaded deck when the review policy allows it.

The upload flow used to make a teacher walk three separate actions — build the
review package, approve it in Teacher Studio, then publish the version in Admin —
before a deck could be taught. This module composes those same domain operations
for the common case, without weakening either gate:

* the package is built by :class:`~app.publication.review.ReviewService`, so the
  V0-005 fidelity gate still refuses a blocked deck before any decision exists;
* a package whose review state is ``READY`` is **auto-allowed**
  (``docs/architecture/07_PUBLICATION_AND_REVIEW.md``), so it is approved with the
  uploading teacher's attribution and published atomically;
* a ``REVIEW_REQUIRED`` package is returned **unpublished** for a human decision.
  Automation must never approve content the policy marked human-required;
* a replay returns the publication already created for the same content
  (``DEC-RUNTIME-003``), so a retried upload does not create a second one.

Attribution is the caller's account (email/account id), falling back to the
tenant for the pre-auth development shortcut — the same convention as the review
and publication routers. It is attribution, not authorization: the endpoint
requires the content, review and publication capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.common.errors import NotFoundError
from app.courses.repository import CourseRepository
from app.publication.review import STATE_READY, ReviewService
from app.publication.service import PublicationService
from app.publication.workflow import ReviewState, ReviewWorkflow

#: The audit reason recorded on the automatic approval.
AUTO_APPROVAL_REASON = (
    "Auto-approved on upload: the package is auto-allowed and needs no human review."
)


@dataclass(frozen=True)
class AutoPublicationResult:
    """What the upload path's publication attempt produced.

    ``published`` is the only success question a client should ask. When it is
    false the artifact and package still exist and remain reviewable; the
    ``review_state`` says why the automation stopped.
    """

    artifact_id: str
    version_id: str
    package_id: str
    content_package_version: str
    state: str
    published: bool
    created: bool
    requires_review: bool
    publication: Optional[dict[str, Any]]
    review_state: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "version_id": self.version_id,
            "package_id": self.package_id,
            "content_package_version": self.content_package_version,
            "state": self.state,
            "published": self.published,
            "created": self.created,
            "requires_review": self.requires_review,
            "publication": self.publication,
            "review_state": self.review_state,
        }


class AutoPublicationService:
    """Publish a freshly uploaded, auto-allowed package as its uploader."""

    def __init__(
        self,
        courses: CourseRepository,
        review_service: ReviewService,
        workflow: ReviewWorkflow,
        publications: PublicationService,
    ) -> None:
        self._courses = courses
        self._reviews = review_service
        self._workflow = workflow
        self._publications = publications

    def publish(
        self,
        institution_id: str,
        artifact_id: str,
        *,
        published_by: Optional[str] = None,
    ) -> AutoPublicationResult:
        """Build, auto-approve when allowed, and publish one artifact's package."""

        artifact = self._courses.get_artifact(institution_id, artifact_id)
        attribution = (published_by or "").strip() or institution_id

        # Idempotency comes before rendering: a replay of an upload that already
        # published this version must not record a second decision, rebuild a
        # package for a newer renderer, or move the version out of PUBLISHED.
        existing = self._existing_publication(institution_id, artifact.version_id)
        if existing is not None:
            state = self._workflow.review_state(institution_id, artifact_id)
            return self._result(state, existing, published=True, created=False)

        review = self._reviews.build_review(institution_id, artifact_id)
        if review.state != STATE_READY or review.requires_review:
            # Human-required: the package is publishable, but only a teacher may
            # decide it. The uploader is told to open Teacher Studio.
            state = self._workflow.review_state(institution_id, artifact_id)
            return self._result(state, None, published=False, created=False)

        state = self._workflow.review_state(institution_id, artifact_id)
        approved = state.decision is not None and state.decision.decision == "APPROVE"
        if not approved or state.stale:
            state = self._workflow.decide(
                institution_id,
                artifact_id,
                decision="APPROVE",
                reason=AUTO_APPROVAL_REASON,
                reviewer=attribution,
            )

        publication, created = self._publications.publish(
            institution_id,
            artifact.version_id,
            published_by=attribution,
        )
        return self._result(
            state, publication.to_dict(), published=True, created=created
        )

    # -- internals ---------------------------------------------------------------
    def _existing_publication(
        self, institution_id: str, version_id: str
    ) -> Optional[dict[str, Any]]:
        try:
            return self._publications.publication_for_version(institution_id, version_id)
        except NotFoundError:
            return None

    @staticmethod
    def _result(
        state: ReviewState,
        publication: Optional[dict[str, Any]],
        *,
        published: bool,
        created: bool,
    ) -> AutoPublicationResult:
        return AutoPublicationResult(
            artifact_id=state.artifact_id,
            version_id=state.version_id,
            package_id=state.package_id,
            content_package_version=state.content_package_version,
            state=state.state,
            published=published,
            created=created,
            requires_review=state.requires_review,
            publication=publication,
            review_state=state.to_dict(),
        )


__all__ = ["AUTO_APPROVAL_REASON", "AutoPublicationResult", "AutoPublicationService"]
