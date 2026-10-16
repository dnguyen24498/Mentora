"""Upload validation: size, filename normalization, extension, and magic bytes.

Deterministic and dependency-free (no file is ever executed). Addresses the
V0-002 acceptance criteria: invalid/oversized/spoofed files are rejected with
stable error codes, and sandbox/malicious-archive threats from the threat model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.common.errors import ErrorCode, error

#: OOXML presentation media type.
PPTX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
#: Legacy binary PowerPoint media type (rejected with a clear code, not misparsed).
LEGACY_PPT_MEDIA_TYPE = "application/vnd.ms-powerpoint"

ZIP_MAGIC = b"PK\x03\x04"
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class ValidatedUpload:
    filename: str
    media_type: str
    size: int


def normalize_filename(raw: str) -> str:
    """Strip directories/control characters and clamp to a safe basename."""

    base = (raw or "").replace("\\", "/").split("/")[-1]
    base = _UNSAFE.sub("_", base).strip("._-")
    if not base:
        base = "upload.pptx"
    return base[:200]


def validate_upload(filename: str, data: bytes, *, max_bytes: int) -> ValidatedUpload:
    if not data:
        raise error(ErrorCode.EMPTY_FILE, "uploaded file is empty")

    size = len(data)
    if size > max_bytes:
        raise error(ErrorCode.FILE_TOO_LARGE, f"file exceeds {max_bytes} bytes")

    normalized = normalize_filename(filename)
    lower = normalized.lower()

    if lower.endswith((".ppt", ".pptm", ".pps", ".ppsx", ".pot", ".potx")):
        # Legacy/binary or non-presentation Office types are out of V0 scope.
        raise error(
            ErrorCode.UNSUPPORTED_LEGACY_FORMAT,
            "only .pptx (OOXML) presentations are supported",
        )
    if not lower.endswith(".pptx"):
        raise error(ErrorCode.UNSUPPORTED_EXTENSION, "expected a .pptx file")

    if data.startswith(OLE_MAGIC):
        raise error(
            ErrorCode.UNSUPPORTED_LEGACY_FORMAT,
            "legacy binary .ppt content is not supported",
        )
    if not data.startswith(ZIP_MAGIC):
        # .pptx must be a ZIP/OOXML package; anything else is a spoofed extension.
        raise error(ErrorCode.INVALID_FILE_TYPE, "file does not look like a .pptx package")

    return ValidatedUpload(filename=normalized, media_type=PPTX_MEDIA_TYPE, size=size)
