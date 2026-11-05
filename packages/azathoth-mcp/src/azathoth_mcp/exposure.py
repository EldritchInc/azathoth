"""The exposure document: which promoted workflows the server offers, and how (ADR 0111).

An operator lists each workflow to expose with the tool name and description
an MCP client will see, and optionally a JSON Schema for the workflow's
input. Nothing that is not listed is ever offered.

A document looks like this:

```json
{
  "version": 1,
  "tools": [
    {
      "workflow_id": "7d1f3c2a-0b8e-4c55-9a61-2f0d6c1e9b44",
      "name": "summarize_ticket",
      "description": "Summarize a support ticket in three sentences.",
      "input_schema": {"type": "object", "required": ["ticket"]}
    }
  ]
}
```

The version is checked before the rest of a document, so a document written
for another version is reported as an unsupported version, never as a list
of fields this version does not know.
"""

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Literal, NoReturn
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    JsonValue,
    ValidationError,
    field_validator,
)

from azathoth.evaluation import json_schema_validator

EXPOSURE_VERSION = 1
"""The one exposure document version this release reads."""

SUPPORTED_EXPOSURE_VERSIONS = (EXPOSURE_VERSION,)

MAX_TOOL_NAME_LENGTH = 64

TOOL_NAME = re.compile(rf"[A-Za-z0-9_.-]{{1,{MAX_TOOL_NAME_LENGTH}}}")
"""What a tool name may hold, a set every MCP client accepts."""

GET_INVOCATION_TOOL = "get_invocation"
"""The server's own tool, which reads an invocation's result and evidence."""

RESERVED_TOOL_NAMES = frozenset({GET_INVOCATION_TOOL})
"""Tool names the server keeps for its own tools."""

VERSION_KEY = "version"


class ExposureDocumentError(ValueError):
    """Raised when an exposure document cannot be read, or is not valid."""


class ExposedWorkflow(BaseModel):
    """One promoted workflow offered as one tool.

    The input schema, when given, is a JSON Schema the workflow's input must
    satisfy. Without one, the tool accepts any JSON value as the input.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    workflow_id: UUID
    name: str
    description: str
    input_schema: JsonValue | None = None

    @field_validator("workflow_id", mode="before")
    @classmethod
    def require_uuid_text(
        cls,
        workflow_id: object,
    ) -> object:
        """Refuse a workflow ID that is neither a UUID nor a UUID written as text."""

        if isinstance(workflow_id, UUID):
            return workflow_id

        if isinstance(workflow_id, str):
            try:
                return UUID(workflow_id)
            except ValueError:
                pass

        raise ValueError(f"A workflow ID must be a UUID; got {json.dumps(workflow_id)}.")

    @field_validator("name", mode="before")
    @classmethod
    def require_tool_name(
        cls,
        name: object,
    ) -> object:
        """Refuse a tool name clients may not accept, or one the server keeps."""

        if not isinstance(name, str) or TOOL_NAME.fullmatch(name) is None:
            raise ValueError(
                f"A tool name holds 1 to {MAX_TOOL_NAME_LENGTH} letters, digits, "
                f'"_", "-" or "."; got {json.dumps(name)}.'
            )

        if name in RESERVED_TOOL_NAMES:
            raise ValueError(f"The tool name {json.dumps(name)} is kept for the server's own tool.")

        return name

    @field_validator("description", mode="before")
    @classmethod
    def require_description(
        cls,
        description: object,
    ) -> object:
        """Refuse a description that is not text, or is blank."""

        if not isinstance(description, str):
            raise ValueError(f"A tool's description must be text; got {json.dumps(description)}.")

        if not description.strip():
            raise ValueError("A tool's description must not be blank.")

        return description

    @field_validator("input_schema")
    @classmethod
    def require_json_schema(
        cls,
        input_schema: JsonValue | None,
    ) -> JsonValue | None:
        """Refuse an input schema that is not a valid JSON Schema."""

        if input_schema is not None:
            json_schema_validator(input_schema)

        return input_schema


class ExposureDocument(BaseModel):
    """Every workflow one server offers, each as one tool.

    Each workflow is exposed at most once, and each tool name is used once.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    version: Literal[1]
    tools: tuple[ExposedWorkflow, ...]

    @field_validator("tools")
    @classmethod
    def require_distinct_tools(
        cls,
        tools: tuple[ExposedWorkflow, ...],
    ) -> tuple[ExposedWorkflow, ...]:
        """Refuse a document that exposes nothing, or repeats a name or a workflow."""

        if not tools:
            raise ValueError("An exposure document must expose at least one workflow.")

        if (name := _first_repeated(tool.name for tool in tools)) is not None:
            raise ValueError(f"The tool name {json.dumps(name)} is used more than once.")

        if (workflow_id := _first_repeated(str(tool.workflow_id) for tool in tools)) is not None:
            raise ValueError(f"The workflow {workflow_id} is exposed more than once.")

        return tools

    def tool_named(
        self,
        name: str,
    ) -> ExposedWorkflow | None:
        """Return the exposed workflow offered under one tool name, if any."""

        return next((tool for tool in self.tools if tool.name == name), None)


