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


def error(code: ErrorCode, message: str) -> AppError:
    """Build an ``AppError`` with a specific code, preserving default status."""

    exc = AppError(message)
    exc.code = code
    return exc
