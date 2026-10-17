"""Media (picture) part handling for the compiler (V0-018).

The compiler — not the renderer — is the only component allowed to open the
source package (``DEC-CONTENT-001``). Pictures are therefore read here and handed
to the render stage as bytes keyed by the ``media_ref`` already in the IR, so the
renderer stays a pure function of the IR plus injected media.

Dependency-free: ``zipfile`` only. There is deliberately no image re-encoding (no
image library is a production dependency), so a picture is inlined exactly as the
author saved it.
"""

from __future__ import annotations

import posixpath
import zipfile
from io import BytesIO
from typing import Iterable, Mapping, Optional

from app.common.errors import ErrorCode, error

#: Media types a browser can render inside an ``<image>`` element. Vector
#: metafiles (EMF/WMF) and TIFF are deliberately absent: no browser can draw them,
#: so they are reported as unsupported instead of being inlined as a broken image.
IMAGE_MEDIA_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}

#: Upper bound on the media bytes the render stage will hold for one document.
DEFAULT_MAX_MEDIA_BYTES = 64 * 1024 * 1024


def extension_of(part: Optional[str]) -> str:
    if not part:
        return ""
    return posixpath.splitext(part)[1].lower()


def media_type_for_part(part: Optional[str]) -> Optional[str]:
    """MIME type for a package part path, or ``None`` when not inlineable."""

    return IMAGE_MEDIA_TYPES.get(extension_of(part))


def read_media_parts(
    data: bytes,
    refs: Iterable[str],
    *,
    max_total_bytes: int = DEFAULT_MAX_MEDIA_BYTES,
) -> dict[str, bytes]:
    """Read the referenced parts from the package, keyed by part path.

    Only the requested parts are read (no XML parsing), a missing part is skipped
    rather than fatal, and the total is bounded so a hostile package cannot make
    the compiler hold an unbounded amount of media.
    """

    wanted = sorted({ref for ref in refs if ref})
    if not wanted:
        return {}
    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as exc:  # pragma: no cover - extraction validates first
        raise error(ErrorCode.INVALID_PPTX_PACKAGE, "not a valid OOXML/zip package") from exc

    found: dict[str, bytes] = {}
    total = 0
    with archive:
        names = set(archive.namelist())
        for part in wanted:
            if part not in names:
                continue
            info = archive.getinfo(part)
            if total + info.file_size > max_total_bytes:
                # Stop rather than fail: the render stage reports the missing
                # media as a placeholder + warning, and the deck still renders.
                break
            payload = archive.read(part)
            total += len(payload)
            found[part] = payload
    return found


def media_refs(document: Mapping) -> list[str]:
    """Every resolvable image ``media_ref`` in a serialised ``ContentIRDocument``.

    Kept dependency-light on plain dicts so both the live document and a loaded
    scene document can be inspected with the same helper.
    """

    refs: list[str] = []
    for slide in document.get("slides") or []:
        for obj in slide.get("objects") or []:
            ref = obj.get("media_ref")
            if ref and media_type_for_part(ref):
                refs.append(ref)
    return refs


def document_media_refs(document) -> list[str]:
    """Every image part the render stage needs bytes for, from a Content IR.

    Covers pictures, picture *fills* (``a:blipFill`` on a shape) and a picture
    slide background, and only parts this build can actually inline.
    """

    refs: list[str] = []

    def add(part: Optional[str]) -> None:
        if part and media_type_for_part(part):
            refs.append(part)

    def add_fill(fill: Optional[Mapping]) -> None:
        if isinstance(fill, Mapping) and fill.get("type") == "picture":
            add(fill.get("media_ref"))

    for scene in getattr(document, "slides", ()) or ():
        add_fill(getattr(scene, "background", None))
        for obj in getattr(scene, "objects", ()) or ():
            add(getattr(obj, "media_ref", None))
            add_fill(getattr(obj, "fill", None))
    return refs


__all__ = [
    "DEFAULT_MAX_MEDIA_BYTES",
    "IMAGE_MEDIA_TYPES",
    "document_media_refs",
    "extension_of",
    "media_refs",
    "media_type_for_part",
    "read_media_parts",
]
