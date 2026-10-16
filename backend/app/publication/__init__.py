"""Publication: teacher review and (V0-008) the atomic publication transition.

This package owns two things in V0-007:

* the **review projection** of a built Baseline Content Package — the render,
  text, notes, warnings/fidelity and lesson order a teacher inspects;
* the **review write path** — approve/reject, and draft lesson-order revisions.

Neither writes to a package. Content is immutable (``DEC-CONTENT-004`` /
``DEC-CONTENT-005``); a decision records *who accepted which content version*
and a draft is an appended *revision*, so a rejected or superseded proposal
never had to be undone. The publication transition
(``APPROVED`` → ``SEALING`` → ``INDEXING`` → ``COMMITTING`` → ``PUBLISHED``,
pinned index, outbox) is V0-008.
"""

from app.publication.draft import DraftDiff, DraftError, SectionInput, resolve_draft_sections
from app.publication.models import (
    DECISION_APPROVE,
    DECISION_REJECT,
    DraftSection,
    ReviewDecision,
    ReviewDecisionKind,
    ReviewDraft,
)
from app.publication.repository import ReviewRepository
from app.publication.review import (
    ReviewPackage,
    ReviewScene,
    ReviewSection,
    ReviewService,
)
from app.publication.workflow import ReviewState, ReviewWorkflow

__all__ = [
    "DECISION_APPROVE",
    "DECISION_REJECT",
    "DraftDiff",
    "DraftError",
    "DraftSection",
    "ReviewDecision",
    "ReviewDecisionKind",
    "ReviewDraft",
    "ReviewPackage",
    "ReviewRepository",
    "ReviewScene",
    "ReviewSection",
    "ReviewService",
    "ReviewState",
    "ReviewWorkflow",
    "SectionInput",
    "resolve_draft_sections",
]
