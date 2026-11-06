"""Media types of workflow input content (ADR 0096, ADR 0112)."""

import json
import re
from collections.abc import Callable, Mapping
from pathlib import PurePath
from typing import NoReturn, cast

from pydantic import JsonValue

JSON_MEDIA_TYPE = "application/json"

TEXT_MEDIA_TYPE_PREFIX = "text/"

PDF_MEDIA_TYPE = "application/pdf"

PNG_MEDIA_TYPE = "image/png"

JPEG_MEDIA_TYPE = "image/jpeg"

WEBP_MEDIA_TYPE = "image/webp"

BINARY_MEDIA_TYPES = frozenset(
    {
        PDF_MEDIA_TYPE,
        PNG_MEDIA_TYPE,
        JPEG_MEDIA_TYPE,
        WEBP_MEDIA_TYPE,
    }
)
"""The binary media types Azathoth keeps and names by content handle (ADR 0112)."""

MEDIA_TYPE_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$",
)

MEDIA_TYPES_BY_EXTENSION = {
    ".json": JSON_MEDIA_TYPE,
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".csv": "text/csv",
    ".pdf": PDF_MEDIA_TYPE,
    ".png": PNG_MEDIA_TYPE,
    ".jpg": JPEG_MEDIA_TYPE,
    ".jpeg": JPEG_MEDIA_TYPE,
    ".webp": WEBP_MEDIA_TYPE,
}

PDF_HEADER = b"%PDF-"

PDF_HEADER_WINDOW = 1024
"""How many leading bytes may hold a PDF's header, as PDF readers allow."""

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

JPEG_SIGNATURE = b"\xff\xd8\xff"

ACCEPTED_MEDIA_TYPES_TEXT = (
    f"{JSON_MEDIA_TYPE}, text/* media types, "
    + ", ".join(sorted(BINARY_MEDIA_TYPES)[:-1])
    + f" and {sorted(BINARY_MEDIA_TYPES)[-1]}"
)
"""What the refusal of an unsupported media type says is accepted."""


class InputContentError(ValueError):
    """Raised when input content cannot be decoded as its media type."""


def is_binary_media_type(
    media_type: str,
) -> bool:
    """Return whether one media type is binary content, kept and named by a handle."""

    return media_type in BINARY_MEDIA_TYPES


def is_supported_media_type(
    media_type: str,
) -> bool:
    """Return whether Azathoth accepts content of one media type.

    JSON, every text media type, and the binary media types are supported.
    """

    return (
        media_type == JSON_MEDIA_TYPE
        or is_binary_media_type(media_type)
        or (
            media_type.startswith(TEXT_MEDIA_TYPE_PREFIX)
            and MEDIA_TYPE_PATTERN.match(media_type) is not None
        )
    )


def is_text_media_type(
    media_type: str,
) -> bool:
    """Return whether one media type is decoded as a string."""

    return media_type.startswith(TEXT_MEDIA_TYPE_PREFIX)


def validate_media_type(
    media_type: str,
) -> str:
    """Return one media type if it is well formed and supported.

    Raises:
        ValueError: The media type is not a lowercase `type/subtype` with no
            parameters, or Azathoth does not accept it.
    """

    if MEDIA_TYPE_PATTERN.match(media_type) is None:
        raise ValueError(
            f"Media type {media_type!r} must be a lowercase type/subtype with no parameters."
        )

    if not is_supported_media_type(media_type):
        raise ValueError(
            f"Media type {media_type!r} is not supported; "
            f"Azathoth accepts {ACCEPTED_MEDIA_TYPES_TEXT}."
        )

    return media_type


def check_binary_signature(
    content: bytes,
    media_type: str,
) -> None:
    """Refuse binary content that does not carry its media type's signature.

    A PDF holds its `%PDF-` header within its first 1024 bytes; a PNG starts
    with its eight-byte signature; a JPEG with its start-of-image marker; a
    WebP is a RIFF container holding `WEBP`. Nothing beyond the signature is
    checked.

    Raises:
        ValueError: The media type is not a binary media type.
        InputContentError: The content does not carry the signature.
    """

    check = _SIGNATURE_CHECKS.get(media_type)

    if check is None:
        raise ValueError(f"Media type {media_type!r} is not a binary media type.")

    problem = check(content)

    if problem is not None:
        raise InputContentError(f"Content is not {media_type}: {problem}.")


