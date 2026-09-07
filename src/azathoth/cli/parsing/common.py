"""Shared command-line parsing primitives."""

import json
from argparse import ArgumentTypeError
from typing import cast

from pydantic import JsonValue

COMMAND_ATTRIBUTE = "command"


def json_value(
    value: str,
) -> JsonValue:
    """Parse one JSON-compatible command-line value."""

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ArgumentTypeError(f"Expected value must be valid JSON: {exc.msg}") from exc

    return cast(
        JsonValue,
        parsed,
    )
