import pytest

from app.common.errors import AppError, ErrorCode
from app.security.validation import normalize_filename, validate_upload

MAX = 1000


def test_empty_file_rejected():
    with pytest.raises(AppError) as exc:
        validate_upload("deck.pptx", b"", max_bytes=MAX)
    assert exc.value.code is ErrorCode.EMPTY_FILE


def test_oversized_file_rejected():
    with pytest.raises(AppError) as exc:
        validate_upload("deck.pptx", b"PK\x03\x04" + b"0" * MAX, max_bytes=MAX)
    assert exc.value.code is ErrorCode.FILE_TOO_LARGE


def test_wrong_extension_rejected():
    with pytest.raises(AppError) as exc:
        validate_upload("notes.txt", b"PK\x03\x04", max_bytes=MAX)
    assert exc.value.code is ErrorCode.UNSUPPORTED_EXTENSION


def test_legacy_ppt_rejected():
    with pytest.raises(AppError) as exc:
        validate_upload("old.ppt", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", max_bytes=MAX)
    assert exc.value.code is ErrorCode.UNSUPPORTED_LEGACY_FORMAT


def test_legacy_ole_content_with_pptx_name_rejected():
    with pytest.raises(AppError) as exc:
        validate_upload("spoof.pptx", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest", max_bytes=MAX)
    assert exc.value.code is ErrorCode.UNSUPPORTED_LEGACY_FORMAT


def test_non_zip_content_with_pptx_name_rejected():
    with pytest.raises(AppError) as exc:
        validate_upload("spoof.pptx", b"not a zip", max_bytes=MAX)
    assert exc.value.code is ErrorCode.INVALID_FILE_TYPE


def test_valid_pptx_passes_and_normalizes_name():
    data = b"PK\x03\x04data"
    result = validate_upload("../../etc/pas swd.pptx", data, max_bytes=MAX)
    assert result.media_type.endswith("presentationml.presentation")
    assert "/" not in result.filename and " " not in result.filename
    assert result.size == len(data)


def test_normalize_filename_strips_path_and_controls():
    assert normalize_filename("a/b\\c\x00deck.pptx") == "c_deck.pptx"
    assert normalize_filename("") == "upload.pptx"
