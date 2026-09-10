"""Tests for canonical external workflow input events."""

from azathoth.workflows import (
    WORKFLOW_INPUT_EVENT_TYPE,
    create_workflow_input_event,
)


def test_workflow_input_event_has_canonical_type() -> None:
    event = create_workflow_input_event(
        "hello",
        producer="test-client",
    )

    assert event.event_type == "workflow.input.received"
    assert event.event_type == WORKFLOW_INPUT_EVENT_TYPE


def test_workflow_input_event_wraps_scalar_payload() -> None:
    event = create_workflow_input_event(
        "hello",
        producer="test-client",
    )

    assert event.payload == {
        "input": "hello",
    }


def test_workflow_input_event_wraps_object_payload() -> None:
    event = create_workflow_input_event(
        {
            "request": "hello",
            "count": 3,
        },
        producer="test-client",
    )

    assert event.payload == {
        "input": {
            "request": "hello",
            "count": 3,
        },
    }


def test_workflow_input_event_wraps_array_payload() -> None:
    event = create_workflow_input_event(
        [
            "one",
            "two",
            "three",
        ],
        producer="test-client",
    )

    assert event.payload == {
        "input": [
            "one",
            "two",
            "three",
        ],
    }


def test_workflow_input_event_preserves_null_payload() -> None:
    event = create_workflow_input_event(
        None,
        producer="test-client",
    )

    assert event.payload == {
        "input": None,
    }


def test_workflow_input_event_records_producer() -> None:
    event = create_workflow_input_event(
        "hello",
        producer="benchmark-runner",
    )

    assert event.producer == "benchmark-runner"


def test_workflow_input_event_uses_context_event_defaults() -> None:
    event = create_workflow_input_event(
        "hello",
        producer="test-client",
    )

    assert event.occurred_at is not None
