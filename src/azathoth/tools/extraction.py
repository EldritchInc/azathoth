"""Extraction outputs: what a document tool extracted, checked and kept (ADR 0114).

An implementation with content inputs may name one of its outputs its
extraction output. The engine requires that output to be a segmented text
(ADR 0113) of one of the contents the tool was given, under the media type
it was given and the tool's own name. It keeps the text in the content store,
records it as a resource of the step, and replaces the output with a handle
naming it. A tool never writes the content store itself.
"""

from collections.abc import Mapping
from typing import Final

from pydantic import JsonValue, ValidationError

from azathoth.citations import SegmentedText
from azathoth.inputs import ContentStore
from azathoth.strategies import StrategyResourceBinding
from azathoth.tools.exceptions import ToolExecutionError
from azathoth.tools.implementation import ToolImplementation

EXTRACTION_RESOURCE_KIND: Final = "extraction"
"""The kind of resource a step records each kept extraction as."""


class ExtractionOutputError(ToolExecutionError):
    """Raised when a tool's extraction output cannot be kept."""


def keep_extraction(
    implementation: ToolImplementation,
    output: JsonValue,
    *,
    tool: str,
    given: Mapping[str, JsonValue],
    store: ContentStore,
) -> tuple[JsonValue, StrategyResourceBinding]:
    """Check, keep and record a tool's extraction; return its output and the record.

    `given` holds the inputs the tool was given, each content input as the
    file it was written to. The extraction output is replaced by the handle
    of the kept extraction; the rest of the output is unchanged.

    Raises:
        ValueError: The implementation names no extraction output.
        ExtractionOutputError: The output holds no extraction, or one that is
            not a segmented text, names another tool, or is of content the
            tool was not given, or not under the media type it was given.
    """

    name = implementation.extraction_output

    if name is None:
        raise ValueError(f"Tool {tool} names no extraction output.")

    if not isinstance(output, dict) or name not in output:
        raise ExtractionOutputError(f"Tool {tool} returned no extraction output {name!r}.")

    try:
        segmented = SegmentedText.model_validate(output[name])
    except ValidationError as exc:
        raise ExtractionOutputError(
            f"Tool {tool} returned an extraction that is not a segmented text: {exc}"
        ) from exc

    if segmented.tool != tool:
        raise ExtractionOutputError(
            f"Tool {tool} returned an extraction that names the tool {segmented.tool}."
        )

    media_types = _given_content(implementation, given)
    source = segmented.source_digest

    if source not in media_types:
        raise ExtractionOutputError(
            f"Tool {tool} returned an extraction of content {source}, which it was not given."
        )

    if segmented.media_type not in media_types[source]:
        raise ExtractionOutputError(
            f"Tool {tool} returned an extraction of content {source} as "
            f"{segmented.media_type}, but was given it as "
            f"{', '.join(sorted(media_types[source]))}."
        )

    digest = segmented.store(store)
    handle = segmented.handle()

    return (
        {**output, name: handle.to_value()},
        StrategyResourceBinding(
            kind=EXTRACTION_RESOURCE_KIND,
            identifier=digest,
            attributes={
                "tool": segmented.tool,
                "version": segmented.version,
                "source_digest": source,
                "media_type": segmented.media_type,
                "segments": len(segmented.segments),
            },
        ),
    )


def _given_content(
    implementation: ToolImplementation,
    given: Mapping[str, JsonValue],
) -> dict[str, set[str]]:
    """Return the digests of the content a tool was given, with their media types."""

    media_types: dict[str, set[str]] = {}

    for name in implementation.content_inputs:
        document = given.get(name)

        if not isinstance(document, dict):
            continue

        digest = document.get("digest")
        media_type = document.get("media_type")

        if isinstance(digest, str) and isinstance(media_type, str):
            media_types.setdefault(digest, set()).add(media_type)

    return media_types


__all__ = [
    "EXTRACTION_RESOURCE_KIND",
    "ExtractionOutputError",
    "keep_extraction",
]
