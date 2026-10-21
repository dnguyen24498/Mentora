"""HTTP surface for classes, start, snapshots, scenes and join authorization.

Routes (``contracts/openapi/openapi.yaml``):

* ``POST /classes`` — schedule a class against a course (optionally a version).
* ``GET  /classes`` — the tenant's classes, newest first.
* ``GET  /classes/{classId}`` — the class, its session and its pinned tuple.
* ``POST /classes/{classId}/start`` — ``SCHEDULED -> ACTIVE``; resolves and pins the
  exact version tuple once and commits the initial snapshot with it. Idempotent: a
  replay returns the same session with ``created: false``.
* ``POST /classes/{classId}/navigate`` — move to a pinned slide (teacher).
* ``POST /classes/{classId}/end`` — ``ACTIVE/DEGRADED -> COMPLETED``; locks the
  lesson for students and revokes their join credentials.
* ``POST /classes/{classId}/reopen`` — ``COMPLETED -> ACTIVE``; runs the same
  class occurrence again from the first slide, in a new actor epoch.
* ``GET  /classes/{classId}/snapshot`` — the authoritative snapshot, checksum-validated.
* ``GET  /classes/{classId}/scenes`` — the slide list of the package the session
  pinned, with each slide's text (navigation + narration).
* ``GET  /classes/{classId}/scenes/{order}`` — the slide the session is presenting,
  read from the package the session **pinned** (``DEC-CONTENT-005``).
* ``POST /classes/{classId}/enrollments`` — add a student to the roster: enrol an
  account that already exists, by address or by id. Enrolment never creates an
  account, so an unknown address is a named refusal rather than an implicit signup.
* ``DELETE /classes/{classId}/enrollments/{studentId}`` — remove a student from the
  roster (idempotent).
* ``GET  /classes/{classId}/enrollments`` — the class roster the join check uses.
* ``POST /classes/{classId}/bootstrap-token`` — the join credential, issued to the
  **authenticated** student and only when they are enrolled in a running class.

Every route resolves a principal through :mod:`app.api.security`, and the tenant is
derived from it, so a caller cannot read or write another institution's class by
naming it. Write verbs additionally require a capability: a student token is refused
(``403`` ``INSUFFICIENT_SCOPE``) on scheduling, starting, navigating, enrolling and
the roster, and a student's join credential is always their **own** — the request
cannot name whose credential it wants. A student's reads of a class, its snapshot
and its pinned scenes are also checked against the class roster
(``403`` ``NOT_ENROLLED``), so the participant read path agrees with the join path.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel

from app.api.security import ApiSecurity
from app.classroom.errors import ClassCommandError
from app.classroom.service import ClassroomService
from app.common.errors import ValidationError
from app.identity.errors import (
    ISSUE_SESSION_REQUIRED,
    AccountRequiredError,
    SessionError,
)
from app.identity.models import Principal, Role, Scope


class NavigateRequest(BaseModel):
    """The teacher's presentation control: which pinned slide to show (V0-025).

    ``order`` is the scene order the package recorded (0-based), not a lesson
    section. The server resolves it against the pinned scene list and lesson plan,
    so the client never supplies a scene id or section position.
    """

    order: int
    expected_state_version: Optional[int] = None
    command_id: Optional[str] = None


class LifecycleRequest(BaseModel):
    """The optional fencing/idempotency fields of end and reopen.

    Neither command has a payload beyond the fence: the server resolves the end
    state and, for a reopen, the first lesson position from the pinned package.
    """

    expected_state_version: Optional[int] = None
    command_id: Optional[str] = None


def _student_id(principal: Principal) -> Optional[str]:
    """The roster id a student's read must be checked against; staff pass ``None``."""

    return principal.account_id if principal.role is Role.STUDENT else None


