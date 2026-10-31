"""Shared command-line parsing primitives."""

import json
from argparse import ArgumentTypeError
from typing import cast

from pydantic import JsonValue

from azathoth.inputs import validate_media_type

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
