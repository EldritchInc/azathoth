"""Tests for the events that record a resolved workflow input (ADR 0096, ADR 0112)."""

from datetime import UTC, datetime

from pydantic import JsonValue

from azathoth.inputs import (
    InputOrigin,
    InputProvenance,
    ResolvedInput,
    content_bytes_digest,
)
from azathoth.workflows import (
    WORKFLOW_INPUT_EVENT_TYPE,
    WORKFLOW_INPUT_RESOLVED_EVENT_TYPE,
    create_workflow_input_event,
    create_workflow_input_events,
)

OCCURRED_AT = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)

PROVENANCE = InputProvenance(
    uri="file:///Users/you/chapter.md",
    media_type="text/markdown",
    size_bytes=7,
    digest=content_bytes_digest(b"Chapter"),
)


def test_resolved_event_type_is_named() -> None:
    assert WORKFLOW_INPUT_RESOLVED_EVENT_TYPE == "workflow.input.resolved"


def test_an_inline_input_records_exactly_todays_input_event() -> None:
    (event,) = create_workflow_input_events(
        ResolvedInput(value={"text": "hello"}, media_type="application/json"),
        producer="azathoth.cli",
        occurred_at=OCCURRED_AT,
    )

    expected = create_workflow_input_event(
        {"text": "hello"},
        producer="azathoth.cli",
        occurred_at=OCCURRED_AT,
    )

    assert (event.event_type, event.payload, event.producer, event.occurred_at) == (
        expected.event_type,
        expected.payload,
        expected.producer,
        expected.occurred_at,
    )


def test_a_reference_records_its_value_then_its_provenance() -> None:
    input_event, resolved_event = create_workflow_input_events(
        ResolvedInput(value="Chapter", media_type="text/markdown", provenance=PROVENANCE),
        producer="azathoth.cli",
        occurred_at=OCCURRED_AT,
    )

    assert input_event.event_type == WORKFLOW_INPUT_EVENT_TYPE
    assert input_event.payload == {"input": "Chapter"}

    assert resolved_event.event_type == WORKFLOW_INPUT_RESOLVED_EVENT_TYPE
    assert resolved_event.payload == {
        "uri": "file:///Users/you/chapter.md",
        "media_type": "text/markdown",
        "size_bytes": 7,
        "digest": content_bytes_digest(b"Chapter"),
    }
    assert resolved_event.producer == input_event.producer == "azathoth.cli"
    assert resolved_event.occurred_at == input_event.occurred_at == OCCURRED_AT


def test_both_events_share_one_time_when_none_is_given() -> None:
    input_event, resolved_event = create_workflow_input_events(
        ResolvedInput(value="Chapter", media_type="text/markdown", provenance=PROVENANCE),
        producer="azathoth.cli",
    )

    assert input_event.occurred_at == resolved_event.occurred_at
    assert input_event.occurred_at.tzinfo is not None


def test_an_inline_text_input_adds_no_provenance_event() -> None:
    events = create_workflow_input_events(
        ResolvedInput(value="hello", media_type="text/plain"),
        producer="azathoth.cli",
    )

    assert [event.event_type for event in events] == [WORKFLOW_INPUT_EVENT_TYPE]


def test_an_inline_input_with_provenance_records_it_without_a_uri() -> None:
    digest = content_bytes_digest(b"%PDF-1.7")
    handle: JsonValue = {
        "content": {"digest": digest, "media_type": "application/pdf", "size_bytes": 8}
    }

    input_event, resolved_event = create_workflow_input_events(
        ResolvedInput(
            value=handle,
            media_type="application/pdf",
            provenance=InputProvenance(
                inline=True,
                origin=InputOrigin(uri="s3://claims-intake/claim-0412.pdf", etag="9b2c"),
                media_type="application/pdf",
                size_bytes=8,
                digest=digest,
            ),
        ),
        producer="azathoth.jobs",
        occurred_at=OCCURRED_AT,
    )

    assert input_event.payload == {"input": handle}
    assert resolved_event.event_type == WORKFLOW_INPUT_RESOLVED_EVENT_TYPE
    assert resolved_event.payload == {
        "inline": True,
        "origin": {"uri": "s3://claims-intake/claim-0412.pdf", "etag": "9b2c"},
        "media_type": "application/pdf",
        "size_bytes": 8,
        "digest": digest,
    }
