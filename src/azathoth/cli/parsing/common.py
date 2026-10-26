"""Shared command-line parsing primitives."""

import json
from argparse import ArgumentTypeError
from typing import cast

from pydantic import JsonValue

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
