"""Header-only image dimensions (V0-019).

The themed renderer places a picture in a media band and must keep its aspect
ratio. The compiler already holds the picture bytes (they travel to the renderer
through ``RenderRequest.media``), so the intrinsic size is read straight from the
file header: no decoding, no image library, and therefore no new dependency.

Only the headers needed to read the size are parsed. An unrecognised or truncated
image returns ``None`` and the caller falls back to the source placeholder's
aspect ratio — never a failure (``DEC-CONTENT-006``: the render degrades
explicitly, it does not crash).
"""

from __future__ import annotations

import struct
from typing import Optional

#: JPEG start-of-frame markers that carry the frame size (everything else is
#: either a different segment or, for the excluded ones, not a frame header).
_JPEG_SOF_MARKERS = frozenset(range(0xC0, 0xC4)) | frozenset(range(0xC5, 0xC8)) | frozenset(
    range(0xC9, 0xCC)
) | frozenset(range(0xCD, 0xD0))


def image_size(data: bytes) -> Optional[tuple[int, int]]:
    """``(width, height)`` in pixels, or ``None`` when it cannot be read."""

    if len(data) < 8:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return _png_size(data)
    if data[:2] == b"\xff\xd8":
        return _jpeg_size(data)
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return _gif_size(data)
    if data[:2] == b"BM":
        return _bmp_size(data)
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return _webp_size(data)
    return None


def _png_size(data: bytes) -> Optional[tuple[int, int]]:
    # IHDR is required to be the first chunk: length(4) + type(4) + w(4) + h(4).
    if len(data) < 24 or data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return _sane(width, height)


def _gif_size(data: bytes) -> Optional[tuple[int, int]]:
    if len(data) < 10:
        return None
    width, height = struct.unpack("<HH", data[6:10])
    return _sane(width, height)


def _bmp_size(data: bytes) -> Optional[tuple[int, int]]:
    if len(data) < 26:
        return None
    width, height = struct.unpack("<ii", data[18:26])
    return _sane(abs(width), abs(height))


def _webp_size(data: bytes) -> Optional[tuple[int, int]]:
    if len(data) < 30:
        return None
    fourcc = data[12:16]
    if fourcc == b"VP8 ":
        # Lossy: the frame header starts after the 3-byte start code + 3-byte
        # size, then a 2-byte dimension field at offset 26 in the chunk.
        if len(data) < 30:
            return None
        width = struct.unpack("<H", data[26:28])[0] & 0x3FFF
        height = struct.unpack("<H", data[28:30])[0] & 0x3FFF
        return _sane(width, height)
    if fourcc == b"VP8L":
        if len(data) < 25 or data[20] != 0x2F:
            return None
        bits = struct.unpack("<I", data[21:25])[0]
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return _sane(width, height)
    if fourcc == b"VP8X":
        if len(data) < 30:
            return None
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
        return _sane(width, height)
    return None


def _jpeg_size(data: bytes) -> Optional[tuple[int, int]]:
    """Walk JPEG segments to the first start-of-frame marker."""

    index = 2
    length = len(data)
    while index + 3 < length:
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        if marker in (0xFF, 0x01) or 0xD0 <= marker <= 0xD7:
            index += 2
            continue
        if index + 4 > length:
            return None
        segment_length = struct.unpack(">H", data[index + 2 : index + 4])[0]
        if segment_length < 2:
            return None
        if marker in _JPEG_SOF_MARKERS:
            if index + 9 > length:
                return None
            height, width = struct.unpack(">HH", data[index + 5 : index + 9])
            return _sane(width, height)
        index += 2 + segment_length
    return None


def _sane(width: int, height: int) -> Optional[tuple[int, int]]:
    """Reject absurd or zero dimensions so a bad header cannot skew layout."""

    if width <= 0 or height <= 0:
        return None
    if width > 100_000 or height > 100_000:
        return None
    return width, height


__all__ = ["image_size"]