def decode_exposure(
    data: JsonValue,
) -> ExposureDocument:
    """Decode one exposure document from JSON data.

    Raises:
        ExposureDocumentError: The data is not an object, names no, a
            non-integer or an unsupported version, or does not have an
            exposure document's shape.
    """

    if not isinstance(data, dict):
        _reject("An exposure document must be a JSON object.")

    _check_version(data)

    try:
        return ExposureDocument.model_validate(data)
    except ValidationError as exc:
        raise ExposureDocumentError(
            "The exposure document is not valid: " + "; ".join(_problems(exc))
        ) from exc


def parse_exposure(
    content: str | bytes,
) -> ExposureDocument:
    """Parse and decode one exposure document from JSON text.

    Bytes are decoded as UTF-8, with or without a byte order mark. `NaN` and
    the infinities are refused, since JSON has no such numbers.

    Raises:
        ExposureDocumentError: The content is not UTF-8, is not JSON, or does
            not decode as an exposure document.
    """

    if isinstance(content, bytes):
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            _reject("An exposure document must be UTF-8 text.")
    else:
        text = content.removeprefix("﻿")

    try:
        data = json.loads(
            text,
            parse_constant=_refuse_constant,
        )
    except json.JSONDecodeError as exc:
        _reject(
            f"An exposure document must be JSON: {exc.msg} at line {exc.lineno}, "
            f"column {exc.colno}."
        )
    except ValueError as exc:
        _reject(f"An exposure document must be JSON: {exc}")

    return decode_exposure(data)


def load_exposure(
    path: Path,
) -> ExposureDocument:
    """Read, parse and decode the exposure document in one file.

    Every message names the file, so an operator knows which one to fix.

    Raises:
        ExposureDocumentError: The file does not exist, cannot be read, or
            does not hold a valid exposure document.
    """

    try:
        content = path.read_bytes()
    except FileNotFoundError as exc:
        raise ExposureDocumentError(f"No exposure document at {path}.") from exc
    except OSError as exc:
        raise ExposureDocumentError(
            f"Cannot read the exposure document {path}: {exc.strerror}."
        ) from exc

    try:
        return parse_exposure(content)
    except ExposureDocumentError as exc:
        raise ExposureDocumentError(f"{path}: {exc}") from exc


def _check_version(
    data: dict[str, JsonValue],
) -> None:
    """Refuse a document that names no version, or one this release does not read."""

    if VERSION_KEY not in data:
        _reject("An exposure document must name its version.")

    version = data[VERSION_KEY]

    if isinstance(version, bool) or not isinstance(version, int):
        _reject(f"An exposure document's version must be an integer; got {json.dumps(version)}.")

    if version not in SUPPORTED_EXPOSURE_VERSIONS:
        _reject(
            f"Exposure document version {version} is not supported; supported versions: "
            + ", ".join(str(supported) for supported in SUPPORTED_EXPOSURE_VERSIONS)
            + "."
        )


def _problems(
    error: ValidationError,
) -> tuple[str, ...]:
    """Return one validation error's problems, each as its field and its message."""

    problems: list[str] = []

    for detail in error.errors(include_url=False):
        field = _field(detail["loc"])

        if detail["type"] == "missing":
            message = "is required"
        elif detail["type"] == "extra_forbidden":
            message = "is not a field of this document"
        elif detail["type"] == "tuple_type":
            message = "must be a list"
        elif detail["type"] == "model_type":
            message = "must be an object"
        else:
            message = str(detail["msg"]).removeprefix("Value error, ")

        problems.append(f"{field}: {message}")

    return tuple(problems)


def _field(
    location: tuple[int | str, ...],
) -> str:
    """Render a validation error's location, such as `tools[0].name`."""

    rendered = ""

    for part in location:
        rendered += f"[{part}]" if isinstance(part, int) else f".{part}" if rendered else part

    return rendered or "document"


def _first_repeated(
    values: Iterable[str],
) -> str | None:
    """Return the first value that appears a second time, if any does."""

    seen: set[str] = set()

    for value in values:
        if value in seen:
            return value

        seen.add(value)

    return None


def _refuse_constant(
    constant: str,
) -> NoReturn:
    """Refuse `NaN`, `Infinity` and `-Infinity`, which JSON does not define."""

    raise ValueError(f"{constant} is not a JSON number.")


def _reject(
    message: str,
) -> NoReturn:
    """Raise the exposure document error for one rejection."""

    raise ExposureDocumentError(message)


__all__ = [
    "EXPOSURE_VERSION",
    "GET_INVOCATION_TOOL",
    "MAX_TOOL_NAME_LENGTH",
    "RESERVED_TOOL_NAMES",
    "SUPPORTED_EXPOSURE_VERSIONS",
    "ExposedWorkflow",
    "ExposureDocument",
    "ExposureDocumentError",
    "decode_exposure",
    "load_exposure",
    "parse_exposure",
]