def build_class_router(
    service: ClassroomService,
    security: ApiSecurity,
) -> APIRouter:
    router = APIRouter()
    require = security.require

    @router.post("/classes", status_code=201)
    def schedule_class(
        course_id: str,
        principal: Principal = Depends(require(Scope.CLASS_WRITE)),
        title: Optional[str] = None,
        version_id: Optional[str] = None,
        scheduled_for: Optional[str] = None,
    ) -> dict:
        """Schedule a class. ``scheduled_for`` is recorded, not enforced (no timer)."""

        return service.schedule_class(
            principal.institution_id,
            course_id,
            title=title,
            version_id=version_id,
            scheduled_for=scheduled_for,
        ).to_dict()

    @router.get("/classes")
    def list_classes(
        principal: Principal = Depends(require(Scope.CLASS_READ)), limit: int = 100
    ) -> list[dict]:
        """The tenant's classes — for a student, only the ones they are enrolled in.

        The roster is what authorizes a join, so it is also what a student's list
        may show. A teacher (and an institution administrator, who reads for
        oversight) sees the tenant's schedule; a student sees their own classes.
        """

        if principal.role is Role.STUDENT:
            if principal.account_id is None:
                return []
            student_id: Optional[str] = principal.account_id
        else:
            student_id = None
        return [
            item.to_dict()
            for item in service.list_classes(
                principal.institution_id, limit=limit, student_id=student_id
            )
        ]

    @router.get("/classes/{class_id}")
    def get_class(
        class_id: str, principal: Principal = Depends(require(Scope.CLASS_READ))
    ) -> dict:
        """The class with its session and pinned tuple (both ``null`` before start).

        A student is a participant, so the read is limited to a class on their
        roster (``403 NOT_ENROLLED`` otherwise); staff read by capability.
        """

        service.require_enrollment(
            principal.institution_id, class_id, student_id=_student_id(principal)
        )
        return service.class_view(principal.institution_id, class_id)

    @router.post("/classes/{class_id}/start")
    def start_class(
        class_id: str, principal: Principal = Depends(require(Scope.CLASS_WRITE))
    ) -> dict:
        """Resolve and pin the exact version tuple, then go ``ACTIVE``.

        ``200`` whether the session was created or replayed (``DEC-RUNTIME-003``).
        ``409`` ``CLASS_NOT_READY`` carries the precise ``issue_code`` when the
        version was never published, the knowledge-index pin does not match the
        content, the package is damaged or unsupported, or the class is not
        ``SCHEDULED``. Nothing is written on a refusal.
        """

        return service.start_class(principal.institution_id, class_id).to_dict()

    @router.get("/classes/{class_id}/snapshot")
    def get_snapshot(
        class_id: str, principal: Principal = Depends(require(Scope.CLASS_READ))
    ) -> dict:
        """The authoritative snapshot (checksum + schema validated before returned).

        The student view polls this to follow the teacher's slide, so a student's
        read is checked against the class roster first (``403 NOT_ENROLLED``) and
        then against the session state: a completed class is locked
        (``409 CLASS_NOT_READY``, ``CLASS_ENDED``) until a teacher reopens it.
        Staff read by capability, so a teacher can review an ended class.
        """

        service.require_student_content_access(
            principal.institution_id, class_id, student_id=_student_id(principal)
        )
        return service.get_snapshot(principal.institution_id, class_id).to_dict()

    @router.post("/classes/{class_id}/navigate")
    def navigate_class(
        class_id: str,
        body: NavigateRequest,
        principal: Principal = Depends(require(Scope.CLASS_WRITE)),
    ) -> dict:
        """Move the class to a pinned slide (V0-025).

        The teacher's presentation control. ``order`` is the package's scene order;
        the server resolves it against the session's **pinned** scene list and
        lesson plan, then sends the aggregate a resolved ``NAVIGATE_SCENE``. It is
        an HTTP command over the existing in-process aggregate — **not** the ordered
        per-class event stream (``DEC-DATA-003`` is ``OPEN``, V1-002). Students see
        the new slide by polling ``GET .../snapshot``; no source document is parsed
        and no later publication can move a running session (``DEC-CONTENT-005``).

        ``409 CONFLICT`` with ``issue_code`` ``STALE_STATE_VERSION`` when the
        teacher's view is behind, ``INVALID_TRANSITION`` after the class ended, and
        ``409 CLASS_NOT_READY``/``NOT_STARTED`` before it starts. A refusal writes
        nothing.
        """

        outcome = service.navigate_to_order(
            principal.institution_id,
            class_id,
            order=body.order,
            command_id=body.command_id,
            expected_state_version=body.expected_state_version,
        )
        if not outcome.result.accepted:
            raise ClassCommandError(
                f"the class cannot move to slide order {body.order} now",
                issue_code=outcome.result.issue_code or "INVALID_COMMAND",
            )
        return outcome.to_dict()

    @router.post("/classes/{class_id}/end")
    def end_class(
        class_id: str,
        body: Optional[LifecycleRequest] = None,
        principal: Principal = Depends(require(Scope.CLASS_WRITE)),
    ) -> dict[str, Any]:
        """End the class: ``ACTIVE/DEGRADED -> COMPLETED``.

        The teacher's close action. The aggregate writes the final checkpoint and
        the completed state in one snapshot, and the service revokes the session's
        join credentials. The lesson is then **locked** for students — they may
        still see that the class ended in their list, but the snapshot and the
        pinned slides are refused (``409 CLASS_NOT_READY``, ``CLASS_ENDED``) until
        a teacher reopens it. A teacher can still review the last slide.

        ``409 CONFLICT`` with ``issue_code`` ``INVALID_TRANSITION`` when the class
        is not running; a refusal writes nothing.
        """

        request = body or LifecycleRequest()
        outcome = service.end_class(
            principal.institution_id,
            class_id,
            command_id=request.command_id,
            expected_state_version=request.expected_state_version,
        )
        if not outcome.result.accepted:
            raise ClassCommandError(
                "the class cannot be ended now",
                issue_code=outcome.result.issue_code or "INVALID_TRANSITION",
            )
        return outcome.to_dict()

    @router.post("/classes/{class_id}/reopen")
    def reopen_class(
        class_id: str,
        body: Optional[LifecycleRequest] = None,
        principal: Principal = Depends(require(Scope.CLASS_WRITE)),
    ) -> dict[str, Any]:
        """Reopen an ended class: ``COMPLETED -> ACTIVE``.

        Keeps the class's roster and its **pinned** package and returns the lesson
        to its first position, so the same occurrence can be taught again. A new
        actor epoch is started, which makes every credential and fenced command
        from before the end stale (``DEC-RUNTIME-007``). The response is the new
        snapshot; the teacher's stage can apply it and continue.

        ``409 CONFLICT`` with ``issue_code`` ``INVALID_TRANSITION`` when the class
        has not ended; ``409 CLASS_NOT_READY``/``NOT_STARTED`` before its first
        start. A refusal writes nothing.
        """

        request = body or LifecycleRequest()
        outcome = service.reopen_class(
            principal.institution_id,
            class_id,
            command_id=request.command_id,
            expected_state_version=request.expected_state_version,
        )
        if not outcome.result.accepted:
            raise ClassCommandError(
                "the class cannot be reopened now",
                issue_code=outcome.result.issue_code or "INVALID_TRANSITION",
            )
        return outcome.to_dict()

    @router.get("/classes/{class_id}/scenes")
    def list_scenes(
        class_id: str, principal: Principal = Depends(require(Scope.SCENE_READ))
    ) -> dict[str, Any]:
        """The slide list of the package this session pinned, with each slide's text.

        A student page uses it to gather the text of the slide the teacher is on;
        the *renders* are fetched one at a time by ``GET .../scenes/{order}``, so
        opening a lesson does not read every asset. A student's read is limited to
        their own roster, and to a running session — an ended class is locked until
        reopened. Both resolve the session's own pinned plan, so neither can
        drift to a newer publication (``DEC-CONTENT-005``).
        """

        service.require_student_content_access(
            principal.institution_id, class_id, student_id=_student_id(principal)
        )
        plan, scenes = service.pinned_scenes(principal.institution_id, class_id)
        return {
            "class_id": class_id,
            "package_id": plan.package_id,
            "content_digest": plan.content_digest,
            "scene_count": len(scenes),
            "scenes": [scene.to_dict() for scene in scenes],
        }

    @router.get("/classes/{class_id}/scenes/{order}")
    def get_scene(
        class_id: str,
        order: int,
        principal: Principal = Depends(require(Scope.SCENE_READ)),
    ) -> Response:
        """One slide of the package the session pinned, as an SVG.

        Resolved from the session's own ``RuntimeSessionPlan``, so a correction
        published after the start does not change what this class sees
        (``DEC-CONTENT-005``). A student's read is limited to their own roster and
        a running session (an ended class is locked until reopened).
        ``404`` when the class has not started or the package has no such scene;
        ``502`` when the pinned bytes no longer match their recorded digest.
        """

        service.require_student_content_access(
            principal.institution_id, class_id, student_id=_student_id(principal)
        )
        scene = service.pinned_scene(principal.institution_id, class_id, order)
        return Response(
            content=scene.svg,
            media_type=scene.media_type,
            headers={
                # Per class and per scene position, and the pinned bytes never
                # change, so a client may reuse it while the page is open — but a
                # shared cache must not, because the URL names a class.
                "Cache-Control": "private, max-age=3600",
                "X-Mentora-Package": scene.package_id,
                "X-Mentora-Scene": scene.scene_id or "",
            },
        )

    @router.post("/classes/{class_id}/enrollments")
    def enroll_student(
        class_id: str,
        principal: Principal = Depends(require(Scope.ENROLLMENT_WRITE)),
        email: Optional[str] = None,
        student_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Add a student to the class roster. Idempotent per ``(class, student)``.

        Two ways to name the student, and **neither creates an account**:

        * ``email`` — resolved against this institution's accounts. An address with no
          account here is ``404 ACCOUNT_REQUIRED``: an institution administrator
          creates accounts (``POST /accounts``), a teacher enrols them (V0-022).
        * ``student_id`` — enrol an account that already exists, by its id. An id that
          is not an account of this tenant is ``404``, not a free-text roster entry.

        The class is validated before the student is resolved, so a bad class id is a
        bad class id regardless of who is named — and a refusal writes nothing at all.
        """

        institution_id = principal.institution_id
        service.class_view(institution_id, class_id)  # 404/403 before any write

        if email:
            account = security.identity.find_account_by_email(institution_id, email)
            if account is None:
                raise AccountRequiredError(
                    f"this institution has no account for {email!r}. An institution "
                    "administrator creates accounts; a teacher enrols the students "
                    "an administrator has created"
                )
        elif student_id:
            account = security.identity.account(institution_id, student_id)
        else:
            raise ValidationError("provide an email or a student_id to enrol")

        enrollment, created = service.enroll(
            institution_id, class_id, account.account_id
        )
        return {
            **enrollment.to_dict(),
            "created": created,
            "student": account.to_dict(),
        }

    @router.delete("/classes/{class_id}/enrollments/{student_id}")
    def unenroll_student(
        class_id: str,
        student_id: str,
        principal: Principal = Depends(require(Scope.ENROLLMENT_WRITE)),
    ) -> dict[str, Any]:
        """Remove a student from the class roster. Idempotent (V0-022).

        A roster correction, not an account change: the account survives, and the
        credential a student already holds keeps working until it expires or the
        actor epoch moves (``DEC-RUNTIME-007``). What ends immediately is the ability
        to obtain a **new** join credential, because the join check reads this roster.
        """

        removed = service.unenroll(principal.institution_id, class_id, student_id)
        return {"class_id": class_id, "student_id": student_id, "removed": removed}

    @router.get("/classes/{class_id}/enrollments")
    def list_enrollments(
        class_id: str, principal: Principal = Depends(require(Scope.ENROLLMENT_WRITE))
    ) -> dict:
        """The roster.

        A teacher capability, not a shared read: the roster is other people's
        identities, so a student's own enrolment is reported by the join check and
        by ``GET /classes/{classId}``, not by this list.
        """

        institution_id = principal.institution_id
        enrollments = []
        for enrollment in service.list_enrollments(institution_id, class_id):
            account = security.identity.find_account(
                institution_id, enrollment.student_id
            )
            enrollments.append(
                {
                    **enrollment.to_dict(),
                    "student": account.to_dict() if account is not None else None,
                }
            )
        return {"class_id": class_id, "enrollments": enrollments}

    @router.post("/classes/{class_id}/bootstrap-token")
    def issue_bootstrap_token(
        class_id: str,
        principal: Principal = Depends(require(Scope.JOIN)),
    ) -> dict:
        """Issue a short-lived join credential to the **authenticated** student.

        There is no student id in the request any more: the credential is bound to
        the session's own account, so a caller cannot ask for someone else's
        credential. Joining is a **participant** action, so it needs the ``join``
        capability, which only the student role holds: a teacher — including the
        development tenant shortcut, which *is* a teacher principal — is refused
        here with ``403`` ``INSUFFICIENT_SCOPE`` (``issue_code SCOPE_REQUIRED``) and
        never reaches the class. That guard is the authorization; the check below is
        the invariant behind it, that a join credential always binds to an account,
        and it can only fire for a principal that somehow held ``join`` without one.
        ``403`` ``NOT_ENROLLED`` when the account is in the tenant but not in this
        class; ``409`` ``CLASS_NOT_READY`` when the class has not started. The token
        is returned once — only its digest is stored — and it carries ``subscribe``
        scope only (``DEC-TURN-001``).
        """

        if principal.account_id is None:
            raise SessionError(
                "joining a class requires a signed-in student account",
                issue_code=ISSUE_SESSION_REQUIRED,
            )
        return service.issue_bootstrap_token(
            principal.institution_id, class_id, principal.account_id
        ).to_dict()

    return router


__all__ = ["build_class_router"]
