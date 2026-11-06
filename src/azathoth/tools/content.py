"""Content inputs: giving a process tool the bytes a content handle names (ADR 0114).

A process implementation may declare some of its inputs content inputs. Each
must be a content handle naming content the run received: content a
`workflow.input.resolved` event recorded in the initial context of the run
or of a run above it in its lineage (ADR 0112). The engine reads the bytes
from the content store and writes them to a file of their own, and the tool
is given the file's path in place of the handle. The file is removed once the
tool is done. A tool never reads the content store itself.
"""

import asyncio
import tempfile
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from uuid import UUID

from pydantic import JsonValue

from azathoth.context import MAX_WORKFLOW_DEPTH, Context, LineageError, lineage_of
from azathoth.inputs import (
    JPEG_MEDIA_TYPE,
    PDF_MEDIA_TYPE,
    PNG_MEDIA_TYPE,
    WEBP_MEDIA_TYPE,
    ContentStore,
    content_bytes_digest,
    content_ref_from_value,
)
from azathoth.tools.exceptions import ToolExecutionError
from azathoth.tools.implementation import ToolImplementation

INPUT_RESOLVED_EVENT_TYPE: Final = "workflow.input.resolved"
"""The event recording a resolved input's provenance (ADR 0096, ADR 0112)."""

CONTENT_FILE_EXTENSIONS: Final[Mapping[str, str]] = {
    PDF_MEDIA_TYPE: ".pdf",
    PNG_MEDIA_TYPE: ".png",
    JPEG_MEDIA_TYPE: ".jpg",
    WEBP_MEDIA_TYPE: ".webp",
}
"""The extension a content input's file is given, by its media type."""

CONTENT_DIRECTORY_PREFIX: Final = "azathoth-content-"
"""The prefix of the temporary folder a tool's content files are written to."""


class ContentInputError(ToolExecutionError):
    """Raised when a tool's content input cannot be given to it."""


@dataclass(frozen=True)
class ToolContentAccess:
    """What a run gives its tools' content inputs from.

    `store` holds the content. `initial_context` returns the initial context
    a run started from, by its ID, or None when it is not known; a run's
    received content is read from initial contexts alone, so nothing a step
    adds while the run is under way can claim content the run never received.
    """

    store: ContentStore
    initial_context: Callable[[UUID], Context | None]


_ACTIVE_CONTENT: ContextVar[ToolContentAccess | None] = ContextVar(
    "azathoth_active_tool_content",
    default=None,
)


def active_tool_content() -> ToolContentAccess | None:
    """Return the content access the running step's tools are given, if any."""

    return _ACTIVE_CONTENT.get()


@contextmanager
def providing_tool_content(
    access: ToolContentAccess,
) -> Iterator[ToolContentAccess]:
    """Give tools content access for the work inside the block.

    The previous access is restored afterwards.
    """

    token = _ACTIVE_CONTENT.set(access)

    try:
        yield access
    finally:
        _ACTIVE_CONTENT.reset(token)


def received_content(
    run_id: UUID,
    *,
    initial_context: Callable[[UUID], Context | None],
) -> dict[str, frozenset[str]]:
    """Return the content one run received, by digest, with the media types recorded.

    The run's own initial context is read, then its parent's, as its lineage
    names it, and so on to the root. A run that is not known ends the walk,
    as does a lineage that loops back, and no more runs are read than
    workflows may nest.
    """

    received: dict[str, set[str]] = {}
    visited: set[UUID] = set()
    current: UUID | None = run_id

    while current is not None and current not in visited and len(visited) <= MAX_WORKFLOW_DEPTH:
        visited.add(current)
        context = initial_context(current)

        if context is None:
            break

        for event in context.by_type(INPUT_RESOLVED_EVENT_TYPE):
            digest = event.payload.get("digest")
            media_type = event.payload.get("media_type")

            if isinstance(digest, str) and isinstance(media_type, str):
                received.setdefault(digest, set()).add(media_type)

        try:
            lineage = lineage_of(context)
        except LineageError:
            break

        current = lineage.parent.run_id if lineage is not None else None

    return {digest: frozenset(media_types) for digest, media_types in received.items()}


