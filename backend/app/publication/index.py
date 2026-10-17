"""The knowledge-index version a publication pins (V0-008).

``DEC-DATA-005``: *"Knowledge retrieval is tenant/course/version filtered and
index-version pinned."* A published content version therefore has exactly one
index version, and the pin has to exist **before** anything can retrieve through
it. That pin is what this module produces.

What it deliberately does not do is build index *content*. The task's out-of-scope
list excludes full semantic index content (that is V0-014, "Approved-content
indexing"), ``DEC-CONTENT-002`` requires a Baseline Content Package to stay usable
without any enrichment, and ``DEC-TECH-008`` (search/vector technology) is ``OPEN``.
Choosing a vector store or writing embeddings here would present an open decision
as accepted architecture.

So the index builder is a replaceable interface with a local baseline
implementation, exactly like the renderer (``DEC-TECH-005``) and the storage/
provider abstractions:

* :class:`BaselineIndexBuilder` declares the package's own
  ``knowledge_index_version`` — ``"unindexed"`` for a baseline package — and
  records the published content digest it was derived from;
* V0-014 replaces it with a builder that reads the approved content, materialises
  index documents and returns ``READY``. Nothing in the publication flow changes:
  the record, the pin and the atomicity stay where they are.

A builder that cannot produce an identity raises (:class:`PublicationError` with
``issue_code`` ``INDEX_FAILED``, or any ``AppError``); the publication is then
refused rather than published with a tuple that only looks complete.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.compiler.package_builder.models import BaselinePackage
from app.publication.models import INDEX_STATUS_UNINDEXED, IndexVersion
from app.publication.seal import PackageSeal


class IndexBuilder(ABC):
    """Establishes the knowledge-index version identity a publication pins."""

    @abstractmethod
    def build(
        self,
        *,
        institution_id: str,
        course_id: str,
        version_id: str,
        package: BaselinePackage,
        seal: PackageSeal,
    ) -> IndexVersion:
        """Return the index version for this published content version.

        Implementations must be **deterministic for a given content version**: the
        same ``(content_package_version, seal.content_digest)`` must yield the same
        ``index_version``, because the publication records the pin and a retry has
        to agree with it.
        """


class BaselineIndexBuilder(IndexBuilder):
    """Local baseline: pin the package's declared index version, build no content.

    A Baseline Content Package declares itself ``unindexed``
    (``DEC-CONTENT-002``), so the compatible index version for it is that same
    identity — there is nothing else to be compatible *with* yet. Recording it is
    not a formality: it is the row a later retrieval filters by, and it is written
    in the same transaction as the publication.
    """

    def build(
        self,
        *,
        institution_id: str,
        course_id: str,
        version_id: str,
        package: BaselinePackage,
        seal: PackageSeal,
    ) -> IndexVersion:
        declared = str(package.manifest.get("knowledge_index_version") or "unindexed")
        return IndexVersion(
            index_version=declared,
            status=INDEX_STATUS_UNINDEXED,
            # The published content this identity is compatible with: a retrieval
            # that finds a different digest is reading a different content version.
            source_digest=seal.content_digest,
        )


__all__ = ["BaselineIndexBuilder", "IndexBuilder"]
