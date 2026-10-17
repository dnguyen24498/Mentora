"""The atomic publication transition: ``APPROVED -> SEALING -> INDEXING -> COMMITTING -> PUBLISHED`` (V0-008).

``docs/state-machines/PUBLICATION_STATE_MACHINE.md`` and
``docs/architecture/07_PUBLICATION_AND_REVIEW.md``: *"Atomic publication validates
references/schemas/checksums/provenance, writes immutable package, builds
compatible pinned index, commits metadata/outbox, then exposes the version.
Corrections create new versions."*

Pipeline position: the last stage of
``docs/sequences/COURSE_UPLOAD_PUBLICATION.md``
(``… -> review -> seal/index/commit -> published event``). It runs *after* the
teacher review (V0-007) accepted the built package and moved the course version to
``APPROVED``, and it is the only writer of publication state.

Three properties decide the shape of this module:

* **Partial failure never exposes a published version.** The three stages run
  before a single commit transaction; a failure at any of them leaves the version
  status unchanged and no publication, index-version or outbox row, so a retry
  starts from a clean state. There is nothing to compensate and nothing visible to
  retract, which is stronger than rolling back a half-written publication.
* **Published bytes cannot be overwritten.** Publishing *writes no bytes*: the
  package is content-addressed, owned by the compiler, and only sealed here. A
  correction changes the source, hence the content version, hence the package
  prefix; the previous publication's prefix is never written again, and
  :meth:`PublicationService.verify` re-checks the pinned content against the
  digest recorded at seal time so a later overwrite is *detected*.
* **Idempotency is a property, not a guard.** The identity is content
  (``version_id`` + ``content_package_version``), so a repeated or concurrent
  publish returns the first publication instead of a second one
  (``DEC-RUNTIME-003``).

Technology decisions stay where they were: ``DEC-TECH-001`` (ordered event
technology) and ``DEC-TECH-003`` (durable workflow) are ``OPEN``, so this is an
in-process sequence of named stages — no workflow engine, no broker, no dispatcher
— and the outbox row is durable and pull-readable.
"""

from __future__ import annotations

from typing import Any, Optional

from app.common.errors import AppError, NotFoundError
from app.compiler.package_builder.layout import package_prefix
from app.compiler.package_builder.loader import LoadedPackage, read_package
from app.compiler.package_builder.service import PackageBuildService
from app.courses.models import CourseVersion, CourseVersionStatus
from app.courses.repository import CourseRepository
from app.publication.errors import (
    ISSUE_COMMIT_CONFLICT,
    ISSUE_INDEX_FAILED,
    ISSUE_NOT_APPROVED,
    ISSUE_STALE_APPROVAL,
    ISSUE_WRONG_STATE,
    PublicationError,
)
from app.publication.index import BaselineIndexBuilder, IndexBuilder
from app.publication.models import (
    DECISION_APPROVE,
    PUBLICATION_STAGE_COMMITTING,
    PUBLICATION_STAGE_INDEXING,
    PUBLICATION_STAGE_SEALING,
    Publication,
)
from app.publication.repository import CommitConflict, PublicationRepository, ReviewRepository
from app.publication.seal import (
    INTEGRITY_MISSING,
    PackageIntegrity,
    PackageSeal,
    seal_package,
    verify_package,
)
from app.publication.telemetry import PublicationTelemetry
from app.storage.object_store import ObjectStore


