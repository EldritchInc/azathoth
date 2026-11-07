"""Reading the content a prompt shows, and the extractions it quotes (ADRs 0115, 0116).

A rendered prompt names content by handle. Before the model is called, the
engine checks that the run, or a run above it in its lineage, received each
piece under the media type the handle names, reads its bytes from the
content store, and checks them against the handle's digest and size: the
same checks a tool's content inputs pass (ADR 0114). A prompt that shows
content the run never received is refused before any provider is called.

A template variable bound to an extraction handle renders the extraction's
segments, each labelled by its ID, so a model can cite them (ADR 0116). Only
an extraction a step of the run, or of a run above it, kept is rendered.
"""

import asyncio
from uuid import UUID

from azathoth.citations import ExtractionError, ExtractionHandle, SegmentedText
from azathoth.context import active_step_lineage
from azathoth.inputs import ContentRef, content_bytes_digest
from azathoth.providers import Prompt, PromptContentError
from azathoth.tools.content import (
    ToolContentAccess,
    active_tool_content,
    kept_extractions,
    received_content,
)


async def read_prompt_content(
    prompt: Prompt,
    *,
    strategy_name: str | None = None,
) -> dict[str, bytes]:
    """Return the bytes of the content a prompt shows, by digest.

    A prompt of text shows none, and needs no content access.

    Raises:
        PromptContentError: The prompt shows content, but there is no content
            access or no running step, or it shows content the run never
            received, under another media type or size, or that the store
            lacks or holds under a wrong digest.
    """

    contents = prompt.contents()

    if not contents:
        return {}

    who = "A prompt" if strategy_name is None else f"Prompt strategy {strategy_name!r}"
    access = active_tool_content()

    if access is None:
        raise PromptContentError(
            f"{who} shows content, which this run cannot give: it has no content store."
        )

    step = active_step_lineage()

    if step is None:
        raise PromptContentError(f"{who} shows content, which only a workflow step can give.")

    return await asyncio.to_thread(
        _read,
        contents,
        who=who,
        access=access,
        run_id=step.step.run_id,
    )


def _read(
    contents: tuple[ContentRef, ...],
    *,
    who: str,
    access: ToolContentAccess,
    run_id: UUID,
) -> dict[str, bytes]:
    """Check and read each piece of content once, in the order the prompt shows it."""

    received = received_content(run_id, initial_context=access.initial_context)
    read: dict[str, bytes] = {}

    for handle in contents:
        media_types = received.get(handle.digest)

        if media_types is None:
            raise PromptContentError(
                f"{who} shows content {handle.digest}, which this run never received."
            )

        if handle.media_type not in media_types:
            raise PromptContentError(
                f"{who} shows content {handle.digest} as {handle.media_type}, but this run "
                f"received it as {', '.join(sorted(media_types))}."
            )

        if handle.digest in read:
            content = read[handle.digest]
        else:
            stored = access.store.get(handle.digest)

            if stored is None:
                raise PromptContentError(f"Content {handle.digest} is not in the content store.")

            if content_bytes_digest(stored) != handle.digest:
                raise PromptContentError(
                    f"Content {handle.digest} in the content store does not match its digest."
                )

            content = stored

        if len(content) != handle.size_bytes:
            raise PromptContentError(
                f"{who} shows content {handle.digest} as {handle.size_bytes} bytes, "
                f"but it holds {len(content)}."
            )

        read[handle.digest] = content

    return read


def kept_extraction(
    handle: ExtractionHandle,
    *,
    strategy_name: str | None = None,
) -> SegmentedText:
    """Return the extraction one handle names, if a step of the run or a run above it kept it.

    Raises:
        PromptContentError: There is no content access or no running step,
            no step of the run or a run above it kept the extraction, or the
            store lacks it, holds something else under its digest, or holds
            an extraction its handle does not describe.
    """

    who = "A prompt" if strategy_name is None else f"Prompt strategy {strategy_name!r}"
    access = active_tool_content()

    if access is None:
        raise PromptContentError(
            f"{who} shows extraction {handle.digest}, which this run cannot give: "
            "it has no content store."
        )

    step = active_step_lineage()

    if step is None:
        raise PromptContentError(
            f"{who} shows extraction {handle.digest}, which only a workflow step can give."
        )

    if handle.digest not in kept_extractions(step.step.run_id, access=access):
        raise PromptContentError(
            f"{who} shows extraction {handle.digest}, which no step of this run kept."
        )

    try:
        segmented = SegmentedText.load(access.store, handle.digest)
    except ExtractionError as exc:
        raise PromptContentError(str(exc)) from exc

    if segmented is None:
        raise PromptContentError(f"Extraction {handle.digest} is not in the content store.")

    if segmented.handle() != handle:
        raise PromptContentError(
            f"{who} shows extraction {handle.digest}, but its handle does not describe the "
            "extraction the content store holds."
        )

    return segmented


def extraction_source(
    variable: str,
    segmented: SegmentedText,
) -> str:
    """Return the text an extraction renders as under one variable's name.

    The extraction's segments are rendered in order, each as its ID in
    brackets and its text, separated by blank lines, inside a `source`
    element named by the variable, which a citation names as its source:

        <source name="claim">
        [p1.s1] Claim 0412.

        [p1.s2] Received on December 14.
        </source>
    """

    segments = "\n\n".join(
        f"[{segment.id}] {segmented.segment_text(segment)}" for segment in segmented.segments
    )
    body = f"{segments}\n" if segments else ""

    return f'<source name="{variable}">\n{body}</source>'


def render_extraction(
    variable: str,
    handle: ExtractionHandle,
    *,
    strategy_name: str | None = None,
) -> str:
    """Return the text an extraction bound to one template variable renders as.

    Raises:
        PromptContentError: The extraction cannot be rendered; see
            `kept_extraction`.
    """

    return extraction_source(variable, kept_extraction(handle, strategy_name=strategy_name))


__all__ = [
    "extraction_source",
    "kept_extraction",
    "read_prompt_content",
    "render_extraction",
]
