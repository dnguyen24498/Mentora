"""Tenant-scoped persistence for review decisions and draft revisions (V0-007).

Every read and write is scoped by ``institution_id``, and the artifact/version
foreign keys make a decision or a draft impossible without a real course version
to attach it to. These tables hold *state about* an immutable package; nothing
here can reach the package bytes (``DEC-CONTENT-005``).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.courses.models import CourseVersionStatus, SourceArtifact
from app.db.database import transaction
from app.publication.draft import ISSUE_REVISION_CONFLICT, DraftError
from app.publication.models import (
    PUBLICATION_STATE_PUBLISHED,
    PUBLICATION_STATE_SUPERSEDED,
    DraftSection,
    IndexVersionRecord,
    Publication,
    ReviewDecision,
    ReviewDraft,
    sections_to_json,
)
from app.publication.outbox import (
    PUBLICATION_AGGREGATE_TYPE,
    PUBLICATION_EVENT_TYPE,
    OutboxEvent,
    publication_event_payload,
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


class CommitConflict(Exception):
    """Internal: the commit transaction lost a race, so it must be re-read.

    Raised by :meth:`PublicationRepository.commit` (after its transaction rolled
    back). :class:`~app.publication.service.PublicationService` turns it into the
    winner's publication, or a classified ``COMMIT_CONFLICT`` when there is none.
    """


class PublicationRepository:
    """Tenant-scoped persistence for the atomic publication transition (V0-008).

    Three tables are written by exactly one method, :meth:`commit`, inside one
    transaction: the knowledge-index version record, the publication row, and the
    outbox event — plus the course version's status change and the supersede of
    any older publication of the same course. That single commit point is what
    makes "Partial failure never exposes published version" true: every read here
    only ever sees rows that transaction wrote completely.

    Nothing in this class writes to the object store. A published package's bytes
    are owned by the compiler stage; a publication only *pins* them.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # -- reads ----------------------------------------------------------------------
    def find_artifact_for_version(
        self, institution_id: str, version_id: str
    ) -> Optional[SourceArtifact]:
        """The source artifact a course version was uploaded as, or ``None``.

        ``CourseRepository`` is keyed by artifact, and the publication endpoint is
        addressed by course version, so this is the one lookup that joins the two
        owners (read-only).
        """

        row = self._conn.execute(
            "SELECT * FROM source_artifacts WHERE institution_id = ? AND version_id = ?",
            (institution_id, version_id),
        ).fetchone()
        return SourceArtifact.from_row(row) if row else None

    def find_publication(
        self, institution_id: str, version_id: str, content_package_version: str
    ) -> Optional[Publication]:
        """The publication of this exact content version, if there is one.

        This is the idempotency key of the whole transition: publishing the same
        course version *and* the same content version twice returns the first
        publication instead of creating a second one (``DEC-RUNTIME-003``).
        """

        row = self._conn.execute(
            "SELECT * FROM publications "
            "WHERE institution_id = ? AND version_id = ? AND content_package_version = ?",
            (institution_id, version_id, content_package_version),
        ).fetchone()
        return Publication.from_row(row) if row else None

    def latest_publication_for_version(
        self, institution_id: str, version_id: str
    ) -> Optional[Publication]:
        """The newest publication of a course version (current or superseded)."""

        row = self._conn.execute(
            "SELECT * FROM publications "
            "WHERE institution_id = ? AND version_id = ? "
            "ORDER BY created_at DESC, publication_id DESC LIMIT 1",
            (institution_id, version_id),
        ).fetchone()
        return Publication.from_row(row) if row else None

    def get_publication(self, institution_id: str, publication_id: str) -> Optional[Publication]:
        row = self._conn.execute(
            "SELECT * FROM publications WHERE institution_id = ? AND publication_id = ?",
            (institution_id, publication_id),
        ).fetchone()
        return Publication.from_row(row) if row else None

    def list_publications(
        self, institution_id: str, course_id: str, *, limit: int = 50
    ) -> list[Publication]:
        """Publication history of a course, newest first.

        Superseded publications are included on purpose: ``DEC-CONTENT-005`` pins
        *all* compatible versions for the sessions already running on them, so
        "read the old version" has to stay possible.
        """

        rows = self._conn.execute(
            "SELECT * FROM publications "
            "WHERE institution_id = ? AND course_id = ? "
            "ORDER BY created_at DESC, publication_id DESC LIMIT ?",
            (institution_id, course_id, max(1, min(int(limit), 500))),
        ).fetchall()
        return [Publication.from_row(row) for row in rows]

    def get_index_version(
        self, institution_id: str, version_id: str, content_package_version: str
    ) -> Optional[IndexVersionRecord]:
        row = self._conn.execute(
            "SELECT * FROM knowledge_index_versions "
            "WHERE institution_id = ? AND version_id = ? AND content_package_version = ?",
            (institution_id, version_id, content_package_version),
        ).fetchone()
        return IndexVersionRecord.from_row(row) if row else None

    def list_outbox(self, institution_id: str, aggregate_id: str) -> list[OutboxEvent]:
        """The events committed for one publication (oldest first)."""

        rows = self._conn.execute(
            "SELECT * FROM publication_outbox "
            "WHERE institution_id = ? AND aggregate_id = ? "
            "ORDER BY created_at, event_id",
            (institution_id, aggregate_id),
        ).fetchall()
        return [OutboxEvent.from_row(row) for row in rows]

    def count_outbox(self, institution_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS total FROM publication_outbox WHERE institution_id = ?",
            (institution_id,),
        ).fetchone()
        return int(row["total"])

    # -- the commit point -------------------------------------------------------------
    def commit(
        self,
        *,
        institution_id: str,
        course_id: str,
        version_id: str,
        course_version: int,
        artifact_id: str,
        package_id: str,
        content_package_version: str,
        lesson_plan_versions: tuple[str, ...],
        knowledge_index_version: str,
        teaching_graph_version: Optional[str],
        manifest_sha256: str,
        content_digest: str,
        file_count: int,
        total_bytes: int,
        index_version: str,
        index_status: str,
        index_source_digest: str,
        published_by: str,
    ) -> tuple[Publication, int]:
        """Commit ``INDEXING -> COMMITTING -> PUBLISHED`` in one transaction.

        Order inside the transaction is the order the invariants need:

        1. **expected-state guard** — flip ``course_versions.status`` only from
           ``APPROVED``. A ``rowcount`` of 0 means the version moved under us (a
           second publish, or a re-review), and the whole transaction aborts
           rather than publishing content nobody approved;
        2. **index-version record** — insert-or-reuse the ``(version,
           content_package_version)`` pin, so a retry cannot fork the identity
           ``DEC-DATA-005`` filters by;
        3. **publication row** — ``PUBLISHED``; ``UNIQUE`` catches a duplicate that
           raced past the guard;
        4. **outbox event** — the same transaction, so metadata and event cannot
           disagree;
        5. **supersede** — strictly older versions of the same course, and any
           other publication of this version, become ``SUPERSEDED``.

        Returns the publication and how many earlier ones it superseded (the
        supersede is a visible effect of this transaction, so it is reported
        rather than inferred by the caller).

        Raises :class:`CommitConflict` when the transaction lost a race (rolled
        back, nothing written); the service re-reads the winner.
        """

        publication_id = _new_id()
        index_version_id = _new_id()
        event_id = _new_id()
        now = _now()
        try:
            with transaction(self._conn):
                cur = self._conn.execute(
                    "UPDATE course_versions SET status = ? "
                    "WHERE version_id = ? AND institution_id = ? AND status = ?",
                    (
                        CourseVersionStatus.PUBLISHED.value,
                        version_id,
                        institution_id,
                        CourseVersionStatus.APPROVED.value,
                    ),
                )
                if cur.rowcount == 0:
                    raise CommitConflict("course version is no longer APPROVED")

                self._conn.execute(
                    "INSERT OR IGNORE INTO knowledge_index_versions "
                    "(index_version_id, institution_id, course_id, version_id, package_id, "
                    " content_package_version, index_version, status, source_digest, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        index_version_id,
                        institution_id,
                        course_id,
                        version_id,
                        package_id,
                        content_package_version,
                        index_version,
                        index_status,
                        index_source_digest,
                        now,
                    ),
                )
                pinned = self._conn.execute(
                    "SELECT index_version_id FROM knowledge_index_versions "
                    "WHERE institution_id = ? AND version_id = ? AND content_package_version = ?",
                    (institution_id, version_id, content_package_version),
                ).fetchone()
                index_version_id = pinned["index_version_id"]

                self._conn.execute(
                    "INSERT INTO publications "
                    "(publication_id, institution_id, course_id, version_id, course_version, "
                    " artifact_id, package_id, content_package_version, lesson_plan_versions, "
                    " knowledge_index_version, teaching_graph_version, index_version_id, "
                    " manifest_sha256, content_digest, file_count, total_bytes, state, "
                    " superseded_by, published_by, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)",
                    (
                        publication_id,
                        institution_id,
                        course_id,
                        version_id,
                        course_version,
                        artifact_id,
                        package_id,
                        content_package_version,
                        json.dumps(list(lesson_plan_versions)),
                        knowledge_index_version,
                        teaching_graph_version,
                        index_version_id,
                        manifest_sha256,
                        content_digest,
                        file_count,
                        total_bytes,
                        PUBLICATION_STATE_PUBLISHED,
                        published_by,
                        now,
                    ),
                )

                payload = publication_event_payload(
                    event_id=event_id,
                    occurred_at=now,
                    institution_id=institution_id,
                    course_id=course_id,
                    version_id=version_id,
                    course_version=course_version,
                    artifact_id=artifact_id,
                    publication_id=publication_id,
                    package_id=package_id,
                    content_package_version=content_package_version,
                    lesson_plan_versions=lesson_plan_versions,
                    knowledge_index_version=knowledge_index_version,
                    teaching_graph_version=teaching_graph_version,
                )
                self._conn.execute(
                    "INSERT INTO publication_outbox "
                    "(event_id, institution_id, aggregate_type, aggregate_id, event_type, "
                    " payload, created_at, dispatched_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                    (
                        event_id,
                        institution_id,
                        PUBLICATION_AGGREGATE_TYPE,
                        publication_id,
                        PUBLICATION_EVENT_TYPE,
                        json.dumps(payload, sort_keys=True, separators=(",", ":")),
                        now,
                    ),
                )

                superseded = self._conn.execute(
                    "UPDATE publications SET state = ?, superseded_by = ? "
                    "WHERE institution_id = ? AND course_id = ? AND publication_id != ? "
                    "AND state = ? AND (course_version < ? OR version_id = ?)",
                    (
                        PUBLICATION_STATE_SUPERSEDED,
                        publication_id,
                        institution_id,
                        course_id,
                        publication_id,
                        PUBLICATION_STATE_PUBLISHED,
                        course_version,
                        version_id,
                    ),
                ).rowcount
        except sqlite3.IntegrityError as exc:  # UNIQUE lost the race the guard missed
            raise CommitConflict(str(exc)) from exc

        row = self._conn.execute(
            "SELECT * FROM publications WHERE publication_id = ?", (publication_id,)
        ).fetchone()
        return Publication.from_row(row), int(superseded)


__all__ = ["CommitConflict", "PublicationRepository", "ReviewRepository"]
