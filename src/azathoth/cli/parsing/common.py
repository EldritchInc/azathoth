"""Shared command-line parsing primitives."""

import json
from argparse import ArgumentTypeError
from typing import cast

from pydantic import JsonValue

from azathoth.evaluation.models import CitedSegment
from azathoth.inputs import validate_media_type
from azathoth.sensitivity import Sensitivity
from azathoth.workflows import validate_idempotency_key

COMMAND_ATTRIBUTE = "command"


def json_value(
    value: str,
) -> JsonValue:
    """Parse one JSON-compatible command-line value.

    The message names no particular option, because every JSON option shares
    this parser and argparse already prefixes the option name.

    Raises:
        ArgumentTypeError: The value is not valid JSON.
    """

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ArgumentTypeError(f"Value must be valid JSON: {exc.msg}") from exc

    return cast(
        JsonValue,
        parsed,
    )


def idempotency_key(
    value: str,
) -> str:
    """Parse one idempotency key command-line value (ADR 0097).

    Raises:
        ArgumentTypeError: The key is empty, too long, or holds a control
            character.
    """

    try:
        return validate_idempotency_key(value)
    except ValueError as exc:
        raise ArgumentTypeError(str(exc)) from exc


def media_type(
    value: str,
) -> str:
    """Parse one supported media type command-line value (ADR 0096).

    Raises:
        ArgumentTypeError: The media type is malformed or not supported.
    """

    try:
        return validate_media_type(value)
    except ValueError as exc:
        raise ArgumentTypeError(str(exc)) from exc


def sensitivity(
    value: str,
) -> Sensitivity:
    """Parse one sensitivity label command-line value (ADR 0123).

    Raises:
        ArgumentTypeError: The value is not public, internal or restricted.
    """

    try:
        return Sensitivity(value)
    except ValueError as exc:
        labels = ", ".join(label.value for label in Sensitivity)

        raise ArgumentTypeError(f"{value!r} is not a sensitivity; choose {labels}.") from exc


def cited_segment(
    value: str,
) -> CitedSegment:
    """Parse one `SOURCE:SEGMENT` command-line value naming a segment to cite (ADR 0117).

    Raises:
        ArgumentTypeError: The value is not a source and a segment, both
            non-empty, separated by a colon.
    """

    source, separator, segment = value.partition(":")

    if not separator or not source or not segment:
        raise ArgumentTypeError(f"Expected SOURCE:SEGMENT, such as claim:p1.s2, got {value!r}.")

    return CitedSegment(source=source, segment=segment)


def positive_integer(
    value: str,
) -> int:
    """Parse one strictly positive integer command-line value."""

    try:
        parsed = int(value)
    except ValueError as exc:
        raise ArgumentTypeError(f"Expected a positive integer, got {value!r}.") from exc

    if parsed < 1:
        raise ArgumentTypeError(f"Expected a positive integer, got {value!r}.")

    return parsed
