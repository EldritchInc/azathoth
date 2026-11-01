"""Machine-readable output records for workflow execution commands.

Each record is one JSON object with a `type`. A stream of records reports
step messages as steps start, emitted step values as they succeed, and ends
with exactly one terminal `result` or `error` record. A client may show the
progress records or read only the terminal record.
"""

import json
from collections.abc import Sequence

from pydantic import JsonValue

from azathoth.workflows import (
    ProductionInvocationFailure,
    ProductionInvocationResult,
    ProductionInvocationSuccess,
    WorkflowOutputDeclaringStep,
    WorkflowResultError,
    WorkflowResultReference,
    WorkflowRun,
    WorkflowStepFinished,
    WorkflowStepStarted,
    WorkflowStepStatus,
    workflow_result,
)

OutputRecord = dict[str, JsonValue]
"""One JSON object of a workflow command's output stream."""

STEP_RECORD_TYPE = "step"
OUTPUT_RECORD_TYPE = "output"
RESULT_RECORD_TYPE = "result"
ERROR_RECORD_TYPE = "error"

WORKFLOW_EXECUTION_FAILED_CODE = "workflow_execution_failed"
"""The error code of a configured run in which a step failed."""

RESULT_NOT_PRODUCED_CODE = "result_not_produced"
"""The error code of a configured run that did not produce its declared result."""


def step_started_record(
    event: WorkflowStepStarted,
) -> OutputRecord | None:
    """Return the message record of a starting step, or None for a silent step."""

    message = event.step.message

    if message is None:
        return None

    return {
        "type": STEP_RECORD_TYPE,
        "step_id": str(event.step.id),
        "message": message,
    }


def step_finished_record(
    event: WorkflowStepFinished,
) -> OutputRecord | None:
    """Return the values record of a finished step, or None when it emits nothing.

    Only an executed step that declares value emission emits its values.
    Failed and skipped steps emit nothing. A step that declares a confidence
    carries it beside its values (ADR 0098).
    """

    if event.status is not WorkflowStepStatus.EXECUTED:
        return None

    if not event.step.emit_values:
        return None

    record: OutputRecord = {
        "type": OUTPUT_RECORD_TYPE,
        "step_id": str(event.step.id),
        "values": {value.name: value.value for value in event.values},
    }

    if event.confidence is not None:
        record["confidence"] = event.confidence

    return record


def production_invocation_record(
    result: ProductionInvocationResult,
) -> OutputRecord:
    """Return the terminal record of one production invocation.

    Failures carry the caller-visible production error code and message, and
    never the internal failure of a step.
    """

    if isinstance(
        result,
        ProductionInvocationSuccess,
    ):
        return {
            "type": RESULT_RECORD_TYPE,
            "invocation_id": str(result.invocation_id),
            "value": result.result,
        }

    assert isinstance(
        result,
        ProductionInvocationFailure,
    )

    record: OutputRecord = {
        "type": ERROR_RECORD_TYPE,
        "invocation_id": str(result.invocation_id),
        "code": result.error_code.value,
        "message": result.message,
    }

    if result.metadata:
        record["metadata"] = dict(result.metadata)

    return record


def workflow_run_record(
    run: WorkflowRun,
    *,
    result: WorkflowResultReference | None,
    steps: Sequence[WorkflowOutputDeclaringStep],
) -> OutputRecord:
    """Return the terminal record of one configured workflow run.

    A run that halted reports the step that halted it with its actual
    failure, because configured runs are the workflow author's tool. A run
    that completed despite tolerated step failures reports its result. A
    successful run without a declared result omits `value`, so it cannot be
    mistaken for a result of null.
    """

    if run.failed:
        failed_step = next(
            step
            for step in run.steps
            if step.status is WorkflowStepStatus.FAILED
            and (run.halting_step_id is None or step.step_id == run.halting_step_id)
        )

        failure = failed_step.attempts[-1].failure

        assert failure is not None

        return {
            "type": ERROR_RECORD_TYPE,
            "run_id": str(run.id),
            "code": WORKFLOW_EXECUTION_FAILED_CODE,
            "step_id": str(failed_step.step_id),
            "exception_type": failure.exception_type,
            "message": failure.message,
        }

    if result is None:
        return {
            "type": RESULT_RECORD_TYPE,
            "run_id": str(run.id),
        }

    try:
        value = workflow_result(
            run,
            result,
            steps=steps,
        )
    except WorkflowResultError as error:
        return {
            "type": ERROR_RECORD_TYPE,
            "run_id": str(run.id),
            "code": RESULT_NOT_PRODUCED_CODE,
            "message": str(error),
        }

    return {
        "type": RESULT_RECORD_TYPE,
        "run_id": str(run.id),
        "value": value,
    }


def render_output_record(
    record: OutputRecord,
) -> str:
    """Render one output record as a single line of JSON."""

    return json.dumps(
        record,
        ensure_ascii=False,
    )