def decode_content(
    content: bytes,
    media_type: str,
) -> JsonValue:
    """Decode JSON or text input content into the value a workflow receives.

    Content is UTF-8, and a leading byte order mark is dropped. JSON content
    is parsed, rejecting non-finite numbers, which JSON does not have. Text
    content becomes a string. Binary content is never decoded: it is kept and
    named by a content handle (ADR 0112).

    Raises:
        InputContentError: The media type is not supported or is binary, or
            the content is not valid UTF-8 or, for JSON, not valid JSON.
    """

    try:
        validate_media_type(media_type)
    except ValueError as exc:
        raise InputContentError(str(exc)) from exc

    if is_binary_media_type(media_type):
        raise InputContentError(
            f"Media type {media_type} is binary: its content is stored and given to a "
            "workflow as a content handle, not decoded into a value."
        )

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputContentError(
            f"Content is not valid UTF-8 for media type {media_type}: {exc.reason} "
            f"at byte {exc.start}."
        ) from exc

    if is_text_media_type(media_type):
        return text

    try:
        parsed = json.loads(
            text,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise InputContentError(f"Content is not valid JSON: {exc.msg}.") from exc

    return cast(
        JsonValue,
        parsed,
    )


def infer_media_type(
    name: str,
) -> str | None:
    """Return the media type implied by a file name's extension, if it is known."""

    return MEDIA_TYPES_BY_EXTENSION.get(PurePath(name).suffix.lower())


def _reject_constant(
    constant: str,
) -> NoReturn:
    """Refuse the non-finite numbers Python's JSON parser accepts by default."""

    raise InputContentError(f"Content is not valid JSON: {constant} is not a JSON number.")


def _pdf_problem(
    content: bytes,
) -> str | None:
    """Return why content is not a PDF, or None when its header is in place."""

    if PDF_HEADER in content[:PDF_HEADER_WINDOW]:
        return None

    return f"no PDF header in its first {PDF_HEADER_WINDOW} bytes"


def _png_problem(
    content: bytes,
) -> str | None:
    """Return why content is not a PNG, or None when it starts with the signature."""

    if content.startswith(PNG_SIGNATURE):
        return None

    return "it does not start with the PNG signature"


def _jpeg_problem(
    content: bytes,
) -> str | None:
    """Return why content is not a JPEG, or None when it starts with its marker."""

    if content.startswith(JPEG_SIGNATURE):
        return None

    return "it does not start with a JPEG start-of-image marker"


def _webp_problem(
    content: bytes,
) -> str | None:
    """Return why content is not a WebP, or None when it is a RIFF holding WEBP."""

    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return None

    return "it is not a RIFF container holding WEBP"


_SIGNATURE_CHECKS: Mapping[str, Callable[[bytes], str | None]] = {
    PDF_MEDIA_TYPE: _pdf_problem,
    PNG_MEDIA_TYPE: _png_problem,
    JPEG_MEDIA_TYPE: _jpeg_problem,
    WEBP_MEDIA_TYPE: _webp_problem,
}
"""How each binary media type's signature is checked."""


__all__ = [
    "BINARY_MEDIA_TYPES",
    "JPEG_MEDIA_TYPE",
    "JSON_MEDIA_TYPE",
    "MEDIA_TYPES_BY_EXTENSION",
    "MEDIA_TYPE_PATTERN",
    "PDF_MEDIA_TYPE",
    "PNG_MEDIA_TYPE",
    "TEXT_MEDIA_TYPE_PREFIX",
    "WEBP_MEDIA_TYPE",
    "InputContentError",
    "check_binary_signature",
    "decode_content",
    "infer_media_type",
    "is_binary_media_type",
    "is_supported_media_type",
    "is_text_media_type",
    "validate_media_type",
]
