"""HTTP surface for the teacher review preview and review actions (V0-007) and
for the atomic publication transition (V0-008).

The review needs the *lesson order*, which only the baseline package knows, so it
cannot be built from the V0-005 endpoints alone. Routes:

* ``POST /artifacts/{artifactId}/review-package`` — build (idempotent, the
  expensive path: it renders) and return the review projection.
* ``GET  /artifacts/{artifactId}/review-package`` — project the *stored* package
  (cheap, no rendering); ``404`` when it has not been built yet.
* ``GET  /artifacts/{artifactId}/review-package/renders/{order}`` — one slide's
  packaged fallback render, served from the package with the tenant header, so the
  browser never needs an unauthenticated ``<img src>``.
* ``POST /artifacts/{artifactId}/review-package/decision`` — approve or reject.
* ``GET  /artifacts/{artifactId}/review-package/review-state`` — the current
  decision, the newest draft and the blocking picture.
* ``POST /artifacts/{artifactId}/review-package/drafts`` — append a draft
  revision of the lesson order (never touches the package).
* ``GET  /artifacts/{artifactId}/review-package/drafts`` — draft history.

Publication (V0-008):

* ``POST /course-versions/{versionId}/publish`` — seal, index and commit an
  approved version (idempotent: a replay returns the same publication).
* ``GET  /course-versions/{versionId}/publication`` — the newest publication of a
  version, optionally re-verified against its seal.
* ``GET  /publications/{publicationId}`` — one publication by identity, including
  a superseded one (``DEC-CONTENT-005``: a session keeps its pinned version).
* ``GET  /courses/{courseId}/publications`` — publication history of a course.

Every route is tenant-scoped through ``X-Institution-Id``. Without the header the
request is rejected before reaching the service (422), which is exactly why the
frontend fetches renders through JS and turns them into blob URLs.
"""

from __future__ import annotations

from typing import Callable, Literal, Optional

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from app.common.errors import NotFoundError
from app.publication.draft import SectionInput
from app.publication.review import ReviewService
from app.publication.service import PublicationService
from app.publication.workflow import ReviewWorkflow


class ReviewDecisionRequest(BaseModel):
    """An approve/reject action on the built package."""

    #: ``APPROVE`` or ``REJECT``. Rejection additionally requires ``reason``.
    decision: Literal["APPROVE", "REJECT"]
    reason: Optional[str] = Field(default=None, max_length=4000)
    #: Attribution only — identity/roles are not implemented yet, so this is not
    #: an authorization control (docs/security/IDENTITY_AUTHORIZATION_AND_TOKENS.md).
    reviewer: Optional[str] = Field(default=None, max_length=256)


class ReviewDraftSectionRequest(BaseModel):
    section_id: str = Field(min_length=1)
    script: Optional[str] = Field(default=None, max_length=20000)


class ReviewDraftRequest(BaseModel):
    """A proposed lesson order: array position *is* the new order."""

    sections: list[ReviewDraftSectionRequest]
    edited_by: Optional[str] = Field(default=None, max_length=256)


