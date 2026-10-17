"""Classified failures of the publication transition (V0-008).

``docs/state-machines/PUBLICATION_STATE_MACHINE.md`` requires an explicit failure
path per stage, and a client must be able to branch on the failure without
parsing prose. The API already maps ``AppError`` to a stable ``code`` + HTTP
status and passes a subclass's ``issue_code`` through the error envelope (V0-007),
so every stage failure here subclasses
:class:`~app.common.errors.PublicationBlockedError` — HTTP ``409``
``PUBLICATION_BLOCKED``: *the version must not be exposed* — and adds the precise
``issue_code``:

* ``NOT_APPROVED`` — the version was never approved for publication;
* ``STALE_APPROVAL`` — it *was* approved, but for different content: a rebuild, a
  new renderer or a fixed extractor produced a different
  ``content_package_version``, so the acceptance no longer covers what would be
  published;
* ``WRONG_STATE`` — the version is not ``APPROVED`` (already published, or back
  in review);
* ``CHECKSUM_MISMATCH`` / ``PACKAGE_INVALID`` — sealing found the package damaged
  (the ``issue_code`` is the validating code, e.g. ``CHECKSUM_MISMATCH``);
* ``INDEX_FAILED`` — the knowledge-index stage could not establish the index
  version a publication must pin (``DEC-DATA-005``);
* ``COMMIT_CONFLICT`` — the commit transaction lost a race and the winner could
  not be re-read; the caller retries and gets the winner idempotently.

Every one of them is raised **before** the commit transaction, so a refused
publication writes nothing: the version status is unchanged and no publication,
index-version or outbox row exists. A retry therefore starts from a clean state
(``DEC-RUNTIME-003``).

``DEC-RELIABILITY-002`` ("bounded failure and state integrity, not impossible
zero failure") is why a stage failure refuses the publication rather than
publishing something whose pinned tuple is only partly known: an unpublished
version is recoverable, a published one is immutable.
"""

from __future__ import annotations

from app.common.errors import PublicationBlockedError

#: The version has no current approval covering the content that would be published.
ISSUE_NOT_APPROVED = "NOT_APPROVED"
#: An approval exists, but for a different ``content_package_version``.
ISSUE_STALE_APPROVAL = "STALE_APPROVAL"
#: The version is not in the ``APPROVED`` state the transition requires.
ISSUE_WRONG_STATE = "WRONG_STATE"
#: Sealing could not establish the package's identity (fallback ``issue_code``).
ISSUE_PACKAGE_INVALID = "PACKAGE_INVALID"
#: The knowledge-index stage could not produce a version identity.
ISSUE_INDEX_FAILED = "INDEX_FAILED"
#: The commit transaction lost a race and the winning publication was not found.
ISSUE_COMMIT_CONFLICT = "COMMIT_CONFLICT"


class PublicationError(PublicationBlockedError):
    """A publication attempt refused before its commit point.

    Carries the precise ``issue_code`` the API surfaces alongside the stable
    ``PUBLICATION_BLOCKED`` code.
    """

    def __init__(self, message: str, *, issue_code: str = ISSUE_PACKAGE_INVALID) -> None:
        super().__init__(message)
        self.issue_code = issue_code


__all__ = [
    "ISSUE_COMMIT_CONFLICT",
    "ISSUE_INDEX_FAILED",
    "ISSUE_NOT_APPROVED",
    "ISSUE_PACKAGE_INVALID",
    "ISSUE_STALE_APPROVAL",
    "ISSUE_WRONG_STATE",
    "PublicationError",
]
