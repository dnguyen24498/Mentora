"""Publication: teacher review (V0-007) and the atomic publication transition (V0-008).

The package owns three things:

* the **review projection** of a built Baseline Content Package — the render,
  text, notes, warnings/fidelity and lesson order a teacher inspects;
* the **review write path** — approve/reject, and draft lesson-order revisions;
* the **publication transition** — ``APPROVED`` → ``SEALING`` → ``INDEXING`` →
  ``COMMITTING`` → ``PUBLISHED``, the pinned knowledge-index version, and the
  transactional outbox.

Neither the review nor the transition writes to a package. Content is immutable
(``DEC-CONTENT-004`` / ``DEC-CONTENT-005``); a decision records *who accepted
which content version*, a draft is an appended *revision*, and a publication only
*pins* bytes the compiler already wrote — so a rejected proposal or a failed
publication never had to be undone.
"""

from app.publication.draft import DraftDiff, DraftError, SectionInput, resolve_draft_sections
from app.publication.errors import PublicationError
from app.publication.index import BaselineIndexBuilder, IndexBuilder
from app.publication.models import (
    DECISION_APPROVE,
    DECISION_REJECT,
    INDEX_STATUS_READY,
    INDEX_STATUS_UNINDEXED,
    PUBLICATION_STAGE_COMMITTING,
    PUBLICATION_STAGE_INDEXING,
    PUBLICATION_STAGE_SEALING,
    PUBLICATION_STAGES,
    PUBLICATION_STATE_PUBLISHED,
    PUBLICATION_STATE_SUPERSEDED,
    PUBLICATION_VISIBLE_STATES,
    DraftSection,
    IndexVersion,
    IndexVersionRecord,
    Publication,
    ReviewDecision,
    ReviewDecisionKind,
    ReviewDraft,
)
from app.publication.outbox import (
    PUBLICATION_EVENT_TYPE,
    OutboxEvent,
    publication_event_payload,
)
from app.publication.repository import (
    CommitConflict,
    PublicationRepository,
    ReviewRepository,
)
from app.publication.review import (
    ReviewPackage,
    ReviewScene,
    ReviewSection,
    ReviewService,
)
from app.publication.seal import (
    INTEGRITY_MISMATCH,
    INTEGRITY_MISSING,
    INTEGRITY_VERIFIED,
    PackageIntegrity,
    PackageSeal,
    seal_package,
    verify_package,
)
from app.publication.service import PublicationService
from app.publication.telemetry import (
    PublicationMetrics,
    PublicationTelemetry,
    ReviewMetrics,
    ReviewTelemetry,
)
from app.publication.workflow import ReviewState, ReviewWorkflow

__all__ = [
    "INDEX_STATUS_READY",
    "INDEX_STATUS_UNINDEXED",
    "INTEGRITY_MISMATCH",
    "INTEGRITY_MISSING",
    "INTEGRITY_VERIFIED",
    "DECISION_APPROVE",
    "DECISION_REJECT",
    "PUBLICATION_EVENT_TYPE",
    "PUBLICATION_STAGES",
    "PUBLICATION_STAGE_COMMITTING",
    "PUBLICATION_STAGE_INDEXING",
    "PUBLICATION_STAGE_SEALING",
    "PUBLICATION_STATE_PUBLISHED",
    "PUBLICATION_STATE_SUPERSEDED",
    "PUBLICATION_VISIBLE_STATES",
    "BaselineIndexBuilder",
    "CommitConflict",
    "DraftDiff",
    "DraftError",
    "DraftSection",
    "IndexBuilder",
    "IndexVersion",
    "IndexVersionRecord",
    "OutboxEvent",
    "PackageIntegrity",
    "PackageSeal",
    "Publication",
    "PublicationError",
    "PublicationMetrics",
    "PublicationRepository",
    "PublicationService",
    "PublicationTelemetry",
    "ReviewDecision",
    "ReviewDecisionKind",
    "ReviewDraft",
    "ReviewMetrics",
    "ReviewPackage",
    "ReviewRepository",
    "ReviewScene",
    "ReviewSection",
    "ReviewService",
    "ReviewState",
    "ReviewTelemetry",
    "ReviewWorkflow",
    "SectionInput",
    "publication_event_payload",
    "resolve_draft_sections",
    "seal_package",
    "verify_package",
]
