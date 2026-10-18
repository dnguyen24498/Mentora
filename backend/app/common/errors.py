"""Stable error codes and the base application error.

Error codes are part of the API contract: the upload endpoint returns them
unchanged so clients can branch without parsing prose (V0-002 acceptance
criteria: "rejected with stable error codes").
"""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    EMPTY_FILE = "EMPTY_FILE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    UNSUPPORTED_EXTENSION = "UNSUPPORTED_EXTENSION"
    UNSUPPORTED_LEGACY_FORMAT = "UNSUPPORTED_LEGACY_FORMAT"
    INVALID_FILE_TYPE = "INVALID_FILE_TYPE"
    INVALID_PPTX_PACKAGE = "INVALID_PPTX_PACKAGE"
    ARCHIVE_TOO_LARGE = "ARCHIVE_TOO_LARGE"
    STORAGE_FAILURE = "STORAGE_FAILURE"
    TENANT_ACCESS_DENIED = "TENANT_ACCESS_DENIED"
    NOT_FOUND = "NOT_FOUND"
    INVALID_REQUEST = "INVALID_REQUEST"
    # V0-005 (render stage): stable classification for renderer capability
    # failures and for the fidelity publication gate.
    RENDER_FAILED = "RENDER_FAILED"
    RENDERER_UNAVAILABLE = "RENDERER_UNAVAILABLE"
    PUBLICATION_BLOCKED = "PUBLICATION_BLOCKED"
    # V0-009 (class start): the class cannot be started because the version tuple
    # it must pin is not usable, and the join denial for a principal that is in
    # the tenant but not enrolled in the class.
    CLASS_NOT_READY = "CLASS_NOT_READY"
    NOT_ENROLLED = "NOT_ENROLLED"
    # V0-021 (identity): no valid session was presented (or the pre-auth
    # development shortcut is disabled), a session was valid but lacks the scope
    # the verb needs, credential verification was refused, and the credential
    # capability is unusable (breaker open / no adapter configured).
    UNAUTHENTICATED = "UNAUTHENTICATED"
    INSUFFICIENT_SCOPE = "INSUFFICIENT_SCOPE"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    AUTHENTICATION_UNAVAILABLE = "AUTHENTICATION_UNAVAILABLE"


class AppError(Exception):
    """Base class for errors that map to a stable code + HTTP status."""

    code: ErrorCode = ErrorCode.INVALID_REQUEST
    http_status: int = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ValidationError(AppError):
    http_status = 400


class NotFoundError(AppError):
    code = ErrorCode.NOT_FOUND
    http_status = 404


class TenantAccessError(AppError):
    code = ErrorCode.TENANT_ACCESS_DENIED
    http_status = 403


class StorageError(AppError):
    code = ErrorCode.STORAGE_FAILURE
    http_status = 502


class RendererUnavailableError(AppError):
    """The renderer capability is unusable (breaker open / not configured)."""

    code = ErrorCode.RENDERER_UNAVAILABLE
    http_status = 503


class PublicationBlockedError(AppError):
    """A document failed the fidelity gate and must not be published."""

    code = ErrorCode.PUBLICATION_BLOCKED
    http_status = 409


class ClassNotReadyError(AppError):
    """A class cannot start: the exact version tuple it must pin is not usable.

    ``docs/state-machines/CLASSROOM_SESSION_STATE_MACHINE.md`` names the
    ``SCHEDULED -> PREPARING -> ACTIVE`` transition; every refusal here happens
    before the commit point, so the class stays ``SCHEDULED`` and a retry after
    the fix starts from a clean state (``DEC-RELIABILITY-002``).
    """

    code = ErrorCode.CLASS_NOT_READY
    http_status = 409


class NotEnrolledError(AppError):
    """The principal is in the tenant but not enrolled in the class.

    Distinct from :class:`TenantAccessError`: the tenant boundary is satisfied,
    so this is a class-participation denial, not a cross-tenant one.
    """

    code = ErrorCode.NOT_ENROLLED
    http_status = 403


class UnauthenticatedError(AppError):
    """No usable principal: no session, an unknown/expired/revoked one, or the
    development tenant shortcut is switched off (V0-021)."""

    code = ErrorCode.UNAUTHENTICATED
    http_status = 401


class InsufficientScopeError(AppError):
    """The principal is authenticated but lacks the scope the verb requires.

    Distinct from :class:`TenantAccessError`: the tenant boundary is satisfied,
    so this is a *role/capability* denial (a student calling a teacher verb).
    """

    code = ErrorCode.INSUFFICIENT_SCOPE
    http_status = 403


class AuthenticationFailedError(AppError):
    """Credential verification was refused.

    The message is deliberately identical for "no such account" and "wrong
    credential", so the response is not an account-enumeration oracle.
    """

    code = ErrorCode.AUTHENTICATION_FAILED
    http_status = 401


class AuthenticationUnavailableError(AppError):
    """The credential capability cannot be used right now (breaker open, no
    adapter configured, or the deadline overran)."""

    code = ErrorCode.AUTHENTICATION_UNAVAILABLE
    http_status = 503


def error(code: ErrorCode, message: str) -> AppError:
    """Build an ``AppError`` with a specific code, preserving default status."""

    exc = AppError(message)
    exc.code = code
    return exc
