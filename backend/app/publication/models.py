"""Review decision and draft-revision models (V0-007).

``docs/architecture/07_PUBLICATION_AND_REVIEW.md``: *"Review outcomes are
auto-allowed, human-required, or blocked."* A teacher records one of two
outcomes, approve or reject, and may propose simple edits to the lesson order
and its scripts.

Both are **state about** a package, never content of it:

* the decision records *who* accepted *which content version* and why (or why
  not), so an acceptance is auditable and cannot drift onto other content;
* a draft is a complete, materialised *proposed* lesson plan — the next revision
  of the lesson order — so a later publication step can consume it without the
  package, and nothing here can rewrite the immutable package
  (``DEC-CONTENT-005``).

Reviewer identity is client-supplied in V0: authentication and roles come from
``docs/security/IDENTITY_AUTHORIZATION_AND_TOKENS.md`` and are not implemented
yet, so ``reviewer``/``edited_by`` are attribution, **not** authorization.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

#: Review outcomes that can be recorded. ``docs/architecture/07_PUBLICATION_AND_REVIEW.md``
#: names the outcome space as auto-allowed / human-required / blocked; a human
#: acts on the "human-required" outcome by accepting or rejecting the document.
DECISION_APPROVE = "APPROVE"
DECISION_REJECT = "REJECT"


class ReviewDecisionKind(str, Enum):
    APPROVE = DECISION_APPROVE
    REJECT = DECISION_REJECT

    @classmethod
    def parse(cls, value: str) -> "ReviewDecisionKind":
        try:
            return cls(value)
        except ValueError as exc:  # pragma: no cover - the API validates first
            raise ValueError(f"unknown review decision {value!r}") from exc


@dataclass(frozen=True)
class ReviewDecision:
    """One recorded review outcome for one content version of one artifact."""

    decision_id: str
    institution_id: str
    artifact_id: str
    version_id: str
    package_id: str
    content_package_version: str
    decision: str
    reason: Optional[str]
    reviewer: str
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ReviewDecision":
        return cls(
            decision_id=row["decision_id"],
            institution_id=row["institution_id"],
            artifact_id=row["artifact_id"],
            version_id=row["version_id"],
            package_id=row["package_id"],
            content_package_version=row["content_package_version"],
            decision=row["decision"],
            reason=row["reason"],
            reviewer=row["reviewer"],
            created_at=row["created_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "artifact_id": self.artifact_id,
            "version_id": self.version_id,
            "package_id": self.package_id,
            "content_package_version": self.content_package_version,
            "decision": self.decision,
            "reason": self.reason,
            "reviewer": self.reviewer,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class DraftSection:
    """One lesson-order entry of a proposed revision.

    ``scene_id``/``scene_step_id``/``safe_markers``/``type`` are *inherited* from
    the package (``DEC-CONTENT-007``: reveal order is preserved as discrete
    steps), so a draft can only reorder and re-script — it can never invent or
    drop a scene reference.
    """

    order: int
    section_id: str
    type: str
    scene_id: Optional[str]
    scene_step_id: Optional[str]
    safe_markers: tuple[str, ...]
    script: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "section_id": self.section_id,
            "type": self.type,
            "scene_id": self.scene_id,
            "scene_step_id": self.scene_step_id,
            "safe_markers": list(self.safe_markers),
            "script": self.script,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DraftSection":
        return cls(
            order=int(payload["order"]),
            section_id=str(payload["section_id"]),
            type=str(payload.get("type", "")),
            scene_id=payload.get("scene_id"),
            scene_step_id=payload.get("scene_step_id"),
            safe_markers=tuple(str(m) for m in (payload.get("safe_markers") or [])),
            script=payload.get("script"),
        )


@dataclass(frozen=True)
class ReviewDraft:
    """One immutable revision of a proposed lesson order."""

    draft_id: str
    institution_id: str
    artifact_id: str
    version_id: str
    package_id: str
    content_package_version: str
    lesson_plan_version: Optional[str]
    revision: int
    sections: tuple[DraftSection, ...]
    edited_by: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "artifact_id": self.artifact_id,
            "version_id": self.version_id,
            "package_id": self.package_id,
            "content_package_version": self.content_package_version,
            "lesson_plan_version": self.lesson_plan_version,
            "revision": self.revision,
            "sections": [section.to_dict() for section in self.sections],
            "edited_by": self.edited_by,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ReviewDraft":
        sections = tuple(DraftSection.from_dict(item) for item in json.loads(row["sections"]))
        return cls(
            draft_id=row["draft_id"],
            institution_id=row["institution_id"],
            artifact_id=row["artifact_id"],
            version_id=row["version_id"],
            package_id=row["package_id"],
            content_package_version=row["content_package_version"],
            lesson_plan_version=row["lesson_plan_version"],
            revision=int(row["revision"]),
            sections=sections,
            edited_by=row["edited_by"],
            created_at=row["created_at"],
        )


def sections_to_json(sections: tuple[DraftSection, ...]) -> str:
    """Canonical JSON for a revision: sorted keys, no incidental whitespace."""

    return json.dumps(
        [section.to_dict() for section in sections], sort_keys=True, separators=(",", ":")
    )


# -- publication (V0-008) ---------------------------------------------------------
#
# ``docs/state-machines/PUBLICATION_STATE_MACHINE.md``:
# ``APPROVED -> SEALING -> INDEXING -> COMMITTING -> PUBLISHED -> SUPERSEDED/ARCHIVED``.
# The three middle states are *in-flight only*: a publication row is written once,
# by the single commit transaction, so a publication that is visible is complete
# and a partial one is invisible. That is this module's reconciliation of
# "Partial publication is invisible" — there is no persisted ``SEALING`` row that
# a reader could mistake for a published version, and no compensation to run for a
# stage that died before the commit point.

#: Stages the flow runs before its commit point, in order.
PUBLICATION_STAGE_SEALING = "SEALING"
PUBLICATION_STAGE_INDEXING = "INDEXING"
PUBLICATION_STAGE_COMMITTING = "COMMITTING"
PUBLICATION_STAGES: tuple[str, ...] = (
    PUBLICATION_STAGE_SEALING,
    PUBLICATION_STAGE_INDEXING,
    PUBLICATION_STAGE_COMMITTING,
)

#: Visible publication states — the only ones a retrieval can see.
PUBLICATION_STATE_PUBLISHED = "PUBLISHED"
PUBLICATION_STATE_SUPERSEDED = "SUPERSEDED"
PUBLICATION_VISIBLE_STATES: tuple[str, ...] = (
    PUBLICATION_STATE_PUBLISHED,
    PUBLICATION_STATE_SUPERSEDED,
)

#: The knowledge-index stage's outcome (``DEC-DATA-005`` pin). ``DEC-TECH-008``
#: (search/vector technology) is ``OPEN``, so V0 records the *identity* a
#: publication pins and builds no index content; ``UNINDEXED`` is the baseline
#: package's own declared state (``DEC-CONTENT-002``: usable without enrichment).
#: ``READY`` is what V0-014's builder will report.
INDEX_STATUS_UNINDEXED = "UNINDEXED"
INDEX_STATUS_READY = "READY"


@dataclass(frozen=True)
class Publication:
    """One committed publication: an immutable package plus its pinned versions.

    ``DEC-CONTENT-005``: the package a publication points at is never modified, and
    the publication records the **whole compatible version tuple**
    (``content_package_version`` + ``lesson_plan_versions`` +
    ``knowledge_index_version`` + ``teaching_graph_version``) so a runtime can pin
    exactly what a student receives. A correction publishes a new course version
    — with its own package — and *supersedes* the previous publication;
    ``superseded_by`` is a link, never a delete, so the pinned bytes stay readable
    for a session that already started on them.
    """

    publication_id: str
    institution_id: str
    course_id: str
    version_id: str
    course_version: int
    artifact_id: str
    package_id: str
    content_package_version: str
    lesson_plan_versions: tuple[str, ...]
    knowledge_index_version: str
    teaching_graph_version: Optional[str]
    index_version_id: str
    #: sha256 of the manifest envelope as sealed (provenance).
    manifest_sha256: str
    #: sha256 over the sealed content — what makes an overwrite detectable.
    content_digest: str
    file_count: int
    total_bytes: int
    state: str
    superseded_by: Optional[str]
    published_by: str
    created_at: str

    @property
    def superseded(self) -> bool:
        return self.state == PUBLICATION_STATE_SUPERSEDED

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Publication":
        return cls(
            publication_id=row["publication_id"],
            institution_id=row["institution_id"],
            course_id=row["course_id"],
            version_id=row["version_id"],
            course_version=int(row["course_version"]),
            artifact_id=row["artifact_id"],
            package_id=row["package_id"],
            content_package_version=row["content_package_version"],
            lesson_plan_versions=tuple(
                str(plan) for plan in json.loads(row["lesson_plan_versions"])
            ),
            knowledge_index_version=row["knowledge_index_version"],
            teaching_graph_version=row["teaching_graph_version"],
            index_version_id=row["index_version_id"],
            manifest_sha256=row["manifest_sha256"],
            content_digest=row["content_digest"],
            file_count=int(row["file_count"]),
            total_bytes=int(row["total_bytes"]),
            state=row["state"],
            superseded_by=row["superseded_by"],
            published_by=row["published_by"],
            created_at=row["created_at"],
        )

    def to_dict(self, *, integrity: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "publication_id": self.publication_id,
            "institution_id": self.institution_id,
            "course_id": self.course_id,
            "version_id": self.version_id,
            "course_version": self.course_version,
            "artifact_id": self.artifact_id,
            "package_id": self.package_id,
            "content_package_version": self.content_package_version,
            "lesson_plan_versions": list(self.lesson_plan_versions),
            "knowledge_index_version": self.knowledge_index_version,
            "teaching_graph_version": self.teaching_graph_version,
            "index_version_id": self.index_version_id,
            "package_prefix": f"packages/{self.package_id}",
            "manifest_sha256": self.manifest_sha256,
            "content_digest": self.content_digest,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
            "state": self.state,
            "superseded_by": self.superseded_by,
            "published_by": self.published_by,
            "created_at": self.created_at,
        }
        if integrity is not None:
            payload["integrity"] = integrity
        return payload


@dataclass(frozen=True)
class IndexVersion:
    """The value an :class:`~app.publication.index.IndexBuilder` returns.

    ``source_digest`` is the published content the identity is compatible with, so a
    retrieval that finds different content knows the pin does not apply.
    """

    index_version: str
    status: str
    source_digest: str


@dataclass(frozen=True)
class IndexVersionRecord:
    """The stored knowledge-index version record (``DEC-DATA-005``)."""

    index_version_id: str
    institution_id: str
    course_id: str
    version_id: str
    package_id: str
    content_package_version: str
    index_version: str
    status: str
    source_digest: str
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "IndexVersionRecord":
        return cls(
            index_version_id=row["index_version_id"],
            institution_id=row["institution_id"],
            course_id=row["course_id"],
            version_id=row["version_id"],
            package_id=row["package_id"],
            content_package_version=row["content_package_version"],
            index_version=row["index_version"],
            status=row["status"],
            source_digest=row["source_digest"],
            created_at=row["created_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "index_version_id": self.index_version_id,
            "version_id": self.version_id,
            "package_id": self.package_id,
            "content_package_version": self.content_package_version,
            "index_version": self.index_version,
            "status": self.status,
            "source_digest": self.source_digest,
            "created_at": self.created_at,
        }


__all__ = [
    "DECISION_APPROVE",
    "DECISION_REJECT",
    "INDEX_STATUS_READY",
    "INDEX_STATUS_UNINDEXED",
    "PUBLICATION_STAGES",
    "PUBLICATION_STAGE_COMMITTING",
    "PUBLICATION_STAGE_INDEXING",
    "PUBLICATION_STAGE_SEALING",
    "PUBLICATION_STATE_PUBLISHED",
    "PUBLICATION_STATE_SUPERSEDED",
    "PUBLICATION_VISIBLE_STATES",
    "DraftSection",
    "IndexVersion",
    "IndexVersionRecord",
    "Publication",
    "ReviewDecision",
    "ReviewDecisionKind",
    "ReviewDraft",
    "sections_to_json",
]