def build_review_router(
    review_service: ReviewService,
    workflow: ReviewWorkflow,
    tenant: Callable[..., str],
) -> APIRouter:
    router = APIRouter()

    @router.post("/artifacts/{artifact_id}/review-package")
    def build_review_package(
        artifact_id: str, institution_id: str = Depends(tenant)
    ) -> dict:
        """Build (or rebuild) the package and return the review view."""

        return review_service.build_review(institution_id, artifact_id).to_dict()

    @router.get("/artifacts/{artifact_id}/review-package")
    def get_review_package(artifact_id: str, institution_id: str = Depends(tenant)) -> dict:
        review = review_service.load_review(institution_id, artifact_id)
        if review is None:
            raise NotFoundError(
                f"no package has been built for artifact {artifact_id}; "
                "POST to this path to build it"
            )
        return review.to_dict()

    @router.get("/artifacts/{artifact_id}/review-package/renders/{order}")
    def get_review_render(
        artifact_id: str, order: int, institution_id: str = Depends(tenant)
    ) -> Response:
        payload = review_service.scene_svg(institution_id, artifact_id, order)
        return Response(
            content=payload,
            media_type="image/svg+xml",
            # The packaged asset is immutable *and* the review's ``render_url`` names
            # it (``?v=<asset digest>``), so a cached response can only ever be this
            # exact slide. Without the version a recompile would hide behind it.
            headers={"Cache-Control": "private, max-age=300"},
        )

    @router.post("/artifacts/{artifact_id}/review-package/decision")
    def record_review_decision(
        artifact_id: str,
        body: ReviewDecisionRequest,
        institution_id: str = Depends(tenant),
    ) -> dict:
        """Approve or reject the built package; returns the resulting review state."""

        return workflow.decide(
            institution_id,
            artifact_id,
            decision=body.decision,
            reason=body.reason,
            reviewer=body.reviewer,
        ).to_dict()

    @router.get("/artifacts/{artifact_id}/review-package/review-state")
    def get_review_state(artifact_id: str, institution_id: str = Depends(tenant)) -> dict:
        return workflow.review_state(institution_id, artifact_id).to_dict()

    @router.post("/artifacts/{artifact_id}/review-package/drafts")
    def save_review_draft(
        artifact_id: str,
        body: ReviewDraftRequest,
        institution_id: str = Depends(tenant),
    ) -> dict:
        """Append a draft revision of the lesson order; the package is unchanged."""

        draft = workflow.save_draft(
            institution_id,
            artifact_id,
            sections=[
                SectionInput(section_id=section.section_id, script=section.script)
                for section in body.sections
            ],
            edited_by=body.edited_by,
        )
        return draft.to_dict()

    @router.get("/artifacts/{artifact_id}/review-package/drafts")
    def list_review_drafts(artifact_id: str, institution_id: str = Depends(tenant)) -> dict:
        drafts = workflow.list_drafts(institution_id, artifact_id)
        return {
            "artifact_id": artifact_id,
            "revisions": [draft.to_dict() for draft in drafts],
        }

    return router


class PublishRequest(BaseModel):
    """An optional attribution for the publication.

    Identity and roles are not implemented yet
    (``docs/security/IDENTITY_AUTHORIZATION_AND_TOKENS.md``), so this is
    attribution, **not** an authorization control — the same note as the review
    decision's ``reviewer``.
    """

    published_by: Optional[str] = Field(default=None, max_length=256)


def build_publication_router(
    service: PublicationService,
    tenant: Callable[..., str],
) -> APIRouter:
    """Routes for the atomic publication transition and published-version retrieval."""

    router = APIRouter()

    @router.post("/course-versions/{version_id}/publish")
    def publish_version(
        version_id: str,
        body: Optional[PublishRequest] = None,
        institution_id: str = Depends(tenant),
    ) -> dict:
        """Seal, index and commit an approved version; returns the publication.

        ``200`` whether the publication was created or replayed: the identity is
        the content, so a retry after a lost response returns the same
        publication with ``created: false`` (``DEC-RUNTIME-003``). ``409``
        ``PUBLICATION_BLOCKED`` carries the precise ``issue_code`` when the
        version is not approved, its approval is stale, the package fails its
        checksums, or the index version could not be established.
        """

        publication, created = service.publish(
            institution_id, version_id, published_by=body.published_by if body else None
        )
        return {**publication.to_dict(), "created": created}

    @router.get("/course-versions/{version_id}/publication")
    def get_version_publication(
        version_id: str,
        verify: bool = False,
        institution_id: str = Depends(tenant),
    ) -> dict:
        """The newest publication of a course version (``404`` when unpublished).

        ``?verify=true`` re-checks the pinned package against its seal and adds an
        ``integrity`` block; it reads the package bytes, so it is opt-in.
        """

        return service.publication_for_version(institution_id, version_id, verify=verify)

    @router.get("/publications/{publication_id}")
    def get_publication(
        publication_id: str,
        verify: bool = False,
        institution_id: str = Depends(tenant),
    ) -> dict:
        """One publication by identity — including a superseded one."""

        return service.get_publication(institution_id, publication_id, verify=verify)

    @router.get("/courses/{course_id}/publications")
    def list_publications(
        course_id: str,
        limit: int = 50,
        institution_id: str = Depends(tenant),
    ) -> dict:
        """A course's publication history, newest first (superseded ones included)."""

        return service.list_publications(institution_id, course_id, limit=limit)

    return router


__all__ = ["build_publication_router", "build_review_router"]

