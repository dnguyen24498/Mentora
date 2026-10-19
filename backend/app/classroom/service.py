"""Class start: resolve, pin, and snapshot the runtime tuple (V0-009).

``docs/sequences/CLASS_START.md``:

```text
Authorize -> resolve exact versions/policy -> home region -> acquire actor epoch
-> room -> warm baseline/capabilities -> initial snapshot -> ACTIVE.
```

V0-009 implements the schedule/start half of that flow and is explicit about the
parts it does not:

* **resolve exact versions/policy, home region, initial snapshot, ACTIVE** — this
  module. Resolution happens *once*, at start, and its result is written into the
  session plan. ``docs/architecture/03_DOMAIN_OWNERSHIP_AND_VERSIONING.md``
  forbids a runtime ``latest`` lookup, and the strongest form of that rule is
  structural: after the start transaction there is no code path that asks a
  publication question again, because the session reads its own pinned tuple.
* **acquire actor epoch** — the session pins the *initial* epoch (1). Claiming,
  fencing and transferring ownership across an actor failure is V1-002
  (``DEC-RUNTIME-007`` is honoured from the first value on by binding join
  credentials to it).
* **room** — media transport is the Media Plane's, and the SFU is out of scope:
  V0-009 issues the *join credential* the media plane will validate, and creates
  no room.

Three properties decide the shape of the module, and they mirror V0-008's:

* **A partial start is invisible.** ``PREPARING`` is in-flight only: the plan, the
  session, the initial snapshot and the class's ``SCHEDULED -> ACTIVE`` change
  commit in one transaction, so a failure at any earlier point leaves the class
  exactly as it was and a retry starts from a clean state. There is nothing to
  compensate (``DEC-RELIABILITY-002``).
* **A running session cannot be moved onto different content.** The plan is
  written once and has no update path; publishing a correction creates a new
  publication and a *new* class pins it, while this session keeps reading the
  bytes it pinned — including a publication that has since been superseded
  (``DEC-CONTENT-005``).
* **Duplicate start is a property, not a guard.** The identity is the class, so a
  repeated or concurrent start returns the first session with ``created: false``
  rather than a second one (``DEC-RUNTIME-003``).

The runtime never parses the source document (``DEC-CONTENT-001``): start reads the
*pinned package* (its manifest and lesson plan) and the pinned knowledge-index
record, and nothing else.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, NoReturn, Optional

from app.common.errors import NotFoundError, ValidationError
from app.classroom.aggregate import (
    COMMAND_CHECKPOINT,
    COMMAND_END,
    COMMAND_NAVIGATE,
    COMMAND_START,
    ClassroomAggregate,
    Command,
    CommandResult,
)
from app.classroom.catalog import RuntimeCatalog, capability_version
from app.classroom.errors import (
    ISSUE_COMMIT_CONFLICT,
    ISSUE_CONTENT_DIGEST_MISMATCH,
    ISSUE_INCOMPATIBLE_CONTENT,
    ISSUE_INCOMPATIBLE_INDEX,
    ISSUE_NOT_ENROLLED,
    ISSUE_NOT_STARTED,
    ISSUE_STALE_EPOCH,
    ISSUE_TOKEN_EXPIRED,
    ISSUE_TOKEN_REVOKED,
    ISSUE_TOKEN_UNKNOWN,
    ISSUE_VERSION_NOT_PUBLISHED,
    ISSUE_WRONG_STATE,
    ClassStartError,
    JoinDeniedError,
)
from app.classroom.models import (
    BOOTSTRAP_TOKEN_SCOPES,
    BOOTSTRAP_TOKEN_TTL_SECONDS,
    CLASSROOM_STATE_ACTIVE,
    CLASSROOM_STATE_SCHEDULED,
    INITIAL_ACTOR_EPOCH,
    INITIAL_EVENT_SEQUENCE,
    INITIAL_STATE_VERSION,
    BootstrapToken,
    Class,
    ClassroomSession,
    Enrollment,
    IssuedBootstrapToken,
    RuntimeSessionPlan,
    SessionSnapshot,
)
from app.classroom.repository import ClassRepository, CommitConflict
from app.classroom.scene_source import PinnedScene, PinnedSceneSource, PinnedSceneSummary
from app.classroom.snapshot import (
    first_lesson_position,
    snapshot_checksum,
    validate_snapshot,
)
from app.classroom.telemetry import ClassroomTelemetry
from app.compiler.package_builder.layout import package_prefix
from app.compiler.package_builder.loader import read_package
from app.courses.repository import CourseRepository
from app.publication.models import Publication
from app.publication.seal import INTEGRITY_VERIFIED, verify_package
from app.storage.object_store import ObjectStore

#: ``docs/architecture/19_RELIABILITY_SLO_AND_BACKPRESSURE.md`` naming of the one
#: long step: reading and re-verifying the pinned package before the commit point.
STAGE_RESOLVING = "RESOLVING"
STAGE_VERIFYING = "VERIFYING"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class SessionStartResult:
    """What a start (or a replayed start) returns."""

    scheduled_class: Class
    session: ClassroomSession
    plan: RuntimeSessionPlan
    snapshot: SessionSnapshot
    created: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "class": self.scheduled_class.to_dict(),
            "session": self.session.to_dict(),
            "session_plan": self.plan.to_dict(),
            "snapshot": self.snapshot.to_dict(),
            "created": self.created,
        }


@dataclass(frozen=True)
class CommandOutcome:
    """What a command dispatch returns: its verdict plus the durable rows.

    A refused command has ``session``/``snapshot`` ``None`` (nothing was written);
    an accepted one carries the updated session and the snapshot the transition
    appended (``DEC-DATA-004``: state and snapshot commit together).
    """

    result: CommandResult
    session: Optional[ClassroomSession]
    snapshot: Optional[SessionSnapshot]

    def to_dict(self) -> dict[str, Any]:
        return {
            "result": self.result.to_dict(),
            "session": self.session.to_dict() if self.session is not None else None,
            "snapshot": self.snapshot.to_dict() if self.snapshot is not None else None,
        }


class ClassroomService:
    """Schedules classes, starts sessions by pinning an exact tuple, and authorizes joins."""

    def __init__(
        self,
        course_repository: CourseRepository,
        repository: ClassRepository,
        object_store: ObjectStore,
        *,
        catalog: RuntimeCatalog,
        capability_probe: Callable[[], Mapping[str, Any]],
        telemetry: Optional[ClassroomTelemetry] = None,
        token_ttl_seconds: int = BOOTSTRAP_TOKEN_TTL_SECONDS,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._courses = course_repository
        self._repository = repository
        self._object_store = object_store
        self._scenes = PinnedSceneSource(object_store)
        self._catalog = catalog
        self._capability_probe = capability_probe
        self._telemetry = telemetry or ClassroomTelemetry()
        self._token_ttl = timedelta(seconds=max(1, int(token_ttl_seconds)))
        self._clock = clock or _utcnow
        # The in-process aggregate registry (DEC-RUNTIME-001: one owner per class).
        # Idempotency memory lives in the aggregate, so a repeated command returns
        # the original verdict without a second effect. The durable store is still
        # the truth; the guarded transition commits fence any other process.
        self._aggregates: dict[str, ClassroomAggregate] = {}
        self._locks: dict[str, threading.Lock] = {}

    @property
    def telemetry(self) -> ClassroomTelemetry:
        return self._telemetry

    # -- scheduling ------------------------------------------------------------------
    def schedule_class(
        self,
        institution_id: str,
        course_id: str,
        *,
        title: Optional[str] = None,
        version_id: Optional[str] = None,
        scheduled_for: Optional[str] = None,
    ) -> Class:
        """Schedule a teaching occurrence against a course (optionally a version).

        Scheduling records intent only. It pins nothing: a version named here is
        validated as *this course's* (so a typo cannot attach a foreign version),
        but whether it is published is decided at start, where the refusal can say
        exactly why the tuple cannot be resolved.

        ``scheduled_for`` is recorded, never enforced. An automatic start would be a
        durable workflow/scheduler, and ``DEC-TECH-003`` is ``OPEN`` — so there is
        no timer, and ``start`` is the explicit, idempotent transition.
        """

        course = self._courses.get_course(institution_id, course_id)
        if version_id is not None:
            version = self._courses.get_version(institution_id, version_id)
            if version.course_id != course.course_id:
                raise ValidationError(
                    f"course version {version_id!r} does not belong to course "
                    f"{course_id!r}"
                )
        scheduled_class = self._repository.create_class(
            institution_id=institution_id,
            course_id=course_id,
            title=(title or "").strip() or course.title,
            version_id=version_id,
            scheduled_for=self._normalize_scheduled_for(scheduled_for),
        )
        self._telemetry.record_scheduled(
            institution_id=institution_id,
            class_id=scheduled_class.class_id,
            course_id=course_id,
            title=scheduled_class.title,
            version_id=version_id,
            scheduled_for=scheduled_class.scheduled_for,
        )
        return scheduled_class

    def get_class(self, institution_id: str, class_id: str) -> Class:
        return self._repository.get_class(institution_id, class_id)

    def list_classes(self, institution_id: str, *, limit: int = 100) -> list[Class]:
        return self._repository.list_classes(institution_id, limit=limit)

    def class_view(self, institution_id: str, class_id: str) -> dict[str, Any]:
        """The class with its session and pinned tuple (both absent before start)."""

        scheduled_class = self._repository.get_class(institution_id, class_id)
        session = self._repository.get_session(institution_id, class_id)
        plan = self._repository.get_session_plan(institution_id, class_id)
        return {
            "class": scheduled_class.to_dict(),
            "session": session.to_dict() if session is not None else None,
            "session_plan": plan.to_dict() if plan is not None else None,
        }

    # -- start -----------------------------------------------------------------------
    def start_class(self, institution_id: str, class_id: str) -> SessionStartResult:
        """``SCHEDULED -> PREPARING -> ACTIVE``: pin the tuple and snapshot it.

        Raises :class:`~app.classroom.errors.ClassStartError` (``409``
        ``CLASS_NOT_READY`` with an ``issue_code``) when the exact tuple cannot be
        resolved or is not usable. Every refusal happens before the commit point, so
        nothing is written and the class stays ``SCHEDULED``.
        """

        scheduled_class = self._repository.get_class(institution_id, class_id)

        # Idempotency first: a replay arrives when the class is already ACTIVE,
        # which is not the SCHEDULED state the transition's precondition names.
        existing = self._repository.get_session(institution_id, class_id)
        if existing is not None:
            plan = self._repository.get_session_plan(institution_id, class_id)
            snapshot = self._repository.latest_snapshot(institution_id, existing.session_id)
            assert plan is not None and snapshot is not None, "a session has its plan and snapshot"
            self._record_started(scheduled_class, existing, plan, created=False)
            return SessionStartResult(scheduled_class, existing, plan, snapshot, created=False)

        if scheduled_class.state != CLASSROOM_STATE_SCHEDULED:
            self._block(
                scheduled_class, STAGE_RESOLVING, ISSUE_WRONG_STATE,
                f"class {class_id!r} is {scheduled_class.state}, not {CLASSROOM_STATE_SCHEDULED}",
            )

        publication = self._resolve_publication(institution_id, scheduled_class)
        loaded = self._load_pinned_package(scheduled_class, publication)
        lesson = self._resolve_lesson(scheduled_class, publication, loaded)
        index = self._resolve_index(institution_id, publication)
        defaults = self._catalog.defaults()
        probe = dict(self._capability_probe())
        identity = dict(probe.get("identity") or {})

        session_plan_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        snapshot_id = str(uuid.uuid4())
        plan = RuntimeSessionPlan(
            session_plan_id=session_plan_id,
            institution_id=institution_id,
            class_id=class_id,
            course_id=publication.course_id,
            version_id=publication.version_id,
            course_version=publication.course_version,
            publication_id=publication.publication_id,
            package_id=publication.package_id,
            content_package_version=publication.content_package_version,
            content_digest=publication.content_digest,
            lesson_plan_version=str(lesson["lesson_plan_version"]),
            knowledge_index_version=publication.knowledge_index_version,
            index_version_id=publication.index_version_id,
            index_source_digest=index.source_digest,
            teaching_graph_version=publication.teaching_graph_version,
            # Named absences: V0 has neither subsystem, and the canonical tuple
            # names both, so they are pinned as null rather than omitted.
            assessment_version=None,
            model_routing_version=None,
            policy_version=defaults.policy_version,
            capability_version=capability_version(identity),
            capabilities={"identity": identity, "support": dict(probe.get("support") or {})},
            region=defaults.region,
            created_at="",
        )
        aggregate = ClassroomAggregate.session(
            plan=plan, session_id=session_id, lesson=lesson, clock=self._clock
        )
        started = aggregate.handle(Command.create(COMMAND_START))
        assert started.accepted, "a freshly built aggregate always accepts START"
        document = aggregate.snapshot()
        checksum = snapshot_checksum(document)

        try:
            session, stored_plan, snapshot = self._repository.commit_start(
                session_plan_id=session_plan_id,
                session_id=session_id,
                snapshot_id=snapshot_id,
                institution_id=institution_id,
                class_id=class_id,
                course_id=plan.course_id,
                version_id=plan.version_id,
                course_version=plan.course_version,
                publication_id=plan.publication_id,
                package_id=plan.package_id,
                content_package_version=plan.content_package_version,
                content_digest=plan.content_digest,
                lesson_plan_version=plan.lesson_plan_version,
                knowledge_index_version=plan.knowledge_index_version,
                index_version_id=plan.index_version_id,
                index_source_digest=plan.index_source_digest,
                teaching_graph_version=plan.teaching_graph_version,
                assessment_version=plan.assessment_version,
                model_routing_version=plan.model_routing_version,
                policy_version=plan.policy_version,
                capability_version=plan.capability_version,
                capabilities=plan.capabilities,
                region=plan.region,
                session_state=CLASSROOM_STATE_ACTIVE,
                actor_epoch=INITIAL_ACTOR_EPOCH,
                state_version=INITIAL_STATE_VERSION,
                event_sequence=INITIAL_EVENT_SEQUENCE,
                snapshot=document,
                snapshot_checksum=checksum,
            )
            created = True
            self._aggregates[class_id] = aggregate
        except CommitConflict:
            # Someone else started this class between our read and our write. Their
            # session is the answer to our request.
            winner = self._repository.get_session(institution_id, class_id)
            if winner is None:
                self._block(
                    scheduled_class, STAGE_RESOLVING, ISSUE_COMMIT_CONFLICT,
                    "another start won the commit for this class; reload and retry",
                )
            plan = self._repository.get_session_plan(institution_id, class_id)
            snapshot = self._repository.latest_snapshot(institution_id, winner.session_id)
            assert plan is not None and snapshot is not None
            self._record_started(scheduled_class, winner, plan, created=False)
            return SessionStartResult(
                self._repository.get_class(institution_id, class_id), winner, plan, snapshot,
                created=False,
            )

        result_class = self._repository.get_class(institution_id, class_id)
        self._record_started(result_class, session, stored_plan, created=created)
        return SessionStartResult(result_class, session, stored_plan, snapshot, created=created)

    def get_snapshot(self, institution_id: str, class_id: str) -> SessionSnapshot:
        """The authoritative snapshot, validated before it is handed out.

        ``DEC-DATA-004`` / the recovery invariants: a snapshot is validated (schema
        version *and* checksum) before it is used, so a damaged one is refused
        rather than replayed.
        """

        session = self._repository.get_session(institution_id, class_id)
        if session is None:
            self._repository.get_class(institution_id, class_id)  # 404/403 first
            raise NotFoundError(f"class {class_id!r} has not started")
        snapshot = self._repository.latest_snapshot(institution_id, session.session_id)
        if snapshot is None:  # pragma: no cover - the start transaction writes one
            raise NotFoundError(f"session {session.session_id!r} has no snapshot")
        validate_snapshot(
            snapshot.document,
            schema_version=snapshot.schema_version,
            checksum=snapshot.checksum,
        )
        self._telemetry.record_snapshot_read(
            institution_id=institution_id,
            class_id=class_id,
            session_id=session.session_id,
            state_version=snapshot.state_version,
        )
        return snapshot

    def pinned_scene(self, institution_id: str, class_id: str, order: int) -> PinnedScene:
        """The slide a running session is presenting, from the package it pinned.

        The read resolves the session's own ``RuntimeSessionPlan`` — never the
        course's *current* publication — so publishing a correction mid-lesson
        changes nothing a student sees (``DEC-CONTENT-005``: a published artifact is
        immutable and an active session pins all compatible versions). A class that
        has not started has no plan and therefore no scene: that is a ``404``, not an
        empty slide.
        """

        plan = self._pinned_plan(institution_id, class_id)
        scene = self._scenes.scene(plan.package_id, order)
        self._telemetry.record_scene_read(
            institution_id=institution_id,
            class_id=class_id,
            session_id=plan.session_plan_id,
            package_id=plan.package_id,
            order=order,
            scene_id=scene.scene_id,
            byte_size=scene.byte_size,
        )
        return scene

    def pinned_scenes(
        self, institution_id: str, class_id: str
    ) -> tuple[RuntimeSessionPlan, tuple[PinnedSceneSummary, ...]]:
        """The slide list of the package the session pinned, with its text.

        A student page needs the number of slides and what each says to offer
        navigation and narration. This reads the pinned package's scene documents
        only — the renders are fetched for the one slide on screen — and it resolves
        the same pinned plan, so nothing here can drift to a newer publication.
        """

        plan = self._pinned_plan(institution_id, class_id)
        scenes = self._scenes.scenes(plan.package_id)
        self._telemetry.record_scene_listing(
            institution_id=institution_id,
            class_id=class_id,
            session_id=plan.session_plan_id,
            package_id=plan.package_id,
            scene_count=len(scenes),
        )
        return plan, scenes

    def _pinned_plan(self, institution_id: str, class_id: str) -> RuntimeSessionPlan:
        plan = self._repository.get_session_plan(institution_id, class_id)
        if plan is None:
            self._repository.get_class(institution_id, class_id)  # 404/403 first
            raise NotFoundError(f"class {class_id!r} has not started")
        return plan

    # -- enrollment and join ---------------------------------------------------------
    def enroll(
        self, institution_id: str, class_id: str, student_id: str
    ) -> tuple[Enrollment, bool]:
        """Authorize a student to join a class. Idempotent per ``(class, student)``."""

        self._repository.get_class(institution_id, class_id)
        student = (student_id or "").strip()
        if not student:
            raise ValidationError("student_id is required")
        enrollment, created = self._repository.enroll(
            institution_id=institution_id, class_id=class_id, student_id=student
        )
        if created:
            self._telemetry.metrics.enrollments_created += 1
        else:
            self._telemetry.metrics.enrollments_replayed += 1
        return enrollment, created

    def list_enrollments(self, institution_id: str, class_id: str) -> list[Enrollment]:
        self._repository.get_class(institution_id, class_id)
        return self._repository.list_enrollments(institution_id, class_id)

    def unenroll(self, institution_id: str, class_id: str, student_id: str) -> bool:
        """Remove a student from a class roster; idempotent (``DEC-RUNTIME-003``).

        A roster correction, not an account change: the account survives, and a
        credential the student already holds stays valid until it expires or the
        actor epoch moves (``DEC-RUNTIME-007``). What ends immediately is the ability
        to obtain a **new** one, because the join check reads this roster.
        """

        self._repository.get_class(institution_id, class_id)
        student = (student_id or "").strip()
        if not student:
            raise ValidationError("student_id is required")
        removed = self._repository.unenroll(institution_id, class_id, student)
        if removed:
            self._telemetry.metrics.enrollments_removed += 1
        return removed

    def enrolled_anywhere(self, institution_id: str, student_id: str) -> bool:
        """Whether this account is on any class roster in the institution.

        The read the account-removal guard uses: an account that a class referenced
        is deactivated, not deleted (V0-022).
        """

        return self._repository.count_enrollments_for_student(institution_id, student_id) > 0

    def issue_bootstrap_token(
        self, institution_id: str, class_id: str, student_id: str
    ) -> IssuedBootstrapToken:
        """Issue a short-lived join credential — **only** to an enrolled student.

        This is where "only authorized enrollment can join" is enforced: the class
        must be running, and the principal must be enrolled in *this* class in
        *this* tenant. The raw token is returned once and only its digest is
        stored, and it binds the class, the student, the session and the actor
        epoch, so a credential cannot outlive the session state it was issued for
        (``DEC-RUNTIME-007``).
        """

        scheduled_class = self._repository.get_class(institution_id, class_id)
        session = self._repository.get_session(institution_id, class_id)
        if session is None or session.state != CLASSROOM_STATE_ACTIVE:
            self._telemetry.record_join(
                institution_id=institution_id,
                class_id=class_id,
                session_id=session.session_id if session is not None else None,
                authorized=False,
                issue_code=ISSUE_NOT_STARTED,
            )
            raise ClassStartError(
                f"class {class_id!r} is not running; start it before joining",
                issue_code=ISSUE_NOT_STARTED,
            )

        student = (student_id or "").strip()
        if not student or not self._repository.is_enrolled(institution_id, class_id, student):
            self._telemetry.record_join(
                institution_id=institution_id,
                class_id=class_id,
                session_id=session.session_id,
                authorized=False,
                issue_code=ISSUE_NOT_ENROLLED,
            )
            raise JoinDeniedError(
                f"student is not enrolled in class {class_id!r}",
                issue_code=ISSUE_NOT_ENROLLED,
            )

        now = self._clock()
        expires_at = now + self._token_ttl
        token = secrets.token_urlsafe(32)
        record = self._repository.record_bootstrap_token(
            token_sha256=self._hash_token(token),
            institution_id=institution_id,
            class_id=class_id,
            session_id=session.session_id,
            student_id=student,
            actor_epoch=session.actor_epoch,
            nonce=str(uuid.uuid4()),
            scopes=BOOTSTRAP_TOKEN_SCOPES,
            issued_at=now.isoformat(),
            expires_at=expires_at.isoformat(),
        )
        self._telemetry.record_join(
            institution_id=institution_id,
            class_id=class_id,
            session_id=session.session_id,
            authorized=True,
        )
        return IssuedBootstrapToken(token=token, record=record)

    def verify_bootstrap_token(
        self, institution_id: str, class_id: str, token: str
    ) -> BootstrapToken:
        """Validate a presented credential, or refuse it with a precise reason.

        The media gateway calls this in V1 (it is not a client-facing route): the
        same binding the token was issued with is re-checked — tenant, class,
        session, live epoch, expiry, revocation.
        """

        record = self._repository.get_bootstrap_token(self._hash_token(token))
        if record is None or record.institution_id != institution_id:
            # An unknown token and another tenant's token are indistinguishable on
            # purpose: neither may reveal whether the credential exists.
            raise JoinDeniedError(
                "bootstrap token is unknown", issue_code=ISSUE_TOKEN_UNKNOWN
            )
        if record.class_id != class_id:
            raise JoinDeniedError(
                "bootstrap token was issued for another class", issue_code=ISSUE_TOKEN_UNKNOWN
            )
        if record.revoked:
            raise JoinDeniedError(
                "bootstrap token was revoked", issue_code=ISSUE_TOKEN_REVOKED
            )
        if datetime.fromisoformat(record.expires_at) <= self._clock():
            raise JoinDeniedError(
                "bootstrap token has expired", issue_code=ISSUE_TOKEN_EXPIRED
            )
        session = self._repository.get_session(institution_id, class_id)
        if session is None or session.actor_epoch != record.actor_epoch:
            raise JoinDeniedError(
                "bootstrap token belongs to a stale session epoch",
                issue_code=ISSUE_STALE_EPOCH,
            )
        return record

    def revoke_bootstrap_token(self, institution_id: str, token: str) -> bool:
        """Terminally revoke a credential ("all tokens have a release path")."""

        record = self._repository.get_bootstrap_token(self._hash_token(token))
        if record is None or record.institution_id != institution_id:
            return False
        return self._repository.revoke_bootstrap_token(institution_id, record.token_sha256) is not None

    # -- the aggregate command path (V0-010) -----------------------------------------
    def navigate_scene(
        self,
        institution_id: str,
        class_id: str,
        *,
        section_index: int,
        scene_id: str,
        section_id: Optional[str] = None,
        scene_step_id: Optional[str] = None,
        command_id: Optional[str] = None,
        expected_state_version: Optional[int] = None,
    ) -> CommandOutcome:
        """Move the session to a scene/step through the aggregate.

        The target is a *resolved* position — the caller (the timeline controller,
        V0-013) resolves it against the pinned lesson plan; the aggregate enforces
        the deterministic invariants (state, version fencing, idempotency), not the
        content lookup (``DEC-CONTENT-001``: the runtime never parses the source,
        and the pinned package's plan is the timeline's job).
        """

        command = Command.create(
            COMMAND_NAVIGATE,
            command_id=command_id,
            expected_state_version=expected_state_version,
            section_index=section_index,
            section_id=section_id,
            scene_id=scene_id,
            scene_step_id=scene_step_id,
        )
        return self._apply_command(institution_id, class_id, command)

    def record_checkpoint(
        self,
        institution_id: str,
        class_id: str,
        *,
        label: Optional[str] = None,
        command_id: Optional[str] = None,
        expected_state_version: Optional[int] = None,
    ) -> CommandOutcome:
        """Record a resume checkpoint at the current position (``DEC-RUNTIME-005``)."""

        command = Command.create(
            COMMAND_CHECKPOINT,
            command_id=command_id,
            expected_state_version=expected_state_version,
            label=label,
        )
        return self._apply_command(institution_id, class_id, command)

    def end_class(
        self,
        institution_id: str,
        class_id: str,
        *,
        command_id: Optional[str] = None,
        expected_state_version: Optional[int] = None,
    ) -> CommandOutcome:
        """``ACTIVE/DEGRADED -> COMPLETED``, revoking any live join credential.

        ``ENDING`` is in-process only: the aggregate commits the final checkpoint
        and the ``COMPLETED`` state in one snapshot, and the service then revokes
        the outstanding join credentials (``CLASS_END``: "revoke/cancel", "no
        leaked token").
        """

        command = Command.create(
            COMMAND_END,
            command_id=command_id,
            expected_state_version=expected_state_version,
        )
        outcome = self._apply_command(institution_id, class_id, command)
        if outcome.result.accepted and outcome.session is not None:
            self._repository.revoke_bootstrap_tokens(
                institution_id, outcome.session.session_id
            )
        return outcome

    def _apply_command(
        self, institution_id: str, class_id: str, command: Command
    ) -> CommandOutcome:
        """Load (or reuse) the aggregate, handle the command, and commit it.

        The per-class lock is the in-process serialization (``DEC-RUNTIME-001``);
        the guarded transition is the cross-process fence. On a lost race the
        aggregate reloads from the newest snapshot and re-handles, bounded, so a
        stale command is refused with ``STALE_STATE_VERSION`` rather than applied
        twice (``DEC-RUNTIME-007``).
        """

        self._repository.get_class(institution_id, class_id)  # 404/403 first
        lock = self._lock_for(class_id)
        with lock:
            for _attempt in range(3):
                aggregate = self._get_aggregate(institution_id, class_id)
                prior_state = aggregate.state
                prior_version = aggregate.state_version
                result = aggregate.handle(command)
                if result.duplicate:
                    # A replayed command has already been answered: return its stored
                    # verdict and write nothing (one logical effect — DEC-RUNTIME-003).
                    self._telemetry.record_command(
                        institution_id=institution_id,
                        class_id=class_id,
                        session_id=aggregate.session_id,
                        command_id=command.command_id,
                        command_type=command.type,
                        accepted=result.accepted,
                        state_version=result.state_version,
                        issue_code=result.issue_code,
                        duplicate=True,
                    )
                    return CommandOutcome(result, None, None)
                if not result.accepted:
                    self._telemetry.record_command(
                        institution_id=institution_id,
                        class_id=class_id,
                        session_id=aggregate.session_id,
                        command_id=command.command_id,
                        command_type=command.type,
                        accepted=False,
                        state_version=result.state_version,
                        issue_code=result.issue_code,
                    )
                    return CommandOutcome(result, None, None)
                document = aggregate.snapshot()
                try:
                    session, snapshot = self._repository.commit_transition(
                        institution_id=institution_id,
                        class_id=class_id,
                        session_id=aggregate.session_id,
                        expected_state=prior_state,
                        expected_state_version=prior_version,
                        actor_epoch=aggregate.actor_epoch,
                        new_state=aggregate.state,
                        state_version=aggregate.state_version,
                        event_sequence=aggregate.event_sequence,
                        snapshot=document,
                        snapshot_checksum=snapshot_checksum(document),
                    )
                except CommitConflict:
                    # Someone else advanced the session; reload and re-handle once.
                    self._aggregates.pop(class_id, None)
                    continue
                self._telemetry.record_command(
                    institution_id=institution_id,
                    class_id=class_id,
                    session_id=session.session_id,
                    command_id=command.command_id,
                    command_type=command.type,
                    accepted=True,
                    state_version=session.state_version,
                )
                return CommandOutcome(result, session, snapshot)
        # The session kept moving under a concurrent writer; refuse rather than loop.
        self._telemetry.record_command(
            institution_id=institution_id,
            class_id=class_id,
            session_id=aggregate.session_id,
            command_id=command.command_id,
            command_type=command.type,
            accepted=False,
            state_version=aggregate.state_version,
            issue_code=ISSUE_COMMIT_CONFLICT,
        )
        return CommandOutcome(
            CommandResult(
                command_id=command.command_id,
                accepted=False,
                issue_code=ISSUE_COMMIT_CONFLICT,
                state_version=aggregate.state_version,
                event_sequence=aggregate.event_sequence,
                events=(),
            ),
            None,
            None,
        )

    def _get_aggregate(self, institution_id: str, class_id: str) -> ClassroomAggregate:
        """The class's aggregate: the cached one, or a validated restore.

        Restore validates schema and checksum before use (``DEC-DATA-004``), so a
        corrupted snapshot is refused rather than replayed.
        """

        cached = self._aggregates.get(class_id)
        if cached is not None:
            return cached
        session = self._repository.get_session(institution_id, class_id)
        if session is None:
            raise ClassStartError(
                f"class {class_id!r} has not started", issue_code=ISSUE_NOT_STARTED
            )
        snapshot = self._repository.latest_snapshot(institution_id, session.session_id)
        if snapshot is None:  # pragma: no cover - the start transaction writes one
            raise NotFoundError(f"session {session.session_id!r} has no snapshot")
        validate_snapshot(
            snapshot.document,
            schema_version=snapshot.schema_version,
            checksum=snapshot.checksum,
        )
        aggregate = ClassroomAggregate.restore(snapshot.document, clock=self._clock)
        self._aggregates[class_id] = aggregate
        return aggregate

    def _lock_for(self, class_id: str) -> threading.Lock:
        return self._locks.setdefault(class_id, threading.Lock())

    # -- internals -------------------------------------------------------------------
    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256((token or "").encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_scheduled_for(value: Optional[str]) -> Optional[str]:
        if value is None or not str(value).strip():
            return None
        try:
            return datetime.fromisoformat(str(value)).isoformat()
        except ValueError as exc:
            raise ValidationError(f"scheduled_for must be an ISO-8601 timestamp: {exc}") from exc

    def _resolve_publication(self, institution_id: str, scheduled_class: Class) -> Publication:
        """Resolve *which* published tuple this session pins — once, here.

        With no pinned version the class takes the course's current publication; with
        one it takes that version's. Neither is a runtime lookup: the answer is
        written into the session plan and never recomputed.
        """

        if scheduled_class.version_id is not None:
            publication = self._repository.find_publication_for_version(
                institution_id, scheduled_class.version_id
            )
            wanted = f"course version {scheduled_class.version_id!r}"
        else:
            publication = self._repository.find_current_publication_for_course(
                institution_id, scheduled_class.course_id
            )
            wanted = f"course {scheduled_class.course_id!r}"
        if publication is None:
            self._block(
                scheduled_class, STAGE_RESOLVING, ISSUE_VERSION_NOT_PUBLISHED,
                f"{wanted} has no published version to pin; publish it first",
            )
        return publication

    def _load_pinned_package(self, scheduled_class: Class, publication: Publication):
        """Read the bytes the publication pinned, and re-verify them against its seal."""

        loaded = read_package(self._object_store, package_prefix(publication.package_id))
        if loaded is None:
            self._block(
                scheduled_class, STAGE_VERIFYING, ISSUE_INCOMPATIBLE_CONTENT,
                f"the package {publication.package_id!r} this publication pins is not stored",
            )
        integrity = verify_package(loaded.package, publication.content_digest)
        if integrity.state != INTEGRITY_VERIFIED:
            self._block(
                scheduled_class, STAGE_VERIFYING, ISSUE_CONTENT_DIGEST_MISMATCH,
                f"the stored package no longer matches the sealed content "
                f"({', '.join(integrity.issues) or integrity.state})",
            )
        supported = self._catalog.defaults().supported_ctf_schema_versions
        schema_version = str(loaded.manifest.get("schema_version", ""))
        if schema_version not in supported:
            self._block(
                scheduled_class, STAGE_VERIFYING, ISSUE_INCOMPATIBLE_CONTENT,
                f"package envelope {schema_version!r} is not one this runtime supports "
                f"({', '.join(supported)})",
            )
        return loaded

    def _resolve_lesson(
        self, scheduled_class: Class, publication: Publication, loaded
    ) -> dict[str, Any]:
        """Position the session at the first step of the *pinned* lesson plan."""

        plan = loaded.lesson_plan()
        if plan is None:
            self._block(
                scheduled_class, STAGE_VERIFYING, ISSUE_INCOMPATIBLE_CONTENT,
                "the pinned package carries no lesson plan",
            )
        plan_version = str(plan.get("lesson_plan_version", ""))
        if publication.lesson_plan_versions and plan_version not in publication.lesson_plan_versions:
            self._block(
                scheduled_class, STAGE_VERIFYING, ISSUE_INCOMPATIBLE_CONTENT,
                f"the package's lesson plan is {plan_version!r} but the publication pinned "
                f"{', '.join(publication.lesson_plan_versions)}",
            )
        return first_lesson_position(plan)

    def _resolve_index(self, institution_id: str, publication: Publication):
        """The knowledge-index pin must be *about* this content (``DEC-DATA-005``)."""

        index = self._repository.get_index_version(
            institution_id, publication.version_id, publication.content_package_version
        )
        if index is None:
            raise ClassStartError(
                f"publication {publication.publication_id!r} has no knowledge-index pin",
                issue_code=ISSUE_INCOMPATIBLE_INDEX,
            )
        if (
            index.index_version != publication.knowledge_index_version
            or index.source_digest != publication.content_digest
        ):
            raise ClassStartError(
                f"the knowledge-index pin ({index.index_version}) does not match the "
                "published content it would retrieve through",
                issue_code=ISSUE_INCOMPATIBLE_INDEX,
            )
        return index

    def _block(
        self, scheduled_class: Class, stage: str, issue_code: str, message: str
    ) -> NoReturn:
        self._telemetry.record_blocked(
            institution_id=scheduled_class.institution_id,
            class_id=scheduled_class.class_id,
            course_id=scheduled_class.course_id,
            stage=stage,
            issue_code=issue_code,
            version_id=scheduled_class.version_id,
        )
        raise ClassStartError(message, issue_code=issue_code)

    def _record_started(
        self,
        scheduled_class: Class,
        session: ClassroomSession,
        plan: RuntimeSessionPlan,
        *,
        created: bool,
    ) -> None:
        self._telemetry.record_started(
            institution_id=plan.institution_id,
            class_id=scheduled_class.class_id,
            session_id=session.session_id,
            course_id=plan.course_id,
            version_id=plan.version_id,
            course_version=plan.course_version,
            package_id=plan.package_id,
            content_package_version=plan.content_package_version,
            knowledge_index_version=plan.knowledge_index_version,
            policy_version=plan.policy_version,
            capability_version=plan.capability_version,
            region=plan.region,
            actor_epoch=session.actor_epoch,
            created=created,
        )


__all__ = ["STAGE_RESOLVING", "STAGE_VERIFYING", "ClassroomService", "CommandOutcome", "SessionStartResult"]
