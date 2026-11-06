"""Tests for extraction outputs: what a document tool extracted, checked and kept (ADR 0114)."""

import asyncio
import json
import sys
from uuid import UUID

import pytest
from pydantic import JsonValue, ValidationError

from azathoth.citations import (
    ExtractionHandle,
    Segment,
    SegmentedText,
    extraction_handle_from_value,
)
from azathoth.context import (
    Context,
    ContextEvent,
    LineageRun,
    LineageStep,
    StepLineage,
    running_step,
)
from azathoth.inputs import (
    InMemoryContentStore,
    InputProvenance,
    ResolvedInput,
    content_bytes_digest,
)
from azathoth.strategies import StrategyMetadata, StrategyOutcome, StrategyResourceBinding
from azathoth.tools import (
    EXTRACTION_RESOURCE_KIND,
    PROCESS_TOOL_RUNTIME,
    ExtractionOutputError,
    ProcessToolExecutor,
    ToolContentAccess,
    ToolImplementation,
    ToolStrategy,
    keep_extraction,
    providing_tool_content,
)
from azathoth.workflows import create_workflow_input_events

TOOL_ID = UUID("c1500000-0000-4000-8000-000000000001")

IMPLEMENTATION_ID = UUID("c1500000-0000-4000-8000-000000000002")

WORKFLOW_ID = UUID("c1500000-0000-4000-8000-000000000003")

STEP_ID = UUID("c1500000-0000-4000-8000-000000000004")

RUN_ID = UUID("c1500000-0000-4000-8000-000000000010")

PDF = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"

DIGEST = content_bytes_digest(PDF)

HANDLE: JsonValue = {
    "content": {"digest": DIGEST, "media_type": "application/pdf", "size_bytes": len(PDF)}
}

TEXT = "Claim 0412.\n\nReceived on December 14."

EXTRACTION = SegmentedText(
    tool="segment_claims",
    version="1",
    source_digest=DIGEST,
    media_type="application/pdf",
    text=TEXT,
    segments=(
        Segment(id="p1.s1", start=0, end=11, page=1),
        Segment(id="p1.s2", start=13, end=len(TEXT), page=1),
    ),
)

RETURN_SOURCE = """import json
import sys

inputs = json.load(sys.stdin)
json.dump(inputs["reply"], sys.stdout)
"""
"""A tool that returns, as its output, the reply it is given."""


def implementation(
    *,
    extraction_output: str | None = "extraction",
    content_inputs: tuple[str, ...] = ("document",),
) -> ToolImplementation:
    """Return one process implementation with an extraction output."""

    return ToolImplementation(
        id=IMPLEMENTATION_ID,
        tool_id=TOOL_ID,
        tool_version="1.0.0",
        runtime=PROCESS_TOOL_RUNTIME,
        source=RETURN_SOURCE,
        command=(sys.executable,),
        content_inputs=content_inputs,
        extraction_output=extraction_output,
    )


def strategy(
    *,
    extraction_output: str | None = "extraction",
) -> ToolStrategy:
    """Return the tool as a strategy named segment_claims."""

    return ToolStrategy(
        metadata=StrategyMetadata(
            id=TOOL_ID,
            name="segment_claims",
            description="Divide a claim into segments.",
            version="1.0.0",
        ),
        implementation=implementation(extraction_output=extraction_output),
        executor=ProcessToolExecutor(),
    )


def initial_context() -> Context:
    """Return a run's initial context, having received the test PDF."""

    return Context(
        events=create_workflow_input_events(
            ResolvedInput(
                value=HANDLE,
                media_type="application/pdf",
                provenance=InputProvenance(
                    uri="file:///claims/claim-0412.pdf",
                    media_type="application/pdf",
                    size_bytes=len(PDF),
                    digest=DIGEST,
                ),
            ),
            producer="azathoth.cli",
        )
    )