@asynccontextmanager
async def content_input_files(
    implementation: ToolImplementation,
    inputs: dict[str, JsonValue],
    *,
    tool: str,
    access: ToolContentAccess | None,
    run_id: UUID | None,
) -> AsyncIterator[dict[str, JsonValue]]:
    """Give a tool its inputs, each content input written to a file of its own.

    Each content input's handle is replaced by its file's `path`, with the
    handle's `digest`, `media_type` and `size_bytes`. The files are written
    to a temporary folder, removed when the block ends, however it ends.
    Inputs of an implementation that takes no content inputs pass unchanged.

    Raises:
        ContentInputError: There is no content access or no running step, or
            a content input is missing, is not a content handle, names content
            the run never received or under another media type or size, or
            names content the store lacks or holds under a wrong digest.
    """

    if not implementation.content_inputs:
        yield inputs
        return

    if access is None:
        raise ContentInputError(
            f"Tool {tool} takes content inputs, which this run cannot give: "
            "it has no content store."
        )

    if run_id is None:
        raise ContentInputError(
            f"Tool {tool} takes content inputs, which only a workflow step can give."
        )

    with tempfile.TemporaryDirectory(prefix=CONTENT_DIRECTORY_PREFIX) as directory:
        given = await asyncio.to_thread(
            _write_content_inputs,
            implementation,
            inputs,
            tool=tool,
            access=access,
            run_id=run_id,
            directory=Path(directory),
        )

        yield given


def _write_content_inputs(
    implementation: ToolImplementation,
    inputs: dict[str, JsonValue],
    *,
    tool: str,
    access: ToolContentAccess,
    run_id: UUID,
    directory: Path,
) -> dict[str, JsonValue]:
    """Return a tool's inputs with each content input written to a file in a folder."""

    received = received_content(run_id, initial_context=access.initial_context)
    given = dict(inputs)

    for name in implementation.content_inputs:
        if name not in inputs:
            raise ContentInputError(f"Content input {name!r} of tool {tool} was not given.")

        handle = content_ref_from_value(inputs[name])

        if handle is None:
            raise ContentInputError(
                f"Content input {name!r} of tool {tool} must be a content handle."
            )

        media_types = received.get(handle.digest)

        if media_types is None:
            raise ContentInputError(
                f"Content input {name!r} of tool {tool} names content {handle.digest}, "
                "which this run never received."
            )

        if handle.media_type not in media_types:
            raise ContentInputError(
                f"Content input {name!r} of tool {tool} names content {handle.digest} as "
                f"{handle.media_type}, but this run received it as "
                f"{', '.join(sorted(media_types))}."
            )

        content = access.store.get(handle.digest)

        if content is None:
            raise ContentInputError(f"Content {handle.digest} is not in the content store.")

        if content_bytes_digest(content) != handle.digest:
            raise ContentInputError(
                f"Content {handle.digest} in the content store does not match its digest."
            )

        if len(content) != handle.size_bytes:
            raise ContentInputError(
                f"Content input {name!r} of tool {tool} names {handle.size_bytes} bytes, "
                f"but content {handle.digest} holds {len(content)}."
            )

        path = directory / f"{name}{CONTENT_FILE_EXTENSIONS[handle.media_type]}"
        path.write_bytes(content)

        given[name] = {
            "path": str(path),
            "digest": handle.digest,
            "media_type": handle.media_type,
            "size_bytes": handle.size_bytes,
        }

    return given


__all__ = [
    "CONTENT_DIRECTORY_PREFIX",
    "CONTENT_FILE_EXTENSIONS",
    "INPUT_RESOLVED_EVENT_TYPE",
    "ContentInputError",
    "ToolContentAccess",
    "active_tool_content",
    "content_input_files",
    "providing_tool_content",
    "received_content",
]