class PublicationService:
    """Seals, indexes and commits one approved package; serves published versions."""

    def __init__(
        self,
        course_repository: CourseRepository,
        review_repository: ReviewRepository,
        publication_repository: PublicationRepository,
        object_store: ObjectStore,
        package_service: PackageBuildService,
        *,
        index_builder: Optional[IndexBuilder] = None,
        telemetry: Optional[PublicationTelemetry] = None,
    ) -> None:
        self._courses = course_repository
        self._reviews = review_repository
        self._publications = publication_repository
        self._object_store = object_store
        self._packages = package_service
        self._index = index_builder or BaselineIndexBuilder()
        self._telemetry = telemetry or PublicationTelemetry()

    @property
    def telemetry(self) -> PublicationTelemetry:
        return self._telemetry

    # -- the transition --------------------------------------------------------------
    def publish(
        self, institution_id: str, version_id: str, *, published_by: Optional[str] = None
    ) -> tuple[Publication, bool]:
        """Publish an approved course version. Returns ``(publication, created)``.

        ``created`` is ``False`` when this was a replay of an identical
        ``(version, content)`` pair — the response is the same publication either
        way, so a client can retry a request whose response it lost.
        """

        # Tenant-scoped: another institution's version raises before any work.
        version = self._courses.get_version(institution_id, version_id)
        artifact = self._publications.find_artifact_for_version(institution_id, version_id)
        if artifact is None:
            raise NotFoundError(
                f"course version {version_id!r} has no source artifact to publish"
            )
        loaded = self._load(institution_id, artifact.artifact_id)
        if loaded is None:
            raise NotFoundError(
                f"no package has been built for artifact {artifact.artifact_id}; "
                "build the review package before publishing it"
            )
        content_version = str(loaded.manifest.get("content_package_version", ""))

        # Idempotency first, and *before* the approval check: a replay arrives when
        # the version is already PUBLISHED, which is not the APPROVED state the
        # transition's precondition names.
        existing = self._publications.find_publication(
            institution_id, version_id, content_version
        )
        if existing is not None:
            self._record_publish(existing, created=False, scenes=None)
            return existing, False

        self._require_approved(institution_id, artifact.artifact_id, version, content_version)

        package_id = str(loaded.manifest.get("package_id", ""))

        # -- SEALING: verify the artifact and compute what the publication pins ----
        try:
            seal = seal_package(loaded.package)
        except PublicationError as exc:
            self._record_blocked(
                PUBLICATION_STAGE_SEALING, exc, institution_id, version_id,
                artifact.artifact_id, package_id, content_version,
            )
            raise
        self._telemetry.record_stage(
            stage=PUBLICATION_STAGE_SEALING,
            outcome="SEALED",
            institution_id=institution_id,
            version_id=version_id,
            artifact_id=artifact.artifact_id,
            package_id=package_id,
            content_package_version=content_version,
            detail=seal.content_digest,
        )
        self._telemetry.metrics.stages_sealed += 1

        # -- INDEXING: establish the index version the publication must pin --------
        try:
            index = self._index.build(
                institution_id=institution_id,
                course_id=artifact.course_id,
                version_id=version_id,
                package=loaded.package,
                seal=seal,
            )
        except AppError as exc:
            # A builder that classifies its own failure (a real provider, V0-014).
            self._record_blocked(
                PUBLICATION_STAGE_INDEXING, getattr(exc, "issue_code", exc.code.value),
                institution_id, version_id, artifact.artifact_id, package_id, content_version,
            )
            raise
        except Exception as exc:  # noqa: BLE001 - classified, then re-raised with the cause
            failure = PublicationError(
                f"the knowledge-index stage could not produce an index version: {exc}",
                issue_code=ISSUE_INDEX_FAILED,
            )
            self._record_blocked(
                PUBLICATION_STAGE_INDEXING, failure.issue_code, institution_id, version_id,
                artifact.artifact_id, package_id, content_version,
            )
            raise failure from exc
        self._telemetry.record_stage(
            stage=PUBLICATION_STAGE_INDEXING,
            outcome="INDEXED",
            institution_id=institution_id,
            version_id=version_id,
            artifact_id=artifact.artifact_id,
            package_id=package_id,
            content_package_version=content_version,
            detail=index.index_version,
        )
        self._telemetry.metrics.stages_indexed += 1

        # -- COMMITTING: one transaction, then the version is visible --------------
        try:
            publication, superseded = self._publications.commit(
                institution_id=institution_id,
                course_id=artifact.course_id,
                version_id=version_id,
                course_version=version.version,
                artifact_id=artifact.artifact_id,
                package_id=package_id,
                content_package_version=content_version,
                lesson_plan_versions=tuple(
                    str(plan) for plan in (loaded.manifest.get("lesson_plan_versions") or [])
                ),
                knowledge_index_version=str(
                    loaded.manifest.get("knowledge_index_version", "")
                ),
                teaching_graph_version=loaded.manifest.get("teaching_graph_version"),
                manifest_sha256=seal.manifest_sha256,
                content_digest=seal.content_digest,
                file_count=seal.file_count,
                total_bytes=seal.total_bytes,
                index_version=index.index_version,
                index_status=index.status,
                index_source_digest=index.source_digest,
                published_by=(published_by or "").strip() or institution_id,
            )
            created = True
        except CommitConflict:
            # Someone else committed this exact content between our read and our
            # write. Their publication is the answer to our request.
            superseded = 0
            publication = self._publications.find_publication(
                institution_id, version_id, content_version
            )
            created = False
            if publication is None:
                conflict = PublicationError(
                    "another publication won the commit for this version; reload and retry",
                    issue_code=ISSUE_COMMIT_CONFLICT,
                )
                self._record_blocked(
                    PUBLICATION_STAGE_COMMITTING, conflict.issue_code, institution_id,
                    version_id, artifact.artifact_id, package_id, content_version,
                )
                raise conflict
        else:
            self._telemetry.record_stage(
                stage=PUBLICATION_STAGE_COMMITTING,
                outcome="COMMITTED",
                institution_id=institution_id,
                version_id=version_id,
                artifact_id=artifact.artifact_id,
                package_id=package_id,
                content_package_version=content_version,
                detail=publication.publication_id,
            )
            self._telemetry.metrics.stages_committed += 1

        self._record_publish(
            publication, created=created, scenes=seal.scene_count, superseded=superseded
        )
        return publication, created

    # -- reads -----------------------------------------------------------------------
    def publication_for_version(
        self, institution_id: str, version_id: str, *, verify: bool = False
    ) -> dict[str, Any]:
        """The newest publication of a course version (its current one)."""

        self._courses.get_version(institution_id, version_id)
        publication = self._publications.latest_publication_for_version(
            institution_id, version_id
        )
        if publication is None:
            raise NotFoundError(f"course version {version_id!r} has not been published")
        return self._project(publication, verify=verify)

    def get_publication(
        self, institution_id: str, publication_id: str, *, verify: bool = False
    ) -> dict[str, Any]:
        """One publication by identity — including a superseded one.

        ``DEC-CONTENT-005``: a session that pinned an older publication keeps
        reading it, so retrieval must not be limited to the current version.
        """

        return self._project(self._require_publication(institution_id, publication_id), verify=verify)

    def list_publications(
        self, institution_id: str, course_id: str, *, limit: int = 50
    ) -> dict[str, Any]:
        self._courses.get_course(institution_id, course_id)
        publications = self._publications.list_publications(
            institution_id, course_id, limit=limit
        )
        return {
            "course_id": course_id,
            "publications": [publication.to_dict() for publication in publications],
        }

    def verify_integrity(self, institution_id: str, publication_id: str) -> dict[str, Any]:
        """Re-check the pinned package against the digest recorded at seal time.

        This is the read half of *"Published bytes cannot be overwritten"*: the seal
        cannot stop a later writer, but it makes a content change observable, and
        the answer is a report (``VERIFIED`` / ``MISMATCH`` / ``MISSING``) rather
        than an error, because a caller asking for verification wants the verdict.
        """

        return self._integrity(self._require_publication(institution_id, publication_id))

    # -- internals -------------------------------------------------------------------
    def _load(self, institution_id: str, artifact_id: str) -> Optional[LoadedPackage]:
        prefix = self._packages.package_prefix_for(institution_id, artifact_id)
        return read_package(self._object_store, prefix)

    def _require_approved(
        self,
        institution_id: str,
        artifact_id: str,
        version: CourseVersion,
        content_version: str,
    ) -> None:
        """Review policy: only content a teacher accepted for *this* content may publish.

        Three distinct refusals, because they need different fixes: no approval,
        an approval for content that has since changed (a rebuild, a new renderer, a
        fixed extractor), or a version that left ``APPROVED``.
        """

        decision = self._reviews.latest_decision(institution_id, artifact_id)
        if decision is None or decision.decision != DECISION_APPROVE:
            raise PublicationError(
                f"course version {version.version_id!r} has not been approved; "
                "review the built package and approve it before publishing",
                issue_code=ISSUE_NOT_APPROVED,
            )
        if decision.content_package_version != content_version:
            raise PublicationError(
                f"the approval covers content {decision.content_package_version!r} "
                f"but the built package is {content_version!r}; review it again",
                issue_code=ISSUE_STALE_APPROVAL,
            )
        if version.status != CourseVersionStatus.APPROVED.value:
            raise PublicationError(
                f"course version {version.version_id!r} is {version.status}, not "
                f"{CourseVersionStatus.APPROVED.value}",
                issue_code=ISSUE_WRONG_STATE,
            )

    def _require_publication(self, institution_id: str, publication_id: str) -> Publication:
        publication = self._publications.get_publication(institution_id, publication_id)
        if publication is None:
            raise NotFoundError(f"publication {publication_id!r} not found")
        return publication

    def _project(self, publication: Publication, *, verify: bool) -> dict[str, Any]:
        integrity = self._integrity(publication) if verify else None
        return publication.to_dict(integrity=integrity)

    def _integrity(self, publication: Publication) -> dict[str, Any]:
        """Verify the *recorded* package prefix, not the one the current renderer implies.

        The publication pins ``package_id``; a later renderer upgrade addresses a
        different prefix, so verification has to follow the pin.
        """

        loaded = read_package(self._object_store, package_prefix(publication.package_id))
        if loaded is None:
            report: dict[str, Any] = {
                "state": INTEGRITY_MISSING,
                "package_id": publication.package_id,
                "expected_digest": publication.content_digest,
                "observed_digest": "",
                "file_count": 0,
                "issues": ["MISSING_PACKAGE"],
            }
        else:
            report = verify_package(loaded.package, publication.content_digest).to_dict()
        self._telemetry.record_integrity(
            institution_id=publication.institution_id,
            publication_id=publication.publication_id,
            package_id=publication.package_id,
            state=str(report["state"]),
            file_count=int(report["file_count"]),
        )
        return report

    def _record_publish(
        self,
        publication: Publication,
        *,
        created: bool,
        scenes: Optional[int],
        superseded: int = 0,
    ) -> None:
        self._telemetry.record_publish(
            publication_id=publication.publication_id,
            institution_id=publication.institution_id,
            course_id=publication.course_id,
            version_id=publication.version_id,
            course_version=publication.course_version,
            artifact_id=publication.artifact_id,
            package_id=publication.package_id,
            content_package_version=publication.content_package_version,
            knowledge_index_version=publication.knowledge_index_version,
            teaching_graph_version=publication.teaching_graph_version,
            file_count=publication.file_count,
            total_bytes=publication.total_bytes,
            scene_count=scenes,
            created=created,
            superseded=superseded,
        )

    def _record_blocked(
        self,
        stage: str,
        issue_code: str,
        institution_id: str,
        version_id: str,
        artifact_id: str,
        package_id: str,
        content_package_version: str,
    ) -> None:
        self._telemetry.record_blocked(
            stage=stage,
            issue_code=issue_code,
            institution_id=institution_id,
            version_id=version_id,
            artifact_id=artifact_id,
            package_id=package_id,
            content_package_version=content_package_version,
        )


__all__ = ["PackageIntegrity", "PackageSeal", "PublicationService"]
