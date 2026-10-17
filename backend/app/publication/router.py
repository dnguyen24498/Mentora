"""HTTP surface for the teacher review preview and review actions (V0-007).

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


__all__ = ["build_review_router"]

