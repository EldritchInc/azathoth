"""The standard tool library that ships inside the package (ADR 0095)."""

from importlib.resources import files
from typing import Final

from azathoth.revisions import Author
from azathoth.tools import (
    ToolDocument,
    decode_tool_document,
)

STANDARD_TOOL_FILES = (
    "run-workflow.json",
    "loop-workflow.json",
    "map-workflow.json",
    "json-select.json",
    "json-object.json",
    "json-merge.json",
    "validate-json.json",
    "chunk-text.json",
    "join-text.json",
    "render-template.json",
    "split-s3-object.json",
    "read-s3-object.json",
    "segment-pdf.json",
)
"""The packaged tool documents, in the order they are installed."""

STANDARD_TOOL_AUTHOR: Final = Author(name="Azathoth")
"""Who installed standard tool revisions are recorded as authored by (ADR 0122).

The standard library is Azathoth's own work, the same on every instance, so
installing it never needs to know who is installing.
"""


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
    "STANDARD_TOOL_AUTHOR",
    "STANDARD_TOOL_FILES",
    "standard_tool_documents",
]
