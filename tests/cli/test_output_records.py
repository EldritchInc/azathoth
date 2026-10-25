"""Tests for machine-readable workflow output records."""

import asyncio
import dataclasses
from uuid import UUID

from azathoth.cli.rendering import (
    ERROR_RECORD_TYPE,
    OUTPUT_RECORD_TYPE,
    RESULT_NOT_PRODUCED_CODE,
    RESULT_RECORD_TYPE,
    STEP_RECORD_TYPE,
    WORKFLOW_EXECUTION_FAILED_CODE,
    production_invocation_record,
    render_output_record,
    step_finished_record,
    step_started_record,
    workflow_run_record,
)
from azathoth.context import Context
from azathoth.workflows import (
    ProductionInvocationErrorCode,
    ProductionInvocationFailure,
    ProductionInvocationSuccess,
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowFailurePolicy,
    WorkflowNamedValueReference,
    WorkflowRun,
    WorkflowRunner,
    WorkflowStepFinished,
    WorkflowStepStarted,
    WorkflowStepStatus,
    WorkflowValue,
)
from tests.workflows.test_run_observation import (
    FIRST_STEP_ID,
    FIRST_STRATEGY_ID,
    CountingExecutor,
    create_candidate,
    create_step,
)

INVOCATION_ID = UUID("d4000000-0000-4000-8000-000000000001")

MESSAGE = "Counting words"

COUNT_RESULT = WorkflowNamedValueReference(
    name="count",
)


def announced_step(
    *,
    emit_values: bool = True,
) -> WorkflowCandidateStep:
    """Return the counter step with a message and, optionally, value emission."""

    return dataclasses.replace(
        create_step(
            step_id=FIRST_STEP_ID,
            strategy_id=FIRST_STRATEGY_ID,
            name="Counter",
        ),
        message=MESSAGE,
        emit_values=emit_values,
    )


def silent_step() -> WorkflowCandidateStep:
    """Return the counter step without a message."""

    return create_step(
        step_id=FIRST_STEP_ID,
        strategy_id=FIRST_STRATEGY_ID,
        name="Counter",
    )


def finished(
    step: WorkflowCandidateStep,
    status: WorkflowStepStatus,
) -> WorkflowStepFinished:
    """Return a finished event for the step, carrying `count = 7` when executed."""

    values = (
        (
            WorkflowValue(
                name="count",
                value=7,
                producer_step_id=step.id,
            ),
        )
        if status is WorkflowStepStatus.EXECUTED
        else ()
    )

    return WorkflowStepFinished(
        step=step,
        layer_index=0,
        status=status,
        values=values,
    )


def run_candidate(
    candidate: WorkflowCandidate,
    *,
    executor: CountingExecutor,
) -> WorkflowRun:
    """Run one candidate, returning its recorded run even when it failed."""

    return asyncio.run(
        WorkflowRunner(
            executor=executor,
        ).run_recording_failures(
            candidate,
            Context(),
        )
    )


def test_record_types_are_stable() -> None:
    assert (
        STEP_RECORD_TYPE,
        OUTPUT_RECORD_TYPE,
        RESULT_RECORD_TYPE,
        ERROR_RECORD_TYPE,
    ) == (
        "step",
        "output",
        "result",
        "error",
    )


def test_starting_step_with_a_message_produces_a_step_record() -> None:
    step = announced_step()

    assert step_started_record(
        WorkflowStepStarted(
            step=step,
            layer_index=0,
        )
    ) == {
        "type": "step",
        "step_id": str(FIRST_STEP_ID),
        "message": MESSAGE,
    }


def test_starting_silent_step_produces_no_record() -> None:
    assert (
        step_started_record(
            WorkflowStepStarted(
                step=silent_step(),
                layer_index=0,
            )
        )
        is None
    )


def test_executed_step_emitting_values_produces_an_output_record() -> None:
    assert step_finished_record(
        finished(
            announced_step(),
            WorkflowStepStatus.EXECUTED,
        )
    ) == {
        "type": "output",
        "step_id": str(FIRST_STEP_ID),
        "values": {
            "count": 7,
        },
    }


def test_executed_step_not_emitting_values_produces_no_record() -> None:
    assert (
        step_finished_record(
            finished(
                announced_step(
                    emit_values=False,
                ),
                WorkflowStepStatus.EXECUTED,
            )
        )
        is None
    )