def run(
    reply: JsonValue,
    *,
    store: InMemoryContentStore | None = None,
    tool: ToolStrategy | None = None,
) -> StrategyOutcome:
    """Run the tool over the test PDF in a step, having it return a reply."""

    content_store = store if store is not None else InMemoryContentStore()
    content_store.put(PDF)

    access = ToolContentAccess(
        store=content_store,
        initial_context=lambda run_id: initial_context(),
    )
    step = StepLineage(
        step=LineageStep(workflow_id=WORKFLOW_ID, run_id=RUN_ID, step_id=STEP_ID, attempt=1),
        depth=0,
        root=LineageRun(workflow_id=WORKFLOW_ID, run_id=RUN_ID),
    )
    context = Context(
        events=tuple(
            ContextEvent(
                event_type="workflow.input.bound",
                payload={"name": name, "value": value},
                producer="workflow-runner",
            )
            for name, value in (("document", HANDLE), ("reply", reply))
        )
    )

    async def execute() -> StrategyOutcome:
        with providing_tool_content(access), running_step(step):
            return await (tool if tool is not None else strategy()).run(context)

    return asyncio.run(execute())


def reply(
    extraction: JsonValue,
    **others: JsonValue,
) -> JsonValue:
    """Return a tool output holding an extraction, and any other outputs."""

    return {"extraction": extraction, **others}


def test_the_resource_an_extraction_is_recorded_as() -> None:
    assert EXTRACTION_RESOURCE_KIND == "extraction"


def test_an_implementation_without_an_extraction_output_dumps_as_it_always_has() -> None:
    assert "extraction_output" not in implementation(extraction_output=None).model_dump(mode="json")


def test_an_implementation_dumps_its_extraction_output() -> None:
    assert implementation().model_dump(mode="json")["extraction_output"] == "extraction"


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        pytest.param(
            {"extraction_output": "the extraction"},
            "Extraction output 'the extraction' must be a name of letters, digits and underscores.",
            id="space",
        ),
        pytest.param(
            {"extraction_output": "extraction\n"},
            "Extraction output 'extraction\\n' must be a name of letters, digits and underscores.",
            id="trailing-newline",
        ),
        pytest.param(
            {"content_inputs": ()},
            "An extraction output holds what a tool extracted from its content inputs, "
            "so an implementation with one takes at least one content input.",
            id="no-content-inputs",
        ),
    ],
)
def test_an_extraction_output_is_validated(
    fields: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValidationError) as raised:
        ToolImplementation.model_validate({**implementation().model_dump(mode="json"), **fields})

    assert message in str(raised.value)


def test_an_extraction_is_kept_and_its_output_becomes_a_handle() -> None:
    store = InMemoryContentStore()

    outcome = run(reply(EXTRACTION.model_dump(mode="json"), pages=1), store=store)

    assert outcome.output == {"extraction": EXTRACTION.handle().to_value(), "pages": 1}
    assert store.get(EXTRACTION.digest()) == EXTRACTION.canonical_bytes()
    assert SegmentedText.load(store, EXTRACTION.digest()) == EXTRACTION


def test_an_extraction_is_recorded_as_a_resource_of_its_step() -> None:
    outcome = run(reply(EXTRACTION.model_dump(mode="json")))

    assert outcome.resources[0].kind == "tool"
    assert outcome.resources[1] == StrategyResourceBinding(
        kind="extraction",
        identifier=EXTRACTION.digest(),
        attributes={
            "tool": "segment_claims",
            "version": "1",
            "source_digest": DIGEST,
            "media_type": "application/pdf",
            "segments": 2,
        },
    )


def test_an_extraction_is_kept_as_its_canonical_form_whatever_the_tool_wrote() -> None:
    written = json.loads(json.dumps(EXTRACTION.model_dump(mode="json"), sort_keys=False))
    written["segments"] = [dict(reversed(list(item.items()))) for item in written["segments"]]

    outcome = run(reply(written))

    assert outcome.output == {"extraction": EXTRACTION.handle().to_value()}


def test_a_tool_without_an_extraction_output_returns_its_output_unchanged() -> None:
    raw = EXTRACTION.model_dump(mode="json")

    outcome = run(reply(raw), tool=strategy(extraction_output=None))

    assert outcome.output == {"extraction": raw}
    assert [resource.kind for resource in outcome.resources] == ["tool"]


def with_fields(
    **changes: JsonValue,
) -> JsonValue:
    """Return the test extraction's JSON with some fields changed."""

    data = EXTRACTION.model_dump(mode="json")
    data.update(changes)

    return data


