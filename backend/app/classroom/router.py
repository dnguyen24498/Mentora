"""HTTP surface for classes, start, snapshots and join authorization (V0-009).

Routes (``contracts/openapi/openapi.yaml``):

* ``POST /classes`` — schedule a class against a course (optionally a version).
* ``GET  /classes`` — the tenant's classes, newest first.
* ``GET  /classes/{classId}`` — the class, its session and its pinned tuple.
* ``POST /classes/{classId}/start`` — ``SCHEDULED -> ACTIVE``; resolves and pins the
  exact version tuple once and commits the initial snapshot with it. Idempotent: a
  replay returns the same session with ``created: false``.
* ``GET  /classes/{classId}/snapshot`` — the authoritative snapshot, checksum-validated.
* ``POST/GET /classes/{classId}/enrollments`` — the class roster the join check uses.
* ``POST /classes/{classId}/bootstrap-token`` — the join credential, issued only to
  an enrolled student of a running class.

Every route is tenant-scoped through ``X-Institution-Id``; without the header the
request is rejected before reaching the service (422).
"""

from __future__ import annotations

from typing import Callable, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.classroom.service import ClassroomService


class BootstrapTokenRequest(BaseModel):
    """The principal asking to join. Identity/federation is not implemented yet, so
    this is *who they claim to be* — enrollment is what actually authorizes it."""

    student_id: str = Field(min_length=1, max_length=256)


def build_class_router(
    service: ClassroomService,
    tenant: Callable[..., str],
) -> APIRouter:
    router = APIRouter()

    @router.post("/classes", status_code=201)
    def schedule_class(
        course_id: str,
        institution_id: str = Depends(tenant),
        title: Optional[str] = None,
        version_id: Optional[str] = None,
        scheduled_for: Optional[str] = None,
    ) -> dict:
        """Schedule a class. ``scheduled_for`` is recorded, not enforced (no timer)."""

        return service.schedule_class(
            institution_id,
            course_id,
            title=title,
            version_id=version_id,
            scheduled_for=scheduled_for,
        ).to_dict()

    @router.get("/classes")
    def list_classes(
        institution_id: str = Depends(tenant), limit: int = 100
    ) -> list[dict]:
        return [item.to_dict() for item in service.list_classes(institution_id, limit=limit)]

    @router.get("/classes/{class_id}")
    def get_class(class_id: str, institution_id: str = Depends(tenant)) -> dict:
        """The class with its session and pinned tuple (both ``null`` before start)."""

        return service.class_view(institution_id, class_id)

    @router.post("/classes/{class_id}/start")
    def start_class(class_id: str, institution_id: str = Depends(tenant)) -> dict:
        """Resolve and pin the exact version tuple, then go ``ACTIVE``.

        ``200`` whether the session was created or replayed (``DEC-RUNTIME-003``).
        ``409`` ``CLASS_NOT_READY`` carries the precise ``issue_code`` when the
        version was never published, the knowledge-index pin does not match the
        content, the package is damaged or unsupported, or the class is not
        ``SCHEDULED``. Nothing is written on a refusal.
        """

        return service.start_class(institution_id, class_id).to_dict()

    @router.get("/classes/{class_id}/snapshot")
    def get_snapshot(class_id: str, institution_id: str = Depends(tenant)) -> dict:
        """The authoritative snapshot (checksum + schema validated before returned)."""

        return service.get_snapshot(institution_id, class_id).to_dict()

    @router.post("/classes/{class_id}/enrollments")
    def enroll_student(
        class_id: str,
        student_id: str,
        institution_id: str = Depends(tenant),
    ) -> dict:
        """Enroll a student in the class. Idempotent: enrolling twice is one enrollment."""

        enrollment, created = service.enroll(institution_id, class_id, student_id)
        return {**enrollment.to_dict(), "created": created}

    @router.get("/classes/{class_id}/enrollments")
    def list_enrollments(class_id: str, institution_id: str = Depends(tenant)) -> dict:
        return {
            "class_id": class_id,
            "enrollments": [
                enrollment.to_dict()
                for enrollment in service.list_enrollments(institution_id, class_id)
            ],
        }

    @router.post("/classes/{class_id}/bootstrap-token")
    def issue_bootstrap_token(
        class_id: str,
        body: BootstrapTokenRequest,
        institution_id: str = Depends(tenant),
    ) -> dict:
        """Issue a short-lived join credential to an enrolled student of a running class.

        ``403`` ``NOT_ENROLLED`` when the principal is in the tenant but not enrolled
        in this class; ``409`` ``CLASS_NOT_READY`` when the class has not started.
        The token is returned once — only its digest is stored — and it carries
        ``subscribe`` scope only.
        """

        return service.issue_bootstrap_token(
            institution_id, class_id, body.student_id
        ).to_dict()

    return router


__all__ = ["build_class_router"]
