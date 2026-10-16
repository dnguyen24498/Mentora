"""Publication: review and (V0-008) the atomic publication transition.

This package currently contains only the **read-only teacher review projection**
of a Baseline Content Package. Approve/reject, draft edits and the
``READY``/``REVIEW_REQUIRED`` → ``PUBLISHED`` transition are V0-008; they must
never mutate a built package (``DEC-CONTENT-004``: content is immutable).
"""

from app.publication.review import (
    ReviewPackage,
    ReviewScene,
    ReviewSection,
    ReviewService,
)

__all__ = [
    "ReviewPackage",
    "ReviewScene",
    "ReviewSection",
    "ReviewService",
]
