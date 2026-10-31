"""Media types of workflow input content (ADR 0096)."""

import json
import re
from pathlib import PurePath
from typing import NoReturn, cast

from pydantic import JsonValue

JSON_MEDIA_TYPE = "application/json"

TEXT_MEDIA_TYPE_PREFIX = "text/"

MEDIA_TYPE_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$",
)

MEDIA_TYPES_BY_EXTENSION = {
    ".json": JSON_MEDIA_TYPE,
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".csv": "text/csv",
}


class InputContentError(ValueError):
    """Raised when input content cannot be decoded as its media type."""


def is_supported_media_type(
    media_type: str,
) -> bool:
    """Return whether Azathoth can decode content of one media type.

    JSON and every text media type are supported. Binary media types arrive
    with multimodal inputs.
    """

    return media_type == JSON_MEDIA_TYPE or (
        media_type.startswith(TEXT_MEDIA_TYPE_PREFIX)
        and MEDIA_TYPE_PATTERN.match(media_type) is not None
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
            parameters, or Azathoth cannot decode it.
    """

    if MEDIA_TYPE_PATTERN.match(media_type) is None:
        raise ValueError(
            f"Media type {media_type!r} must be a lowercase type/subtype with no parameters."
        )

    if not is_supported_media_type(media_type):
        raise ValueError(
            f"Media type {media_type!r} is not supported; "
            f"Azathoth accepts {JSON_MEDIA_TYPE} and text/* media types."
        )

    return media_type


def decode_content(
    content: bytes,
    media_type: str,
) -> JsonValue:
    """Decode input content into the value a workflow receives.

    Content is UTF-8, and a leading byte order mark is dropped. JSON content
    is parsed, rejecting non-finite numbers, which JSON does not have. Text
    content becomes a string.

    Raises:
        InputContentError: The media type is not supported, or the content is
            not valid UTF-8 or, for JSON, not valid JSON.
    """

    try:
        validate_media_type(media_type)
    except ValueError as exc:
        raise InputContentError(str(exc)) from exc

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


__all__ = [
    "JSON_MEDIA_TYPE",
    "MEDIA_TYPES_BY_EXTENSION",
    "MEDIA_TYPE_PATTERN",
    "TEXT_MEDIA_TYPE_PREFIX",
    "InputContentError",
    "decode_content",
    "infer_media_type",
    "is_supported_media_type",
    "is_text_media_type",
    "validate_media_type",
]
