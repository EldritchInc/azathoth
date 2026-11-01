"""Span attributes for Azathoth's own records (ADR 0100).

Every builder returns identifiers, statuses and measurements only. Nothing a
workflow received, produced or said is ever an attribute.
"""

from uuid import UUID

from azathoth.jobs import JobResult
from azathoth.strategies import StrategyExecutionMetrics
from azathoth.telemetry.api import AttributeValue
from azathoth.telemetry.conventions import (
    COST_USD,
    ERROR_CODE,
    GEN_AI_INPUT_TOKENS,
    GEN_AI_OUTPUT_TOKENS,
    GEN_AI_PROVIDER,
    GEN_AI_REQUEST_MODEL,
    INVOCATION_ID,
    INVOCATION_OUTCOME,
    JOB_KIND,
    JOB_REPLAYED,
    JOB_STATUS,
    JOB_VERSION,
    RUN_EXECUTED_STEPS,
    RUN_FAILED_STEPS,
    RUN_ID,
    RUN_SKIPPED_STEPS,
    RUN_STATUS,
    STEP_ATTEMPTS,
    STEP_CONFIDENCE,
    STEP_ID,
    STEP_STATUS,
    STRATEGY_NAME,
    WORKFLOW_ID,
    WORKFLOW_REVISION,
)
from azathoth.workflows import (
    ProductionInvocationFailure,
    ProductionInvocationResult,
    WorkflowRun,
    WorkflowStepStatus,
)

SUCCEEDED_OUTCOME = "succeeded"
FAILED_STATUS = "failed"


def model_attributes(
    metrics: StrategyExecutionMetrics | None,
) -> dict[str, AttributeValue]:
    """Return the model attributes of one execution's metrics, as far as they are known."""

    if metrics is None:
        return {}

    candidates: dict[str, AttributeValue | None] = {
        GEN_AI_PROVIDER: metrics.provider,
        GEN_AI_REQUEST_MODEL: metrics.model,
        GEN_AI_INPUT_TOKENS: metrics.prompt_tokens,
        GEN_AI_OUTPUT_TOKENS: metrics.completion_tokens,
        COST_USD: metrics.estimated_cost_usd,
    }

    return {key: value for key, value in candidates.items() if value is not None}


def step_attributes(
    step_id: UUID,
    status: WorkflowStepStatus,
    *,
    attempts: int,
    strategy_name: str | None = None,
    confidence: float | None = None,
    metrics: StrategyExecutionMetrics | None = None,
) -> dict[str, AttributeValue]:
    """Return the attributes of one finished step."""

    attributes: dict[str, AttributeValue] = {
        STEP_ID: str(step_id),
        STEP_STATUS: status.value,
        STEP_ATTEMPTS: attempts,
    }

    if strategy_name is not None:
        attributes[STRATEGY_NAME] = strategy_name

    if confidence is not None:
        attributes[STEP_CONFIDENCE] = confidence

    attributes.update(model_attributes(metrics))

    return attributes


def run_attributes(
    run: WorkflowRun,
) -> dict[str, AttributeValue]:
    """Return the attributes of one completed run."""

    statistics = run.statistics

    attributes: dict[str, AttributeValue] = {
        RUN_ID: str(run.id),
        WORKFLOW_ID: str(run.workflow.id),
        RUN_STATUS: SUCCEEDED_OUTCOME if run.succeeded else FAILED_STATUS,
        RUN_EXECUTED_STEPS: statistics.executed_steps,
        RUN_FAILED_STEPS: statistics.failed_steps,
        RUN_SKIPPED_STEPS: statistics.skipped_steps,
    }

    if run.workflow_revision is not None:
        attributes[WORKFLOW_REVISION] = run.workflow_revision

    return attributes


def invocation_attributes(
    result: ProductionInvocationResult,
    *,
    workflow_id: UUID,
) -> dict[str, AttributeValue]:
    """Return the attributes of one production invocation's terminal result."""

    attributes: dict[str, AttributeValue] = {
        INVOCATION_ID: str(result.invocation_id),
        WORKFLOW_ID: str(workflow_id),
    }

    if isinstance(result, ProductionInvocationFailure):
        attributes[INVOCATION_OUTCOME] = result.error_code.value
        attributes[ERROR_CODE] = result.error_code.value
    else:
        attributes[INVOCATION_OUTCOME] = SUCCEEDED_OUTCOME

    return attributes


def job_attributes(
    result: JobResult,
) -> dict[str, AttributeValue]:
    """Return the attributes of one job result. The idempotency key is never one."""

    attributes: dict[str, AttributeValue] = {
        JOB_KIND: result.kind,
        JOB_VERSION: result.version,
        JOB_STATUS: result.status.value,
        JOB_REPLAYED: result.replayed,
    }

    if result.invocation_id is not None:
        attributes[INVOCATION_ID] = str(result.invocation_id)

    if result.error is not None:
        attributes[ERROR_CODE] = result.error.code.value

    return attributes


__all__ = [
    "FAILED_STATUS",
    "SUCCEEDED_OUTCOME",
    "invocation_attributes",
    "job_attributes",
    "model_attributes",
    "run_attributes",
    "step_attributes",
]
