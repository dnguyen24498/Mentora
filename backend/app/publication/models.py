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


__all__ = [
    "DECISION_APPROVE",
    "DECISION_REJECT",
    "DraftSection",
    "ReviewDecision",
    "ReviewDecisionKind",
    "ReviewDraft",
    "sections_to_json",
]
