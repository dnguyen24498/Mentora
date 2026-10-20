"""HTTP surface for classes, start, snapshots, scenes and join authorization.

Routes (``contracts/openapi/openapi.yaml``):

* ``POST /classes`` — schedule a class against a course (optionally a version).
* ``GET  /classes`` — the tenant's classes, newest first.
* ``GET  /classes/{classId}`` — the class, its session and its pinned tuple.
* ``POST /classes/{classId}/start`` — ``SCHEDULED -> ACTIVE``; resolves and pins the
  exact version tuple once and commits the initial snapshot with it. Idempotent: a
  replay returns the same session with ``created: false``.
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
(``403`` ``INSUFFICIENT_SCOPE``) on scheduling, starting, enrolling and the roster,
and a student's join credential is always their **own** — the request cannot name
whose credential it wants.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.api.security import ApiSecurity
from app.classroom.service import ClassroomService
from app.common.errors import ValidationError
from app.identity.errors import (
    ISSUE_SESSION_REQUIRED,
    AccountRequiredError,
    SessionError,
)
from app.identity.models import Principal, Role, Scope


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
        """The class with its session and pinned tuple (both ``null`` before start)."""

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
        """The authoritative snapshot (checksum + schema validated before returned)."""

        return service.get_snapshot(principal.institution_id, class_id).to_dict()

    @router.get("/classes/{class_id}/scenes")
    def list_scenes(
        class_id: str, principal: Principal = Depends(require(Scope.SCENE_READ))
    ) -> dict[str, Any]:
        """The slide list of the package this session pinned, with each slide's text.

        A student page uses it to offer navigation and gather narration; the
        *renders* are fetched one at a time by ``GET .../scenes/{order}``, so opening
        a lesson does not read every asset. Both resolve the session's own pinned
        plan, so neither can drift to a newer publication (``DEC-CONTENT-005``).
        """

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
        (``DEC-CONTENT-005``). ``404`` when the class has not started or the package
        has no such scene; ``502`` when the pinned bytes no longer match their
        recorded digest.
        """

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
