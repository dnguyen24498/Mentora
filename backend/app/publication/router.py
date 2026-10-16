"""HTTP surface for the teacher review preview (V0-007, read-only).

The review needs the *lesson order*, which only the baseline package knows, so it
cannot be built from the V0-005 endpoints alone. Three routes:

* ``POST /artifacts/{artifactId}/review-package`` — build (idempotent, the
  expensive path: it renders) and return the review projection.
* ``GET  /artifacts/{artifactId}/review-package`` — project the *stored* package
  (cheap, no rendering); ``404`` when it has not been built yet.
* ``GET  /artifacts/{artifactId}/review-package/renders/{order}`` — one slide's
  packaged fallback render, served from the package with the tenant header, so the
  browser never needs an unauthenticated ``<img src>``.

Every route is tenant-scoped through ``X-Institution-Id``. Without the header the
request is rejected before reaching the service (422), which is exactly why the
frontend fetches renders through JS and turns them into blob URLs.
"""

from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, Depends, Response

from app.common.errors import NotFoundError
from app.publication.review import ReviewService


def build_review_router(
    review_service: ReviewService, tenant: Callable[..., str]
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
            # A packaged asset is immutable, so it is safe to cache privately.
            headers={"Cache-Control": "private, max-age=300"},
        )

    return router


__all__ = ["build_review_router"]