def test_failed_and_skipped_steps_produce_no_record() -> None:
    for status in (
        WorkflowStepStatus.FAILED,
        WorkflowStepStatus.SKIPPED,
    ):
        assert (
            step_finished_record(
                finished(
                    announced_step(),
                    status,
                )
            )
            is None
        )


def test_successful_invocation_produces_a_result_record() -> None:
    assert production_invocation_record(
        ProductionInvocationSuccess(
            invocation_id=INVOCATION_ID,
            result={
                "count": 4,
            },
        )
    ) == {
        "type": "result",
        "invocation_id": str(INVOCATION_ID),
        "value": {
            "count": 4,
        },
    }


def test_failed_invocation_produces_an_error_record() -> None:
    assert production_invocation_record(
        ProductionInvocationFailure(
            invocation_id=INVOCATION_ID,
            error_code=ProductionInvocationErrorCode.WORKFLOW_EXECUTION_FAILED,
            message="Production workflow execution failed.",
        )
    ) == {
        "type": "error",
        "invocation_id": str(INVOCATION_ID),
        "code": "workflow_execution_failed",
        "message": "Production workflow execution failed.",
    }


def test_failed_invocation_record_carries_metadata_when_present() -> None:
    record = production_invocation_record(
        ProductionInvocationFailure(
            invocation_id=INVOCATION_ID,
            error_code=ProductionInvocationErrorCode.INVALID_INPUT,
            message="Invalid input.",
            metadata={
                "field": "input",
            },
        )
    )

    assert record["metadata"] == {
        "field": "input",
    }


def test_successful_run_with_declared_result_produces_its_value() -> None:
    candidate = create_candidate(silent_step())

    run = run_candidate(
        candidate,
        executor=CountingExecutor(),
    )

    assert workflow_run_record(
        run,
        result=COUNT_RESULT,
        steps=candidate.steps,
    ) == {
        "type": "result",
        "run_id": str(run.id),
        "value": 7,
    }


def test_successful_run_without_declared_result_omits_value() -> None:
    candidate = create_candidate(silent_step())

    run = run_candidate(
        candidate,
        executor=CountingExecutor(),
    )

    assert workflow_run_record(
        run,
        result=None,
        steps=candidate.steps,
    ) == {
        "type": "result",
        "run_id": str(run.id),
    }


def test_halted_run_reports_the_step_that_halted_it() -> None:
    candidate = create_candidate(
        create_step(
            step_id=FIRST_STEP_ID,
            strategy_id=FIRST_STRATEGY_ID,
            name="Counter",
            failure_policy=WorkflowFailurePolicy.FAIL_WORKFLOW,
        )
    )

    run = run_candidate(
        candidate,
        executor=CountingExecutor(
            failing=frozenset({"Counter"}),
        ),
    )

    assert workflow_run_record(
        run,
        result=COUNT_RESULT,
        steps=candidate.steps,
    ) == {
        "type": "error",
        "run_id": str(run.id),
        "code": WORKFLOW_EXECUTION_FAILED_CODE,
        "step_id": str(FIRST_STEP_ID),
        "exception_type": "RuntimeError",
        "message": "Counter failed",
    }


def test_completed_run_with_a_tolerated_failure_reports_its_missing_result() -> None:
    candidate = create_candidate(silent_step())

    run = run_candidate(
        candidate,
        executor=CountingExecutor(
            failing=frozenset({"Counter"}),
        ),
    )

    assert run.succeeded
    assert workflow_run_record(
        run,
        result=COUNT_RESULT,
        steps=candidate.steps,
    ) == {
        "type": "error",
        "run_id": str(run.id),
        "code": RESULT_NOT_PRODUCED_CODE,
        "message": "Workflow result 'count' was not produced by any workflow step.",
    }


def test_run_without_its_declared_result_produces_an_error_record() -> None:
    candidate = create_candidate(silent_step())

    run = run_candidate(
        candidate,
        executor=CountingExecutor(),
    )

    assert workflow_run_record(
        run,
        result=WorkflowNamedValueReference(
            name="total",
        ),
        steps=candidate.steps,
    ) == {
        "type": "error",
        "run_id": str(run.id),
        "code": RESULT_NOT_PRODUCED_CODE,
        "message": "Workflow result 'total' was not produced by any workflow step.",
    }


def test_record_renders_as_one_line_of_json() -> None:
    assert render_output_record(
        {
            "type": "step",
            "step_id": str(FIRST_STEP_ID),
            "message": "Zählen der Wörter",
        }
    ) == (f'{{"type": "step", "step_id": "{FIRST_STEP_ID}", "message": "Zählen der Wörter"}}')
