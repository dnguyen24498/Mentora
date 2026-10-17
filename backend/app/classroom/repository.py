"""Tenant-scoped persistence for classes, enrollments, plans and sessions (V0-009).

Every read and write is scoped by ``institution_id``, in one place
(``docs/architecture/17_SECURITY_PRIVACY_AND_GOVERNANCE.md``). A class in another
institution raises rather than returning ``None``, and the foreign keys make a
session impossible without a real class and plan to hang from.

Two ownership rules shape the queries:

* the **plan, session and snapshot** are written by exactly one method,
  :meth:`ClassRepository.commit_start`, inside one transaction. That single commit
  point is what makes "a partial start is invisible" true: every read here only
  ever sees rows that transaction wrote completely, so ``PREPARING`` never has to
  exist as stored state.
* the **publication and its knowledge-index record** are owned by
  ``app.publication``. This repository *reads* them to resolve the pinned tuple
  (read-only projection, the same join ``PublicationRepository`` does the other way
  for ``source_artifacts``) and never writes them.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.common.errors import NotFoundError, TenantAccessError
from app.classroom.models import (
    CLASSROOM_STATE_SCHEDULED,
    BootstrapToken,
    Class,
    ClassroomSession,
    Enrollment,
    RuntimeSessionPlan,
    SessionSnapshot,
)
from app.db.database import transaction
from app.publication.models import (
    PUBLICATION_STATE_PUBLISHED,
    IndexVersionRecord,
    Publication,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


class CommitConflict(Exception):
    """Internal: the start transaction lost a race, so it must be re-read.

    Raised by :meth:`ClassRepository.commit_start` (after its transaction rolled
    back). :class:`~app.classroom.service.ClassroomService` turns it into the
    winner's session, or a classified ``COMMIT_CONFLICT`` when there is none.
    """


class ClassRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # -- classes ---------------------------------------------------------------------
    def create_class(
        self,
        *,
        institution_id: str,
        course_id: str,
        title: str,
        version_id: Optional[str] = None,
        scheduled_for: Optional[str] = None,
    ) -> Class:
        """Schedule a class. Its lifecycle starts in ``SCHEDULED``."""

        class_id = _new_id()
        with transaction(self._conn):
            self._conn.execute(
                "INSERT INTO classes "
                "(class_id, institution_id, course_id, title, version_id, scheduled_for, "
                " state, created_at, started_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    class_id,
                    institution_id,
                    course_id,
                    title,
                    version_id,
                    scheduled_for,
                    CLASSROOM_STATE_SCHEDULED,
                    _now(),
                ),
            )
        return self.get_class(institution_id, class_id)

    def get_class(self, institution_id: str, class_id: str) -> Class:
        """One class, or a classified failure.

        Fetched by id alone so the two refusals stay distinct: a class that does
        not exist is ``404``, and one that belongs to another institution is
        ``403`` — never a silent ``None`` that a caller could read as absence.
        """

        row = self._conn.execute(
            "SELECT * FROM classes WHERE class_id = ?", (class_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"class {class_id!r} not found")
        if row["institution_id"] != institution_id:
            raise TenantAccessError("class belongs to another institution")
        return Class.from_row(row)

    def list_classes(self, institution_id: str, *, limit: int = 100) -> list[Class]:
        rows = self._conn.execute(
            "SELECT * FROM classes WHERE institution_id = ? "
            "ORDER BY created_at DESC, class_id DESC LIMIT ?",
            (institution_id, max(1, min(int(limit), 500))),
        ).fetchall()
        return [Class.from_row(row) for row in rows]

    # -- enrollments -----------------------------------------------------------------
    def enroll(
        self, *, institution_id: str, class_id: str, student_id: str
    ) -> tuple[Enrollment, bool]:
        """Enroll a student. Idempotent: enrolling twice is one enrollment."""

        enrollment_id = _new_id()
        with transaction(self._conn):
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO enrollments "
                "(enrollment_id, institution_id, class_id, student_id, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (enrollment_id, institution_id, class_id, student_id, _now()),
            )
            created = cur.rowcount == 1
            row = self._conn.execute(
                "SELECT * FROM enrollments "
                "WHERE institution_id = ? AND class_id = ? AND student_id = ?",
                (institution_id, class_id, student_id),
            ).fetchone()
        return Enrollment.from_row(row), created

    def list_enrollments(self, institution_id: str, class_id: str) -> list[Enrollment]:
        rows = self._conn.execute(
            "SELECT * FROM enrollments WHERE institution_id = ? AND class_id = ? "
            "ORDER BY created_at DESC, enrollment_id DESC",
            (institution_id, class_id),
        ).fetchall()
        return [Enrollment.from_row(row) for row in rows]

    def is_enrolled(self, institution_id: str, class_id: str, student_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 AS present FROM enrollments "
            "WHERE institution_id = ? AND class_id = ? AND student_id = ?",
            (institution_id, class_id, student_id),
        ).fetchone()
        return row is not None

    # -- the pinned tuple: reads of publication-owned tables (read-only) --------------
    def find_current_publication_for_course(
        self, institution_id: str, course_id: str
    ) -> Optional[Publication]:
        """The course's current (non-superseded) publication, or ``None``.

        This is the one place a start resolves *which* version to pin when the
        class named none. It runs once, at start, and its result is written into
        the session plan; nothing at runtime asks this question again.
        """

        row = self._conn.execute(
            "SELECT * FROM publications "
            "WHERE institution_id = ? AND course_id = ? AND state = ? "
            "ORDER BY course_version DESC, created_at DESC, publication_id DESC LIMIT 1",
            (institution_id, course_id, PUBLICATION_STATE_PUBLISHED),
        ).fetchone()
        return Publication.from_row(row) if row else None

    def find_publication_for_version(
        self, institution_id: str, version_id: str
    ) -> Optional[Publication]:
        """The newest publication of one course version, superseded included.

        An explicit pin may legitimately name an older version: ``DEC-CONTENT-005``
        keeps it readable, and a class reproduced on it pins the same content a
        session that already ran on it did.
        """

        row = self._conn.execute(
            "SELECT * FROM publications "
            "WHERE institution_id = ? AND version_id = ? "
            "ORDER BY created_at DESC, publication_id DESC LIMIT 1",
            (institution_id, version_id),
        ).fetchone()
        return Publication.from_row(row) if row else None

    def get_index_version(
        self, institution_id: str, version_id: str, content_package_version: str
    ) -> Optional[IndexVersionRecord]:
        """The knowledge-index pin of a published content version (``DEC-DATA-005``)."""

        row = self._conn.execute(
            "SELECT * FROM knowledge_index_versions "
            "WHERE institution_id = ? AND version_id = ? AND content_package_version = ?",
            (institution_id, version_id, content_package_version),
        ).fetchone()
        return IndexVersionRecord.from_row(row) if row else None

    # -- sessions and plans ----------------------------------------------------------
    def get_session(self, institution_id: str, class_id: str) -> Optional[ClassroomSession]:
        row = self._conn.execute(
            "SELECT * FROM classroom_sessions "
            "WHERE institution_id = ? AND class_id = ?",
            (institution_id, class_id),
        ).fetchone()
        return ClassroomSession.from_row(row) if row else None

    def get_session_plan(
        self, institution_id: str, class_id: str
    ) -> Optional[RuntimeSessionPlan]:
        row = self._conn.execute(
            "SELECT * FROM runtime_session_plans "
            "WHERE institution_id = ? AND class_id = ?",
            (institution_id, class_id),
        ).fetchone()
        return RuntimeSessionPlan.from_row(row) if row else None

    def latest_snapshot(
        self, institution_id: str, session_id: str
    ) -> Optional[SessionSnapshot]:
        row = self._conn.execute(
            "SELECT * FROM session_snapshots "
            "WHERE institution_id = ? AND session_id = ? "
            "ORDER BY state_version DESC, snapshot_id DESC LIMIT 1",
            (institution_id, session_id),
        ).fetchone()
        return SessionSnapshot.from_row(row) if row else None

    def count_rows(self, institution_id: str) -> dict[str, int]:
        """Per-table row counts for one tenant (recovery/monitoring checks)."""

        counts: dict[str, int] = {}
        for label, table in (
            ("classes", "classes"),
            ("enrollments", "enrollments"),
            ("session_plans", "runtime_session_plans"),
            ("sessions", "classroom_sessions"),
            ("snapshots", "session_snapshots"),
            ("bootstrap_tokens", "bootstrap_tokens"),
        ):
            row = self._conn.execute(
                f"SELECT COUNT(*) AS total FROM {table} WHERE institution_id = ?",
                (institution_id,),
            ).fetchone()
            counts[label] = int(row["total"])
        return counts

    # -- the commit point ------------------------------------------------------------
    def commit_start(
        self,
        *,
        session_plan_id: str,
        session_id: str,
        snapshot_id: str,
        institution_id: str,
        class_id: str,
        course_id: str,
        version_id: str,
        course_version: int,
        publication_id: str,
        package_id: str,
        content_package_version: str,
        content_digest: str,
        lesson_plan_version: str,
        knowledge_index_version: str,
        index_version_id: str,
        index_source_digest: str,
        teaching_graph_version: Optional[str],
        assessment_version: Optional[str],
        model_routing_version: Optional[str],
        policy_version: str,
        capability_version: str,
        capabilities: dict,
        region: str,
        session_state: str,
        actor_epoch: int,
        state_version: int,
        event_sequence: int,
        snapshot: dict,
        snapshot_checksum: str,
    ) -> tuple[ClassroomSession, RuntimeSessionPlan, SessionSnapshot]:
        """Commit ``SCHEDULED -> PREPARING -> ACTIVE`` in one transaction.

        Ids come from the caller because the snapshot document *is about* the
        session: the service builds the initial state first and this method writes
        it, rather than writing a session and then describing it.

        Order inside the transaction is the order the foreign keys need:

        1. **expected-state guard** — move the class to ``ACTIVE`` only from
           ``SCHEDULED``. A ``rowcount`` of ``0`` means the class moved under us (a
           duplicate or concurrent start), and the transaction aborts instead of
           creating a second session;
        2. **plan** — the pinned tuple, written once (``UNIQUE (class_id)`` is the
           backstop if the guard is raced);
        3. **session** — ``ACTIVE`` at ``actor_epoch``/``state_version``, carrying the
           snapshot it was built from;
        4. **snapshot** — the initial document in the same transaction, so state and
           snapshot can never disagree.

        Returns the stored rows. Raises :class:`CommitConflict` when the transaction
        lost a race (rolled back, nothing written); the service re-reads the winner.
        """

        now = _now()
        try:
            with transaction(self._conn):
                cur = self._conn.execute(
                    "UPDATE classes SET state = ?, started_at = ? "
                    "WHERE class_id = ? AND institution_id = ? AND state = ?",
                    (session_state, now, class_id, institution_id, CLASSROOM_STATE_SCHEDULED),
                )
                if cur.rowcount == 0:
                    raise CommitConflict("class is no longer SCHEDULED")

                self._conn.execute(
                    "INSERT INTO runtime_session_plans "
                    "(session_plan_id, institution_id, class_id, course_id, version_id, "
                    " course_version, publication_id, package_id, content_package_version, "
                    " content_digest, lesson_plan_version, knowledge_index_version, "
                    " index_version_id, index_source_digest, teaching_graph_version, "
                    " assessment_version, model_routing_version, policy_version, "
                    " capability_version, capabilities, region, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        session_plan_id,
                        institution_id,
                        class_id,
                        course_id,
                        version_id,
                        course_version,
                        publication_id,
                        package_id,
                        content_package_version,
                        content_digest,
                        lesson_plan_version,
                        knowledge_index_version,
                        index_version_id,
                        index_source_digest,
                        teaching_graph_version,
                        assessment_version,
                        model_routing_version,
                        policy_version,
                        capability_version,
                        json.dumps(capabilities, sort_keys=True, separators=(",", ":")),
                        region,
                        now,
                    ),
                )

                self._conn.execute(
                    "INSERT INTO classroom_sessions "
                    "(session_id, institution_id, class_id, course_id, session_plan_id, state, "
                    " actor_epoch, state_version, event_sequence, snapshot_id, created_at, "
                    " started_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        session_id,
                        institution_id,
                        class_id,
                        course_id,
                        session_plan_id,
                        session_state,
                        actor_epoch,
                        state_version,
                        event_sequence,
                        snapshot_id,
                        now,
                        now,
                    ),
                )

                self._conn.execute(
                    "INSERT INTO session_snapshots "
                    "(snapshot_id, institution_id, session_id, class_id, schema_version, state, "
                    " state_version, event_sequence, actor_epoch, document, checksum, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        snapshot_id,
                        institution_id,
                        session_id,
                        class_id,
                        str(snapshot["schema_version"]),
                        session_state,
                        state_version,
                        event_sequence,
                        actor_epoch,
                        json.dumps(snapshot, sort_keys=True, separators=(",", ":")),
                        snapshot_checksum,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:  # UNIQUE lost the race the guard missed
            raise CommitConflict(str(exc)) from exc

        session = self.get_session(institution_id, class_id)
        plan = self.get_session_plan(institution_id, class_id)
        stored_snapshot = self.latest_snapshot(institution_id, session_id)
        assert session is not None and plan is not None and stored_snapshot is not None
        return session, plan, stored_snapshot

    # -- the per-transition commit point ---------------------------------------------
    def commit_transition(
        self,
        *,
        institution_id: str,
        class_id: str,
        session_id: str,
        expected_state: Optional[str],
        expected_state_version: int,
        actor_epoch: int,
        new_state: str,
        state_version: int,
        event_sequence: int,
        snapshot: dict,
        snapshot_checksum: str,
        snapshot_id: Optional[str] = None,
    ) -> tuple[ClassroomSession, SessionSnapshot]:
        """Commit one accepted aggregate transition (``DEC-RUNTIME-007`` fencing).

        The guarded ``UPDATE`` fences on the *pre-command* state, version and
        epoch: if another writer advanced the session between the aggregate's load
        and this commit, the ``rowcount`` is ``0`` and the transaction aborts —
        the loser reloads and re-handles rather than clobbering. Then the class
        mirrors the new state and the snapshot appends, all in one transaction, so
        a session's counters and its newest snapshot can never disagree
        (``DEC-DATA-004``).

        Raises :class:`CommitConflict` when the guard lost a race (rolled back,
        nothing written).
        """

        snapshot_id = snapshot_id or _new_id()
        now = _now()
        try:
            with transaction(self._conn):
                cur = self._conn.execute(
                    "UPDATE classroom_sessions "
                    "SET state = ?, state_version = ?, event_sequence = ?, snapshot_id = ? "
                    "WHERE session_id = ? AND institution_id = ? "
                    "  AND state = ? AND state_version = ? AND actor_epoch = ?",
                    (
                        new_state,
                        state_version,
                        event_sequence,
                        snapshot_id,
                        session_id,
                        institution_id,
                        expected_state,
                        expected_state_version,
                        actor_epoch,
                    ),
                )
                if cur.rowcount == 0:
                    raise CommitConflict("session state/version moved under the actor")

                self._conn.execute(
                    "UPDATE classes SET state = ? WHERE class_id = ? AND institution_id = ?",
                    (new_state, class_id, institution_id),
                )

                self._conn.execute(
                    "INSERT INTO session_snapshots "
                    "(snapshot_id, institution_id, session_id, class_id, schema_version, state, "
                    " state_version, event_sequence, actor_epoch, document, checksum, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        snapshot_id,
                        institution_id,
                        session_id,
                        class_id,
                        str(snapshot["schema_version"]),
                        new_state,
                        state_version,
                        event_sequence,
                        actor_epoch,
                        json.dumps(snapshot, sort_keys=True, separators=(",", ":")),
                        snapshot_checksum,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:  # UNIQUE(session_id, state_version) raced
            raise CommitConflict(str(exc)) from exc

        session = self.get_session(institution_id, class_id)
        stored_snapshot = self.latest_snapshot(institution_id, session_id)
        assert session is not None and stored_snapshot is not None
        return session, stored_snapshot

    # -- join credentials ------------------------------------------------------------
    def record_bootstrap_token(
        self,
        *,
        token_sha256: str,
        institution_id: str,
        class_id: str,
        session_id: str,
        student_id: str,
        actor_epoch: int,
        nonce: str,
        scopes: tuple[str, ...],
        issued_at: str,
        expires_at: str,
    ) -> BootstrapToken:
        """Store a join credential — its digest, never the token itself."""

        with transaction(self._conn):
            self._conn.execute(
                "INSERT INTO bootstrap_tokens "
                "(token_sha256, institution_id, class_id, session_id, student_id, actor_epoch, "
                " nonce, scopes, issued_at, expires_at, revoked_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    token_sha256,
                    institution_id,
                    class_id,
                    session_id,
                    student_id,
                    actor_epoch,
                    nonce,
                    json.dumps(list(scopes)),
                    issued_at,
                    expires_at,
                ),
            )
        record = self.get_bootstrap_token(token_sha256)
        assert record is not None
        return record

    def get_bootstrap_token(self, token_sha256: str) -> Optional[BootstrapToken]:
        """A stored token by digest (any tenant; the caller applies the boundary)."""

        row = self._conn.execute(
            "SELECT * FROM bootstrap_tokens WHERE token_sha256 = ?", (token_sha256,)
        ).fetchone()
        return BootstrapToken.from_row(row) if row else None

    def revoke_bootstrap_token(
        self, institution_id: str, token_sha256: str
    ) -> Optional[BootstrapToken]:
        """Terminally revoke a token (the other terminal path is its expiry)."""

        with transaction(self._conn):
            cur = self._conn.execute(
                "UPDATE bootstrap_tokens SET revoked_at = ? "
                "WHERE token_sha256 = ? AND institution_id = ? AND revoked_at IS NULL",
                (_now(), token_sha256, institution_id),
            )
            if cur.rowcount == 0:
                return None
        return self.get_bootstrap_token(token_sha256)

    def revoke_bootstrap_tokens(self, institution_id: str, session_id: str) -> int:
        """Terminally revoke every live join credential of a session (``CLASS_END``).

        Ending a class must not leak a join credential that can still authorise, so
        the end transition revokes the outstanding tokens in the same commit. Only
        the digest is updated; the raw token was never stored.
        """

        with transaction(self._conn):
            cur = self._conn.execute(
                "UPDATE bootstrap_tokens SET revoked_at = ? "
                "WHERE institution_id = ? AND session_id = ? AND revoked_at IS NULL",
                (_now(), institution_id, session_id),
            )
            return cur.rowcount


__all__ = ["ClassRepository", "CommitConflict"]
