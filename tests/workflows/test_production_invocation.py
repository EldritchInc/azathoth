"""Tests for immutable production workflow invocation contracts."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from azathoth.workflows import (
    ProductionInvocation,
    ProductionInvocationErrorCode,
    ProductionInvocationFailure,
    ProductionInvocationSuccess,
    create_production_invocation,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")
STEP_ID = UUID("33333333-3333-3333-3333-333333333333")
INVOCATION_ID = UUID("55555555-5555-5555-5555-555555555555")


def test_production_invocation_references_workflow() -> None:
    invocation = create_production_invocation(
        workflow_id=WORKFLOW_ID,
        payload={
            "request": "hello",
        },
    )

    assert invocation.workflow_id == WORKFLOW_ID


def test_production_invocation_contains_no_revision_identity() -> None:
    assert set(ProductionInvocation.model_fields) == {
        "id",
        "workflow_id",
        "initial_context",
        "caller_metadata",
        "created_at",
    }


def test_production_invocation_normalizes_object_payload_into_context() -> None:
    invocation = create_production_invocation(
        workflow_id=WORKFLOW_ID,
        payload={
            "request": "hello",
            "count": 3,
        },
    )

    assert len(invocation.initial_context.events) == 1

    event = invocation.initial_context.events[0]

    assert event.event_type == "production.invocation.received"
    assert event.producer == "azathoth.production"
    assert event.payload == {
        "input": {
            "request": "hello",
            "count": 3,
        },
    }


def test_production_invocation_normalizes_scalar_payload_into_context() -> None:
    invocation = create_production_invocation(
        workflow_id=WORKFLOW_ID,
        payload="hello",
    )

    event = invocation.initial_context.events[0]

    assert event.payload == {
        "input": "hello",
    }


def test_production_invocation_normalizes_array_payload_into_context() -> None:
    invocation = create_production_invocation(
        workflow_id=WORKFLOW_ID,
        payload=[
            "one",
            "two",
            "three",
        ],
    )

    event = invocation.initial_context.events[0]

    assert event.payload == {
        "input": [
            "one",
            "two",
            "three",
        ],
    }


def test_production_invocation_uses_creation_time_for_input_event() -> None:
    invocation = create_production_invocation(
        workflow_id=WORKFLOW_ID,
        payload={
            "request": "hello",
        },
    )

    event = invocation.initial_context.events[0]

    assert event.occurred_at == invocation.created_at


def test_production_invocation_keeps_caller_metadata_outside_context() -> None:
    caller_metadata = {
        "tenant_id": "acme",
        "trace_id": "trace-123",
    }

    invocation = create_production_invocation(
        workflow_id=WORKFLOW_ID,
        payload={
            "request": "hello",
        },
        caller_metadata=caller_metadata,
    )

    assert invocation.caller_metadata == caller_metadata

    event = invocation.initial_context.events[0]

    assert event.payload == {
        "input": {
            "request": "hello",
        },
    }

    assert "tenant_id" not in event.payload
    assert "trace_id" not in event.payload


def test_production_invocation_defaults_to_empty_caller_metadata() -> None:
    invocation = create_production_invocation(
        workflow_id=WORKFLOW_ID,
        payload=None,
    )

    assert invocation.caller_metadata == {}


def test_production_invocations_receive_independent_identity() -> None:
    first = create_production_invocation(
        workflow_id=WORKFLOW_ID,
        payload="same input",
    )

    second = create_production_invocation(
        workflow_id=WORKFLOW_ID,
        payload="same input",
    )

    assert first.id != second.id


def test_production_invocation_is_immutable() -> None:
    invocation = create_production_invocation(
        workflow_id=WORKFLOW_ID,
        payload="hello",
    )

    with pytest.raises(
        ValidationError,
        match="Instance is frozen",
    ):
        invocation.__setattr__(
            "workflow_id",
            UUID("66666666-6666-6666-6666-666666666666"),
        )


def test_production_invocation_success_contains_only_public_result_contract() -> None:
    result = ProductionInvocationSuccess(
        invocation_id=INVOCATION_ID,
        result={
            "classification": "positive",
            "confidence": 0.99,
        },
    )

    assert result.invocation_id == INVOCATION_ID

    assert result.result == {
        "classification": "positive",
        "confidence": 0.99,
    }

    assert set(ProductionInvocationSuccess.model_fields) == {
        "invocation_id",
        "result",
    }


def test_production_invocation_failure_records_stable_error_contract() -> None:
    result = ProductionInvocationFailure(
        invocation_id=INVOCATION_ID,
        error_code=ProductionInvocationErrorCode.MODEL_UNAVAILABLE,
        message="The configured production model is unavailable.",
        metadata={
            "step_id": str(STEP_ID),
        },
    )

    assert result.invocation_id == INVOCATION_ID

    assert result.error_code is ProductionInvocationErrorCode.MODEL_UNAVAILABLE

    assert result.message == ("The configured production model is unavailable.")

    assert result.metadata == {
        "step_id": str(STEP_ID),
    }


def test_production_invocation_failure_defaults_to_empty_metadata() -> None:
    result = ProductionInvocationFailure(
        invocation_id=INVOCATION_ID,
        error_code=ProductionInvocationErrorCode.WORKFLOW_EXECUTION_FAILED,
        message="Workflow execution failed.",
    )

    assert result.metadata == {}


def test_production_invocation_failure_requires_message() -> None:
    with pytest.raises(
        ValidationError,
    ):
        ProductionInvocationFailure(
            invocation_id=INVOCATION_ID,
            error_code=ProductionInvocationErrorCode.WORKFLOW_EXECUTION_FAILED,
            message="",
        )


def test_production_invocation_error_codes_are_stable() -> None:
    assert tuple(error_code.value for error_code in ProductionInvocationErrorCode) == (
        "workflow_not_deployed",
        "invalid_input",
        "model_unavailable",
        "no_approved_model_substitute",
        "tool_unavailable",
        "workflow_execution_failed",
        "timeout",
    )
