"""How prompt strategies interpret a language model's reply."""

import json
import re
from enum import StrEnum
from typing import cast

from pydantic import JsonValue

FENCE_OPENING = re.compile(r"```[A-Za-z0-9_-]*")


class PromptOutputFormat(StrEnum):
    """The form a prompt strategy's output takes.

    `text` returns the model's reply unchanged. `json` parses the reply as one
    JSON value, so later workflow steps can read fields of it by path.
    """

    TEXT = "text"
    JSON = "json"


def parse_json_reply(
    reply: str,
) -> JsonValue:
    """Parse one model reply as a JSON value.

    Surrounding whitespace and one surrounding Markdown code fence, with or
    without a language tag, are tolerated. Anything else must be valid JSON.

    Raises:
        json.JSONDecodeError: The reply is not one JSON value.
    """

    text = reply.strip()
    lines = text.split("\n")

    if (
        len(lines) >= 2
        and FENCE_OPENING.fullmatch(lines[0].strip()) is not None
        and lines[-1].strip() == "```"
    ):
        inner = "\n".join(lines[1:-1])

        if "```" not in inner:
            text = inner

    return cast(
        JsonValue,
        json.loads(text),
    )