@pytest.mark.parametrize(
    ("returned", "message"),
    [
        pytest.param(
            {"pages": 1},
            "Tool segment_claims returned no extraction output 'extraction'.",
            id="missing",
        ),
        pytest.param(
            reply(with_fields(source_digest=content_bytes_digest(b"other"))),
            "Tool segment_claims returned an extraction of content "
            f"{content_bytes_digest(b'other')}, which it was not given.",
            id="other-source",
        ),
        pytest.param(
            reply(with_fields(media_type="image/png")),
            f"Tool segment_claims returned an extraction of content {DIGEST} as image/png, "
            "but was given it as application/pdf.",
            id="other-media-type",
        ),
        pytest.param(
            reply(with_fields(tool="segment_text")),
            "Tool segment_claims returned an extraction that names the tool segment_text.",
            id="other-tool",
        ),
    ],
)
def test_an_extraction_must_be_of_content_the_tool_was_given(
    returned: JsonValue,
    message: str,
) -> None:
    store = InMemoryContentStore()

    with pytest.raises(ExtractionOutputError) as raised:
        run(returned, store=store)

    assert str(raised.value) == message
    assert not store.contains(EXTRACTION.digest())


@pytest.mark.parametrize(
    ("extraction", "problem"),
    [
        pytest.param("Claim 0412.", "Input should be a valid dictionary", id="string"),
        pytest.param(with_fields(text="Cafe\u0301"), "normalization form NFC", id="not-nfc"),
        pytest.param(
            with_fields(segments=[{"id": "p1.s1", "start": 0, "end": 99, "page": 1}]),
            "past the end of the text",
            id="segment-past-the-end",
        ),
    ],
)
def test_an_extraction_must_be_a_segmented_text(
    extraction: JsonValue,
    problem: str,
) -> None:
    with pytest.raises(ExtractionOutputError) as raised:
        run(reply(extraction))

    assert str(raised.value).startswith(
        "Tool segment_claims returned an extraction that is not a segmented text: "
    )
    assert problem in str(raised.value)


def test_an_output_that_is_not_an_object_has_no_extraction() -> None:
    #
    # A process tool's output is always an object; another runtime's need not be.
    #
    with pytest.raises(ExtractionOutputError) as raised:
        keep_extraction(
            implementation(),
            ["not", "an", "object"],
            tool="segment_claims",
            given={},
            store=InMemoryContentStore(),
        )

    assert str(raised.value) == "Tool segment_claims returned no extraction output 'extraction'."


def test_only_an_implementation_with_an_extraction_output_keeps_one() -> None:
    with pytest.raises(ValueError) as raised:
        keep_extraction(
            implementation(extraction_output=None),
            {},
            tool="segment_claims",
            given={},
            store=InMemoryContentStore(),
        )

    assert str(raised.value) == "Tool segment_claims names no extraction output."


def test_an_extraction_handle_names_the_digest_the_store_keeps() -> None:
    outcome = run(reply(EXTRACTION.model_dump(mode="json")))

    assert isinstance(outcome.output, dict)

    handle = extraction_handle_from_value(outcome.output["extraction"])

    assert isinstance(handle, ExtractionHandle)
    assert handle.digest == content_bytes_digest(EXTRACTION.canonical_bytes())


def keep(
    output: JsonValue,
    given: dict[str, JsonValue],
    *,
    content_inputs: tuple[str, ...] = ("document",),
) -> JsonValue:
    """Keep an extraction directly, as another runtime than process could ask to."""

    kept, _ = keep_extraction(
        implementation(content_inputs=content_inputs),
        output,
        tool="segment_claims",
        given=given,
        store=InMemoryContentStore(),
    )

    return kept


def test_a_string_output_naming_the_extraction_holds_none() -> None:
    with pytest.raises(ExtractionOutputError) as raised:
        keep("extraction", {})

    assert str(raised.value) == "Tool segment_claims returned no extraction output 'extraction'."


GIVEN_PDF: JsonValue = {
    "path": "/tmp/document.pdf",
    "digest": DIGEST,
    "media_type": "application/pdf",
    "size_bytes": len(PDF),
}


def test_the_source_may_be_any_of_the_content_inputs_given() -> None:
    kept = keep(
        reply(EXTRACTION.model_dump(mode="json")),
        {"cover": None, "document": GIVEN_PDF},
        content_inputs=("cover", "document"),
    )

    assert kept == {"extraction": EXTRACTION.handle().to_value()}


def test_a_given_input_without_a_media_type_gave_no_content() -> None:
    with pytest.raises(ExtractionOutputError) as raised:
        keep(reply(EXTRACTION.model_dump(mode="json")), {"document": {"digest": DIGEST}})

    assert str(raised.value) == (
        f"Tool segment_claims returned an extraction of content {DIGEST}, which it was not given."
    )
