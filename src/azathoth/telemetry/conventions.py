"""Span names and attribute keys Azathoth exports (ADR 0100).

Model attributes follow OpenTelemetry's generative AI conventions, which are
still experimental upstream; every other key is Azathoth's own.
"""

from typing import Final

JOB_SPAN: Final = "azathoth.job"
INVOCATION_SPAN: Final = "azathoth.invocation"
RUN_SPAN: Final = "azathoth.run"
STEP_SPAN: Final = "azathoth.step"

ATTEMPT_FAILED_EVENT: Final = "azathoth.attempt.failed"
"""The span event recorded for each failed attempt of a step."""

JOB_KIND: Final = "azathoth.job.kind"
JOB_VERSION: Final = "azathoth.job.version"
JOB_STATUS: Final = "azathoth.job.status"
JOB_REPLAYED: Final = "azathoth.job.replayed"

INVOCATION_ID: Final = "azathoth.invocation.id"
INVOCATION_OUTCOME: Final = "azathoth.invocation.outcome"

ERROR_CODE: Final = "azathoth.error.code"
ERROR_TYPE: Final = "error.type"

WORKFLOW_ID: Final = "azathoth.workflow.id"
WORKFLOW_REVISION: Final = "azathoth.workflow.revision"

RUN_ID: Final = "azathoth.run.id"
RUN_STATUS: Final = "azathoth.run.status"
RUN_EXECUTED_STEPS: Final = "azathoth.run.steps.executed"
RUN_FAILED_STEPS: Final = "azathoth.run.steps.failed"
RUN_SKIPPED_STEPS: Final = "azathoth.run.steps.skipped"

STEP_ID: Final = "azathoth.step.id"
STEP_STATUS: Final = "azathoth.step.status"
STEP_ATTEMPTS: Final = "azathoth.step.attempts"
STEP_CONFIDENCE: Final = "azathoth.step.confidence"
STRATEGY_NAME: Final = "azathoth.strategy.name"
COST_USD: Final = "azathoth.cost.usd"

ATTEMPT_NUMBER: Final = "azathoth.attempt.number"

GEN_AI_PROVIDER: Final = "gen_ai.provider.name"
GEN_AI_REQUEST_MODEL: Final = "gen_ai.request.model"
GEN_AI_INPUT_TOKENS: Final = "gen_ai.usage.input_tokens"
GEN_AI_OUTPUT_TOKENS: Final = "gen_ai.usage.output_tokens"

ATTRIBUTE_KEYS: Final = frozenset(
    {
        JOB_KIND,
        JOB_VERSION,
        JOB_STATUS,
        JOB_REPLAYED,
        INVOCATION_ID,
        INVOCATION_OUTCOME,
        ERROR_CODE,
        ERROR_TYPE,
        WORKFLOW_ID,
        WORKFLOW_REVISION,
        RUN_ID,
        RUN_STATUS,
        RUN_EXECUTED_STEPS,
        RUN_FAILED_STEPS,
        RUN_SKIPPED_STEPS,
        STEP_ID,
        STEP_STATUS,
        STEP_ATTEMPTS,
        STEP_CONFIDENCE,
        STRATEGY_NAME,
        COST_USD,
        ATTEMPT_NUMBER,
        GEN_AI_PROVIDER,
        GEN_AI_REQUEST_MODEL,
        GEN_AI_INPUT_TOKENS,
        GEN_AI_OUTPUT_TOKENS,
    }
)
"""Every attribute key Azathoth may set. None of them carries content."""

SPAN_NAMES: Final = frozenset({JOB_SPAN, INVOCATION_SPAN, RUN_SPAN, STEP_SPAN})
"""Every span name Azathoth exports."""
