"""Tests for caller-visible production invocation rendering."""

from uuid import UUID

from azathoth.cli import render_production_invocation_result
from azathoth.workflows import (
    ProductionInvocationErrorCode,
    ProductionInvocationFailure,
    ProductionInvocationSuccess,
)

INVOCATION_ID = UUID("11111111-1111-1111-1111-111111111111")


def test_render_production_invocation_success() -> None:
    result = ProductionInvocationSuccess(
        invocation_id=INVOCATION_ID,
        result={
            "classification": "positive",
            "confidence": 0.98,
        },
    )

    rendered = render_production_invocation_result(
        result,
    )

    assert rendered == (
        f"Invocation ID: {INVOCATION_ID}\n"
        "Status: succeeded\n"
        "Result:\n"
        "{\n"
        '  "classification": "positive",\n'
        '  "confidence": 0.98\n'
        "}"
    )


def test_render_production_invocation_success_preserves_scalar_result() -> None:
    result = ProductionInvocationSuccess(
        invocation_id=INVOCATION_ID,
        result="success",
    )

    rendered = render_production_invocation_result(
        result,
    )

    assert rendered == (f'Invocation ID: {INVOCATION_ID}\nStatus: succeeded\nResult:\n"success"')


def test_render_production_invocation_failure() -> None:
    result = ProductionInvocationFailure(
        invocation_id=INVOCATION_ID,
        error_code=ProductionInvocationErrorCode.MODEL_UNAVAILABLE,
        message="The production model is unavailable.",
    )

    rendered = render_production_invocation_result(
        result,
    )

    assert rendered == (
        f"Invocation ID: {INVOCATION_ID}\n"
        "Status: failed\n"
        "Error: model_unavailable\n"
        "Message: The production model is unavailable."
    )


def test_render_production_invocation_failure_includes_public_metadata() -> None:
    result = ProductionInvocationFailure(
        invocation_id=INVOCATION_ID,
        error_code=ProductionInvocationErrorCode.INVALID_INPUT,
        message="Production workflow input is invalid.",
        metadata={
            "field": "message",
            "reason": "required",
        },
    )

    rendered = render_production_invocation_result(
        result,
    )

    assert rendered == (
        f"Invocation ID: {INVOCATION_ID}\n"
        "Status: failed\n"
        "Error: invalid_input\n"
        "Message: Production workflow input is invalid.\n"
        "Metadata:\n"
        "{\n"
        '  "field": "message",\n'
        '  "reason": "required"\n'
        "}"
    )


def test_render_production_invocation_failure_omits_empty_metadata() -> None:
    result = ProductionInvocationFailure(
        invocation_id=INVOCATION_ID,
        error_code=ProductionInvocationErrorCode.WORKFLOW_NOT_DEPLOYED,
        message="The requested workflow is not deployed to production.",
    )

    rendered = render_production_invocation_result(
        result,
    )

    assert "Metadata:" not in rendered


def test_render_production_invocation_result_contains_no_execution_evidence() -> None:
    result = ProductionInvocationSuccess(
        invocation_id=INVOCATION_ID,
        result={
            "answer": "public",
        },
    )

    rendered = render_production_invocation_result(
        result,
    )

    assert "Workflow ID:" not in rendered
    assert "Run ID:" not in rendered
    assert "Step " not in rendered
    assert "Strategy:" not in rendered
    assert "Provider:" not in rendered
    assert "Model:" not in rendered
    assert "Attempts:" not in rendered
    assert "Prompt Tokens:" not in rendered
    assert "Completion Tokens:" not in rendered
    assert "Output:" not in rendered
