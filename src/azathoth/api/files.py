"""Files given to Azathoth through the service API (ADR 0121).

A file a run, an invocation or a benchmark case is given is checked as the
command line's `--input-file` is (ADR 0112): JSON and `text/*` content is
decoded into its value, and a PDF or an image is kept in the content store
by its digest, standing as its handle.
"""

import base64
from typing import Final

from azathoth.api.errors import InvalidArgumentError
from azathoth.api.models import RunFile
from azathoth.inputs import (
    DEFAULT_MAX_INPUT_BYTES,
    ContentStore,
    InlineInput,
    InputContentError,
    InputPolicy,
    InputProvenance,
    InputResolutionError,
    ResolvedInput,
    check_binary_signature,
    decode_content,
    is_binary_media_type,
    resolve_inline_input,
    validate_media_type,
)

INLINE_ONLY: Final = InputPolicy()
"""An invocation's input is the value given: no reference is resolved."""

MAX_INPUT_FILE_BYTES: Final = DEFAULT_MAX_INPUT_BYTES
"""The largest file a run or an invocation is given, as for `--input-file`."""

INPUT_FILE_NAME: Final = "The input file"
"""What a refusal of a file given as input calls it."""


def file_input(
    run_file: RunFile,
    *,
    max_bytes: int = MAX_INPUT_FILE_BYTES,
) -> InlineInput:
    """Return the inline input a file stands for, checked as `--input-file` is (ADR 0121).

    JSON and text content is decoded into its value. Binary content is
    checked against its media type's signature, and stands as base64 until
    it is resolved and kept (ADR 0112).

    Raises:
        InvalidArgumentError: The media type is not one Azathoth accepts, the
            content is larger than `max_bytes`, or it is not its media type.
    """

    try:
        media_type = validate_media_type(run_file.media_type)
    except ValueError as exc:
        raise InvalidArgumentError(str(exc)) from exc

    if len(run_file.content) > max_bytes:
        raise InvalidArgumentError(
            f"{INPUT_FILE_NAME} is larger than the limit of {max_bytes} bytes."
        )

    try:
        if is_binary_media_type(media_type):
            check_binary_signature(run_file.content, media_type)

            return InlineInput(
                value=base64.b64encode(run_file.content).decode("ascii"),
                media_type=media_type,
            )

        return InlineInput(
            value=decode_content(run_file.content, media_type),
            media_type=media_type,
        )
    except InputContentError as exc:
        raise InvalidArgumentError(str(exc)) from exc


def resolved_file(
    run_file: RunFile,
    store: ContentStore,
    *,
    uri: str | None = None,
) -> ResolvedInput:
    """Return what a file resolves to, its binary content kept in `store`.

    Its provenance is an inline input's: only binary content has one.
    Given the `uri` it was read from, it is that reference's, as the
    command line records a file it reads, and its content is kept as a
    read file's is (ADR 0117).

    Raises:
        InvalidArgumentError: The file is refused, as `file_input` refuses
            it, or its URI is blank.
    """

    try:
        resolved = resolve_inline_input(file_input(run_file), policy=INLINE_ONLY, store=store)
    except InputResolutionError as exc:
        raise InvalidArgumentError(str(exc)) from exc

    if uri is None:
        return resolved

    if not uri.strip():
        raise InvalidArgumentError("A file's URI must not be blank.")

    return resolved.model_copy(
        update={
            "provenance": InputProvenance(
                uri=uri,
                media_type=resolved.media_type,
                size_bytes=len(run_file.content),
                digest=store.put(run_file.content),
            ),
        }
    )


__all__ = [
    "INLINE_ONLY",
    "INPUT_FILE_NAME",
    "MAX_INPUT_FILE_BYTES",
    "file_input",
    "resolved_file",
]
