"""Sealing a built Baseline Content Package for publication (V0-008).

``docs/sequences/COURSE_UPLOAD_PUBLICATION.md`` ends the compiler pipeline with
``… -> review -> seal/index/commit -> published event``. Sealing is the first of
those three stages and the only one that reads the package: it **verifies** the
artifact and computes the digests a publication is pinned to.

It writes nothing. ``DEC-CONTENT-005`` (*"Published artifacts are immutable"*) is
satisfied structurally — the package is content-addressed and its manifest is
written last, so a reader that does not see the manifest sees no package
(``contracts/ctf/PACKAGE_LAYOUT.md``) — and the compiler stage is the only writer
of ``packages/``. The seal's job is therefore to make an overwrite *detectable*
rather than to try to make it impossible: the digests recorded here are re-checked
by :func:`verify_package` whenever a published package is read with verification
on.

Two digests are recorded, and the difference matters:

* ``manifest_sha256`` — the manifest *envelope* as sealed. Provenance only: a
  rebuild of the same content legitimately rewrites it with a new ``created_at``
  (``BaselinePackage.manifest_bytes`` is canonical, so this is the sha256 of the
  stored manifest while nothing has changed).
* ``content_digest`` — sha256 over the sealed **content**: every listed file's path
  and checksum, sorted. A published content version's ``content_digest`` must never
  change, and it is the digest a read verifies against. It deliberately does not
  cover the manifest envelope, so a legitimate rebuild is not a false alarm while
  a genuine content replacement is caught.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable

from app.compiler.package_builder.models import BaselinePackage, PackageFile
from app.compiler.validators.package import validate_package
from app.publication.errors import ISSUE_PACKAGE_INVALID, PublicationError

#: ``verify_package`` outcomes.
INTEGRITY_VERIFIED = "VERIFIED"
INTEGRITY_MISMATCH = "MISMATCH"
#: The package the publication pins is not in object storage at all.
INTEGRITY_MISSING = "MISSING"


@dataclass(frozen=True)
class PackageSeal:
    """The identity a publication pins, computed from the built package."""

    package_id: str
    content_package_version: str
    #: sha256 of the manifest envelope (provenance; may change on a rebuild).
    manifest_sha256: str
    #: sha256 of the content (must never change for a published version).
    content_digest: str
    file_count: int
    total_bytes: int
    scene_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "package_id": self.package_id,
            "content_package_version": self.content_package_version,
            "manifest_sha256": self.manifest_sha256,
            "content_digest": self.content_digest,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
            "scene_count": self.scene_count,
        }


@dataclass(frozen=True)
class PackageIntegrity:
    """Outcome of re-checking a stored package against a recorded content digest."""

    state: str
    package_id: str
    expected_digest: str
    observed_digest: str
    file_count: int
    issues: tuple[str, ...] = ()

    @property
    def verified(self) -> bool:
        return self.state == INTEGRITY_VERIFIED

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "package_id": self.package_id,
            "expected_digest": self.expected_digest,
            "observed_digest": self.observed_digest,
            "file_count": self.file_count,
            "issues": list(self.issues),
        }


def content_digest(files: Iterable[PackageFile]) -> str:
    """sha256 over the sealed content: each listed file's path and digest, sorted.

    Deterministic and order-independent, so it identifies the *set* of bytes the
    package references regardless of how the manifest happens to be ordered.
    """

    digest = hashlib.sha256()
    for package_file in sorted(files, key=lambda f: f.path):
        digest.update(package_file.path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(package_file.sha256.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def seal_package(package: BaselinePackage) -> PackageSeal:
    """Verify a built package and compute the identity a publication pins.

    Raises :class:`~app.publication.errors.PublicationError` when the package is
    damaged; the ``issue_code`` is the validating code (``CHECKSUM_MISMATCH``,
    ``MISSING_FILE_BYTES``, …) so a client can tell *what* is wrong.

    The V0-005 render fidelity gate is not re-run here — it is enforced by the
    builder, which refuses to write a package for a document that failed it — so
    sealing is about the artifact's integrity, not about review policy. Review
    policy is the approval precondition the service checks before sealing.
    """

    report = validate_package(package)
    if not report.ok:
        first = report.errors[0]
        raise PublicationError(
            f"package {package.package_id} cannot be sealed: {first.code}: {first.message}",
            issue_code=first.code or ISSUE_PACKAGE_INVALID,
        )

    return PackageSeal(
        package_id=package.package_id,
        content_package_version=str(package.manifest.get("content_package_version", "")),
        manifest_sha256=hashlib.sha256(package.manifest_bytes).hexdigest(),
        content_digest=content_digest(package.files),
        file_count=len(package.files),
        total_bytes=sum(f.byte_size for f in package.files) + len(package.manifest_bytes),
        scene_count=sum(
            1
            for f in package.files
            if f.path.startswith("scenes/") and f.path.endswith(".json")
        ),
    )


def verify_package(package: BaselinePackage, expected_digest: str) -> PackageIntegrity:
    """Re-check a stored package against the digest its publication recorded.

    Two independent checks, so a tampered package cannot pass by accident:

    * the recomputed ``content_digest`` equals the recorded one;
    * the package still validates against its own manifest (``CHECKSUM_MISMATCH``,
      ``MISSING_FILE_BYTES``, ``ORPHAN_FILE`` …), which names *which* file changed.
    """

    report = validate_package(package)
    observed = content_digest(package.files)
    return PackageIntegrity(
        state=INTEGRITY_VERIFIED if report.ok and observed == expected_digest else INTEGRITY_MISMATCH,
        package_id=package.package_id,
        expected_digest=expected_digest,
        observed_digest=observed,
        file_count=len(package.files),
        issues=tuple(issue.code for issue in report.errors),
    )


__all__ = [
    "INTEGRITY_MISMATCH",
    "INTEGRITY_MISSING",
    "INTEGRITY_VERIFIED",
    "PackageIntegrity",
    "PackageSeal",
    "content_digest",
    "seal_package",
    "verify_package",
]
