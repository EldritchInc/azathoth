"""Shared JSON rendering for human-readable CLI output."""

import json

from pydantic import JsonValue


def render_json_value(
    value: JsonValue,
) -> str:
    """Render one JSON-compatible CLI value."""

    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
    )
