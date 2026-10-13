"""Tests for human-readable production invocation history rendering."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import JsonValue

from azathoth.cli import (
    render_production_invocation,
    render_production_invocation_summaries,
)
from azathoth.context import Context
from azathoth.workflows import (
    ProductionInvocation,
    ProductionInvocationErrorCode,
    ProductionInvocationFailure,
    ProductionInvocationResult,
    ProductionInvocationSuccess,
    create_production_invocation,
)

WORKFLOW_ID = UUID("11111111-1111-1111-1111-111111111111")

FIRST_RUN_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1")

CREATED_AT = datetime(
    2026,
    10,
    9,
    17,
    0,
    tzinfo=UTC,
)


def create_invocation(
    payload: JsonValue,
    *,
    caller_metadata: dict[str, JsonValue] | None = None,
) -> ProductionInvocation:
    """Create one invocation with a deterministic creation time."""

    invocation = create_production_invocation(
        workflow_id=WORKFLOW_ID,
        payload=payload,
        caller_metadata=caller_metadata,
    )

    return invocation.model_copy(
        update={
            "created_at": CREATED_AT,
        }
    )


def test_summaries_render_outcome_and_run_in_given_order() -> None:
    succeeded = create_invocation({"text": "first"})
    failed = create_invocation({"text": "second"})
    pending = create_invocation({"text": "third"})

    results: dict[UUID, ProductionInvocationResult] = {
        succeeded.id: ProductionInvocationSuccess(
            invocation_id=succeeded.id,
            result={"answer": "OK"},
        ),
        failed.id: ProductionInvocationFailure(
            invocation_id=failed.id,
            error_code=ProductionInvocationErrorCode.INVALID_INPUT,
            message="Input was rejected.",
        ),
    }

    rendered = render_production_invocation_summaries(
        (failed, succeeded, pending),
        results=results,
        run_ids={
            succeeded.id: FIRST_RUN_ID,
        },
    )

    lines = rendered.splitlines()

    assert len(lines) == 3

    assert lines[0].startswith(f"{failed.id}  {CREATED_AT.isoformat()}  invalid_input")
    assert lines[0].endswith("  no run")

    assert lines[1].startswith(f"{succeeded.id}  {CREATED_AT.isoformat()}  succeeded")
    assert lines[1].endswith(f"  {FIRST_RUN_ID}")

    assert lines[2].startswith(f"{pending.id}  {CREATED_AT.isoformat()}  pending")
    assert lines[2].endswith("  no run")

    # Run columns align regardless of outcome label length.
    assert lines[0].index("no run") == lines[1].index(str(FIRST_RUN_ID))
    assert lines[0].index("no run") == lines[2].index("no run")


def test_summaries_of_no_invocations_render_empty() -> None:
    assert (
        render_production_invocation_summaries(
            (),
            results={},
            run_ids={},
        )
        == ""
    )


def test_successful_invocation_renders_input_result_and_run() -> None:
    invocation = create_invocation(
        {"text": "hello"},
        caller_metadata={"caller": "billing-service"},
    )

    rendered = render_production_invocation(
        invocation,
        result=ProductionInvocationSuccess(
            invocation_id=invocation.id,
            result={"answer": "OK"},
        ),
        run_id=FIRST_RUN_ID,
    )

    assert rendered == "\n".join(
        (
            f"Invocation ID: {invocation.id}",
            f"Workflow ID: {WORKFLOW_ID}",
            f"Created At: {CREATED_AT.isoformat()}",
            "Outcome: succeeded",
            f"Run ID: {FIRST_RUN_ID}",
            "Caller Metadata:",
            "{",
            '  "caller": "billing-service"',
            "}",
            "Input:",
            "{",
            '  "text": "hello"',
            "}",
            "Result:",
            "{",
            '  "answer": "OK"',
            "}",
        )
    )


def test_failed_invocation_renders_message_and_metadata() -> None:
    invocation = create_invocation({"text": "hello"})

    rendered = render_production_invocation(
        invocation,
        result=ProductionInvocationFailure(
            invocation_id=invocation.id,
            error_code=ProductionInvocationErrorCode.MODEL_UNAVAILABLE,
            message="Primary model is unavailable.",
            metadata={"model": "openai/gpt-test"},
        ),
        run_id=None,
    )

    assert rendered == "\n".join(
        (
            f"Invocation ID: {invocation.id}",
            f"Workflow ID: {WORKFLOW_ID}",
            f"Created At: {CREATED_AT.isoformat()}",
            "Outcome: model_unavailable",
            "Run ID: no run",
            "Input:",
            "{",
            '  "text": "hello"',
            "}",
            "Message: Primary model is unavailable.",
            "Metadata:",
            "{",
            '  "model": "openai/gpt-test"',
            "}",
        )
    )


def test_pending_invocation_renders_without_result() -> None:
    invocation = create_invocation({"text": "hello"})

    rendered = render_production_invocation(
        invocation,
        result=None,
        run_id=None,
    )

    assert "Outcome: pending" in rendered
    assert "Result:" not in rendered
    assert "Message:" not in rendered
    assert rendered.endswith('Input:\n{\n  "text": "hello"\n}')


def test_invocation_without_recorded_input_renders_null_input() -> None:
    invocation = ProductionInvocation(
        workflow_id=WORKFLOW_ID,
        initial_context=Context(),
        created_at=CREATED_AT,
    )

    rendered = render_production_invocation(
        invocation,
        result=None,
        run_id=None,
    )

    assert rendered.endswith("Input:\nnull")
