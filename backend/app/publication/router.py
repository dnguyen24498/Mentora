"""HTTP surface for the teacher review preview and review actions (V0-007) and
for the atomic publication transition (V0-008).

The review needs the *lesson order*, which only the baseline package knows, so it
cannot be built from the V0-005 endpoints alone. Routes:

* ``POST /artifacts/{artifactId}/review-package`` — build (idempotent, the
  expensive path: it renders) and return the review projection.
* ``GET  /artifacts/{artifactId}/review-package`` — project the *stored* package
  (cheap, no rendering); ``404`` when it has not been built yet.
* ``GET  /artifacts/{artifactId}/review-package/renders/{order}`` — one slide's
  packaged fallback render, served from the package with an authenticated request,
  so the browser never needs an unauthenticated ``<img src>``.
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
* ``POST /artifacts/{artifactId}/auto-publish`` — the upload shortcut: build the
  package, auto-approve it **only when the policy says auto-allowed**, and
  publish it as the uploading teacher. A human-required package is returned
  unpublished for Teacher Studio.

Every route resolves a principal (``app/api/security.py``) and the tenant comes from
it. Review and publication writes are **teacher** capabilities: a student token is
refused with ``403`` ``INSUFFICIENT_SCOPE``, and because the request is authenticated
the browser can fetch renders through JS and turn them into blob URLs.
"""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from app.api.security import ApiSecurity
from app.common.errors import NotFoundError
from app.identity.models import Principal, Scope
from app.publication.auto import AutoPublicationService
from app.publication.draft import SectionInput
from app.publication.review import ReviewService
from app.publication.service import PublicationService
from app.publication.workflow import ReviewWorkflow


class ReviewDecisionRequest(BaseModel):
    """An approve/reject action on the built package."""

    #: ``APPROVE`` or ``REJECT``. Rejection additionally requires ``reason``.
    decision: Literal["APPROVE", "REJECT"]
    reason: Optional[str] = Field(default=None, max_length=4000)
    #: Attribution only. Authorization is the session's ``review:write`` scope
    #: (V0-021); this field records *who* in a human sense and is never consulted
    #: to decide whether the action is allowed.
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
    security: ApiSecurity,
) -> APIRouter:
    router = APIRouter()
    require = security.require

    @router.post("/artifacts/{artifact_id}/review-package")
    def build_review_package(
        artifact_id: str, principal: Principal = Depends(require(Scope.REVIEW_WRITE))
    ) -> dict:
        """Build (or rebuild) the package and return the review view."""

        return review_service.build_review(
            principal.institution_id, artifact_id
        ).to_dict()

    @router.get("/artifacts/{artifact_id}/review-package")
    def get_review_package(
        artifact_id: str, principal: Principal = Depends(require(Scope.CONTENT_READ))
    ) -> dict:
        review = review_service.load_review(principal.institution_id, artifact_id)
        if review is None:
            raise NotFoundError(
                f"no package has been built for artifact {artifact_id}; "
                "POST to this path to build it"
            )
        return review.to_dict()

    @router.get("/artifacts/{artifact_id}/review-package/renders/{order}")
    def get_review_render(
        artifact_id: str,
        order: int,
        principal: Principal = Depends(require(Scope.CONTENT_READ)),
    ) -> Response:
        payload = review_service.scene_svg(
            principal.institution_id, artifact_id, order
        )
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
        principal: Principal = Depends(require(Scope.REVIEW_WRITE)),
    ) -> dict:
        """Approve or reject the built package; returns the resulting review state."""

        return workflow.decide(
            principal.institution_id,
            artifact_id,
            decision=body.decision,
            reason=body.reason,
            reviewer=body.reviewer or principal.email or principal.account_id,
        ).to_dict()

    @router.get("/artifacts/{artifact_id}/review-package/review-state")
    def get_review_state(
        artifact_id: str, principal: Principal = Depends(require(Scope.CONTENT_READ))
    ) -> dict:
        return workflow.review_state(principal.institution_id, artifact_id).to_dict()

    @router.post("/artifacts/{artifact_id}/review-package/drafts")
    def save_review_draft(
        artifact_id: str,
        body: ReviewDraftRequest,
        principal: Principal = Depends(require(Scope.REVIEW_WRITE)),
    ) -> dict:
        """Append a draft revision of the lesson order; the package is unchanged."""

        draft = workflow.save_draft(
            principal.institution_id,
            artifact_id,
            sections=[
                SectionInput(section_id=section.section_id, script=section.script)
                for section in body.sections
            ],
            edited_by=body.edited_by or principal.email or principal.account_id,
        )
        return draft.to_dict()

    @router.get("/artifacts/{artifact_id}/review-package/drafts")
    def list_review_drafts(
        artifact_id: str, principal: Principal = Depends(require(Scope.CONTENT_READ))
    ) -> dict:
        drafts = workflow.list_drafts(principal.institution_id, artifact_id)
        return {
            "artifact_id": artifact_id,
            "revisions": [draft.to_dict() for draft in drafts],
        }

    return router


