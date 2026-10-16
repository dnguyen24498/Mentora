"""Tenant-scoped persistence for review decisions and draft revisions (V0-007).

Every read and write is scoped by ``institution_id``, and the artifact/version
foreign keys make a decision or a draft impossible without a real course version
to attach it to. These tables hold *state about* an immutable package; nothing
here can reach the package bytes (``DEC-CONTENT-005``).
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.db.database import transaction
from app.publication.draft import ISSUE_REVISION_CONFLICT, DraftError
from app.publication.models import (
    DraftSection,
    ReviewDecision,
    ReviewDraft,
    sections_to_json,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


class ReviewRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # -- decisions ------------------------------------------------------------------
    def record_decision(
        self,
        *,
        institution_id: str,
        artifact_id: str,
        version_id: str,
        package_id: str,
        content_package_version: str,
        decision: str,
        reason: Optional[str],
        reviewer: str,
    ) -> ReviewDecision:
        """Append one decision. History is append-only; the newest row wins."""

        decision_id = _new_id()
        with transaction(self._conn):
            self._conn.execute(
                "INSERT INTO review_decisions "
                "(decision_id, institution_id, artifact_id, version_id, package_id, "
                " content_package_version, decision, reason, reviewer, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    decision_id,
                    institution_id,
                    artifact_id,
                    version_id,
                    package_id,
                    content_package_version,
                    decision,
                    reason,
                    reviewer,
                    _now(),
                ),
            )
        row = self._conn.execute(
            "SELECT * FROM review_decisions WHERE decision_id = ?", (decision_id,)
        ).fetchone()
        return ReviewDecision.from_row(row)

    def latest_decision(
        self, institution_id: str, artifact_id: str
    ) -> Optional[ReviewDecision]:
        """The current decision, or ``None`` when the artifact was never reviewed.

        Ties on ``created_at`` are broken by id so the result is deterministic
        (and PostgreSQL-compatible; ``rowid`` does not exist there).
        """

        row = self._conn.execute(
            "SELECT * FROM review_decisions "
            "WHERE institution_id = ? AND artifact_id = ? "
            "ORDER BY created_at DESC, decision_id DESC LIMIT 1",
            (institution_id, artifact_id),
        ).fetchone()
        return ReviewDecision.from_row(row) if row else None

    def list_decisions(self, institution_id: str, artifact_id: str) -> list[ReviewDecision]:
        rows = self._conn.execute(
            "SELECT * FROM review_decisions "
            "WHERE institution_id = ? AND artifact_id = ? "
            "ORDER BY created_at DESC, decision_id DESC",
            (institution_id, artifact_id),
        ).fetchall()
        return [ReviewDecision.from_row(row) for row in rows]

    # -- drafts ---------------------------------------------------------------------
    def create_draft(
        self,
        *,
        institution_id: str,
        artifact_id: str,
        version_id: str,
        package_id: str,
        content_package_version: str,
        lesson_plan_version: Optional[str],
        sections: tuple[DraftSection, ...],
        edited_by: str,
    ) -> ReviewDraft:
        """Append the next draft revision.

        The revision number is computed *inside* the write transaction, so two
        concurrent saves cannot silently branch the history: the loser violates
        ``UNIQUE (artifact_id, revision)`` and gets a stable ``REVISION_CONFLICT``
        instead of overwriting the winner.
        """

        draft_id = _new_id()
        try:
            with transaction(self._conn):
                revision = self._next_revision(institution_id, artifact_id)
                self._conn.execute(
                    "INSERT INTO review_drafts "
                    "(draft_id, institution_id, artifact_id, version_id, package_id, "
                    " content_package_version, lesson_plan_version, revision, sections, "
                    " edited_by, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        draft_id,
                        institution_id,
                        artifact_id,
                        version_id,
                        package_id,
                        content_package_version,
                        lesson_plan_version,
                        revision,
                        sections_to_json(sections),
                        edited_by,
                        _now(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise DraftError(
                "another draft revision was saved at the same time; reload and retry",
                issue_code=ISSUE_REVISION_CONFLICT,
                http_status=409,
            ) from exc

        stored = self._conn.execute(
            "SELECT * FROM review_drafts WHERE draft_id = ?", (draft_id,)
        ).fetchone()
        return ReviewDraft.from_row(stored)

    def latest_draft(self, institution_id: str, artifact_id: str) -> Optional[ReviewDraft]:
        row = self._conn.execute(
            "SELECT * FROM review_drafts "
            "WHERE institution_id = ? AND artifact_id = ? "
            "ORDER BY revision DESC LIMIT 1",
            (institution_id, artifact_id),
        ).fetchone()
        return ReviewDraft.from_row(row) if row else None

    def list_drafts(self, institution_id: str, artifact_id: str) -> list[ReviewDraft]:
        rows = self._conn.execute(
            "SELECT * FROM review_drafts "
            "WHERE institution_id = ? AND artifact_id = ? "
            "ORDER BY revision DESC",
            (institution_id, artifact_id),
        ).fetchall()
        return [ReviewDraft.from_row(row) for row in rows]

    def draft_count(self, institution_id: str, artifact_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS total FROM review_drafts "
            "WHERE institution_id = ? AND artifact_id = ?",
            (institution_id, artifact_id),
        ).fetchone()
        return int(row["total"])

    def _next_revision(self, institution_id: str, artifact_id: str) -> int:
        """Next revision number, read inside the write transaction.

        Kept as its own method so the append-only guarantee can be tested
        directly: overriding it forces the unique-constraint backstop.
        """

        row = self._conn.execute(
            "SELECT COALESCE(MAX(revision), 0) + 1 AS next FROM review_drafts "
            "WHERE institution_id = ? AND artifact_id = ?",
            (institution_id, artifact_id),
        ).fetchone()
        return int(row["next"])


__all__ = ["ReviewRepository"]
