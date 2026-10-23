"""Evaluation of workflow runs that failed before producing a judgeable result."""

from azathoth.evaluation import (
    EvaluationEvidence,
    EvaluationResult,
    EvaluationStatus,
    ExpectedOutcome,
)
from azathoth.workflows.execution import (
    WorkflowRun,
    WorkflowStepStatus,
)

RUN_FAILURE_EVALUATOR_NAME = "workflow-run-failure"

RUN_FAILURE_EVALUATOR_VERSION = "1.0.0"


def evaluate_failed_run(
    run: WorkflowRun,
    expected: ExpectedOutcome,
) -> EvaluationResult:
    """Return the failing evaluation recorded for one failed workflow run.

    The run is blamed on its first failed step in recorded order, using the
    failure of that step's final attempt. The evaluation scores 0.0 against a
    threshold of 1.0, so it always fails, and it is persisted and rendered
    like any other evaluator judgment.

    Raises:
        ValueError: The run contains no failed step.
    """

    failed_step = next(
        (step for step in run.steps if step.status is WorkflowStepStatus.FAILED),
        None,
    )

    if failed_step is None:
        raise ValueError(f"Workflow run {run.id} did not fail.")

    #
    # A failed step always ends with a failed attempt, so the final
    # attempt always carries a failure.
    #
    failure = failed_step.attempts[-1].failure

    if failure is None:
        raise ValueError(f"Workflow run {run.id} recorded a failed step without a failure.")

    return EvaluationResult(
        evaluator_name=RUN_FAILURE_EVALUATOR_NAME,
        evaluator_version=RUN_FAILURE_EVALUATOR_VERSION,
        score=0.0,
        threshold=1.0,
        status=EvaluationStatus.FAILED,
        reason=f"Workflow run failed at step {failed_step.step_id}: {failure.message}",
        evidence=(
            EvaluationEvidence(
                label="expected",
                value=expected.value,
            ),
            EvaluationEvidence(
                label="failed_step_id",
                value=str(failed_step.step_id),
            ),
            EvaluationEvidence(
                label="failure",
                value={
                    "exception_type": failure.exception_type,
                    "message": failure.message,
                },
            ),
        ),
    )
