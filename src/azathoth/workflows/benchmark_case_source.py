"""Benchmark cases built from the evidence of recorded workflow runs (ADR 0112)."""

from collections.abc import Iterable

from pydantic import JsonValue

from azathoth.evaluation import (
    BenchmarkCase,
    ExpectedOutcome,
    OutcomeComparison,
    json_schema_validator,
)
from azathoth.inputs import is_binary_media_type
from azathoth.workflows.execution import WorkflowRun
from azathoth.workflows.feedback import (
    WorkflowRunFeedback,
    WorkflowRunFeedbackDisposition,
)
from azathoth.workflows.input import (
    WORKFLOW_INPUT_EVENT_TYPE,
    WORKFLOW_INPUT_RESOLVED_EVENT_TYPE,
)

SOURCE_RUN_METADATA_KEY = "source_run_id"
SOURCE_FEEDBACK_METADATA_KEY = "source_feedback_id"


class BenchmarkCaseSourceError(ValueError):
    """Raised when a recorded run cannot become a benchmark case."""


def workflow_run_input(
    run: WorkflowRun,
) -> JsonValue:
    """Return the external input one recorded run received.

    The input is the payload of the run's single canonical workflow input
    event. A received JSON null is input like any other value.

    A run given binary content is refused, as its recorded provenance says:
    its input is a content handle, and a benchmark case cannot carry the
    content it names yet (ADR 0112).

    Raises:
        BenchmarkCaseSourceError: The run received no workflow input,
            received it more than once, or received binary content.
    """

    events = tuple(
        event
        for event in run.initial_context.events
        if event.event_type == WORKFLOW_INPUT_EVENT_TYPE and "input" in event.payload
    )

    if not events:
        raise BenchmarkCaseSourceError(f"Run {run.id} did not receive workflow input.")

    if len(events) > 1:
        raise BenchmarkCaseSourceError(f"Run {run.id} received workflow input more than once.")

    for event in run.initial_context.events:
        media_type = event.payload.get("media_type")

        if (
            event.event_type == WORKFLOW_INPUT_RESOLVED_EVENT_TYPE
            and isinstance(media_type, str)
            and is_binary_media_type(media_type)
        ):
            raise BenchmarkCaseSourceError(
                f"Run {run.id} received {media_type} content, which a benchmark case "
                "cannot hold yet."
            )

    return events[0].payload["input"]


def latest_corrected_output(
    feedback: Iterable[WorkflowRunFeedback],
) -> WorkflowRunFeedback | None:
    """Return the most recent bad feedback that carries a corrected output.

    Feedback is read in insertion order, so a later record wins a timestamp
    tie, the same rule that decides a run's latest disposition. Good feedback
    never supplies a value, and neither does bad feedback without a
    correction, so neither hides an earlier correction.
    """

    latest: WorkflowRunFeedback | None = None

    for record in feedback:
        if (
            record.disposition is not WorkflowRunFeedbackDisposition.BAD
            or record.corrected_output is None
        ):
            continue

        if latest is None or record.created_at >= latest.created_at:
            latest = record

    return latest


def benchmark_case_from_run(
    run: WorkflowRun,
    *,
    comparison: OutcomeComparison,
    expected: JsonValue,
    description: str | None = None,
    feedback: WorkflowRunFeedback | None = None,
) -> BenchmarkCase:
    """Return a new benchmark case replaying one recorded run's input.

    The case expects the given value under the given comparison. A blank or
    absent description becomes one naming the source run. The case metadata
    records the source run, and the feedback whose corrected output supplied
    the expected value when there is one.

    Raises:
        BenchmarkCaseSourceError: The run did not receive workflow input
            exactly once, the feedback judges a different run, or the
            expected value is not a valid JSON Schema for a schema comparison.
    """

    if feedback is not None and feedback.run_id != run.id:
        raise BenchmarkCaseSourceError(f"Feedback {feedback.id} does not judge run {run.id}.")

    case_input = workflow_run_input(run)

    if comparison is OutcomeComparison.SCHEMA:
        try:
            json_schema_validator(expected)
        except ValueError as exc:
            raise BenchmarkCaseSourceError(
                f"Expected value cannot be used with comparison 'schema': {exc}"
            ) from exc

    normalized_description = description.strip() if description is not None else ""

    metadata: dict[str, JsonValue] = {
        SOURCE_RUN_METADATA_KEY: str(run.id),
    }

    if feedback is not None:
        metadata[SOURCE_FEEDBACK_METADATA_KEY] = str(feedback.id)

    return BenchmarkCase(
        input=case_input,
        expected=ExpectedOutcome(
            description=normalized_description or f"Added from run {run.id}.",
            value=expected,
            comparison=comparison,
        ),
        metadata=metadata,
    )


__all__ = [
    "SOURCE_FEEDBACK_METADATA_KEY",
    "SOURCE_RUN_METADATA_KEY",
    "BenchmarkCaseSourceError",
    "benchmark_case_from_run",
    "latest_corrected_output",
    "workflow_run_input",
]