class PublishRequest(BaseModel):
    """An optional attribution for the publication.

    Authorization is the session's ``publication:write`` scope (V0-021); this field
    is attribution, not an authorization control — the same note as the review
    decision's ``reviewer``.
    """

    published_by: Optional[str] = Field(default=None, max_length=256)


def build_publication_router(
    service: PublicationService,
    auto_service: AutoPublicationService,
    security: ApiSecurity,
) -> APIRouter:
    """Routes for the atomic publication transition and published-version retrieval."""

    router = APIRouter()
    require = security.require
    require_all = security.require_all

    @router.post("/artifacts/{artifact_id}/auto-publish")
    def auto_publish_artifact(
        artifact_id: str,
        principal: Principal = Depends(
            require_all(Scope.CONTENT_WRITE, Scope.REVIEW_WRITE, Scope.PUBLICATION_WRITE)
        ),
    ) -> dict:
        """Publish an uploaded deck when the review policy says it is auto-allowed.

        This is the Library's upload path: it builds the package, records the
        uploading teacher's approval, and runs the atomic publication transition.
        A package marked ``REVIEW_REQUIRED`` is **not** approved automatically —
        the response says ``published: false`` and leaves it in Teacher Studio. A
        blocking fidelity failure is refused by the package builder (``409``).
        Idempotent on the content: a replay returns the same publication with
        ``created: false``.
        """

        attribution = (
            principal.email or principal.account_id or principal.institution_id
        )
        return auto_service.publish(
            principal.institution_id,
            artifact_id,
            published_by=attribution,
        ).to_dict()

    @router.post("/course-versions/{version_id}/publish")
    def publish_version(
        version_id: str,
        body: Optional[PublishRequest] = None,
        principal: Principal = Depends(require(Scope.PUBLICATION_WRITE)),
    ) -> dict:
        """Seal, index and commit an approved version; returns the publication.

        ``200`` whether the publication was created or replayed: the identity is
        the content, so a retry after a lost response returns the same
        publication with ``created: false`` (``DEC-RUNTIME-003``). ``409``
        ``PUBLICATION_BLOCKED`` carries the precise ``issue_code`` when the
        version is not approved, its approval is stale, the package fails its
        checksums, or the index version could not be established.
        """

        attribution = (body.published_by if body else None) or principal.email
        publication, created = service.publish(
            principal.institution_id, version_id, published_by=attribution
        )
        return {**publication.to_dict(), "created": created}

    @router.get("/course-versions/{version_id}/publication")
    def get_version_publication(
        version_id: str,
        verify: bool = False,
        principal: Principal = Depends(require(Scope.CONTENT_READ)),
    ) -> dict:
        """The newest publication of a course version (``404`` when unpublished).

        ``?verify=true`` re-checks the pinned package against its seal and adds an
        ``integrity`` block; it reads the package bytes, so it is opt-in.
        """

        return service.publication_for_version(
            principal.institution_id, version_id, verify=verify
        )

    @router.get("/publications/{publication_id}")
    def get_publication(
        publication_id: str,
        verify: bool = False,
        principal: Principal = Depends(require(Scope.CONTENT_READ)),
    ) -> dict:
        """One publication by identity — including a superseded one."""

        return service.get_publication(
            principal.institution_id, publication_id, verify=verify
        )

    @router.get("/courses/{course_id}/publications")
    def list_publications(
        course_id: str,
        limit: int = 50,
        principal: Principal = Depends(require(Scope.CONTENT_READ)),
    ) -> dict:
        """A course's publication history, newest first (superseded ones included)."""

        return service.list_publications(
            principal.institution_id, course_id, limit=limit
        )

    return router


__all__ = ["build_publication_router", "build_review_router"]
