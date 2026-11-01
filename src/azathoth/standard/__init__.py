"""The standard tool library that ships inside the package (ADR 0095)."""

from importlib.resources import files

from azathoth.tools import (
    ToolDocument,
    decode_tool_document,
)

STANDARD_TOOL_FILES = (
    "run-workflow.json",
    "loop-workflow.json",
    "json-select.json",
    "json-object.json",
    "json-merge.json",
)
"""The packaged tool documents, in the order they are installed."""


def standard_tool_documents() -> tuple[ToolDocument, ...]:
    """Return the standard tool documents, in the order they are installed."""

    directory = files(__name__) / "tools"

    return tuple(
        decode_tool_document(
            (directory / name).read_text(
                encoding="utf-8",
            )
        )
        for name in STANDARD_TOOL_FILES
    )


__all__ = [
    "STANDARD_TOOL_FILES",
    "standard_tool_documents",
]
