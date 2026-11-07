"""Benchmark cases built from recorded workflow runs and from input files (ADR 0112, ADR 0117)."""

from collections.abc import Iterable

from pydantic import JsonValue, ValidationError

from azathoth.evaluation import (
    BenchmarkCase,
    CitationExpectation,
    ExpectedOutcome,
    OutcomeComparison,
    json_schema_validator,
)
from azathoth.inputs import InputProvenance, ResolvedInput
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
SOURCE_URI_METADATA_KEY = "source_uri"


class BenchmarkCaseSourceError(ValueError):
    """Raised when a recorded run cannot become a benchmark case."""


def workflow_run_input(
    run: WorkflowRun,
) -> JsonValue:
    """Return the external input one recorded run received.

    The input is the payload of the run's single canonical workflow input
    event. A received JSON null is input like any other value, and so is a
    content handle, which a case holds with its provenance (ADR 0117).

    Raises:
        BenchmarkCaseSourceError: The run received no workflow input, or
            received it more than once.
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

    return events[0].payload["input"]


def workflow_run_input_provenance(
    run: WorkflowRun,
) -> InputProvenance | None:
    """Return the provenance one recorded run's input was resolved with, or None.

    The provenance is the payload of the run's `workflow.input.resolved`
    event: where the input was read from, and which content it was (ADR
    0112). An input given inline as JSON or text records none.
    """

    return next(
        (
            InputProvenance.model_validate(event.payload)
            for event in run.initial_context.events
            if event.event_type == WORKFLOW_INPUT_RESOLVED_EVENT_TYPE
        ),
        None,
    )


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
    citations: CitationExpectation | None = None,
) -> BenchmarkCase:
    """Return a new benchmark case replaying one recorded run's input.

    The case holds the run's input with the provenance it was resolved
    with, so a document the run was given is given to the case's run as it
    was (ADR 0117). The case expects the given value under the given
    comparison, and the run's citations, when given, to meet them. A blank or
    absent description becomes one naming the source run. The case metadata
    records the source run, and the feedback whose corrected output supplied
    the expected value when there is one.

    Raises:
        BenchmarkCaseSourceError: The run did not receive workflow input
            exactly once, the feedback judges a different run, the expected
            value is not a valid JSON Schema for a schema comparison, or the
            run's provenance names content its input is not the handle of.
    """

    if feedback is not None and feedback.run_id != run.id:
        raise BenchmarkCaseSourceError(f"Feedback {feedback.id} does not judge run {run.id}.")

    case_input = workflow_run_input(run)

    metadata: dict[str, JsonValue] = {
        SOURCE_RUN_METADATA_KEY: str(run.id),
    }

    if feedback is not None:
        metadata[SOURCE_FEEDBACK_METADATA_KEY] = str(feedback.id)

    return _case(
        input=case_input,
        input_provenance=workflow_run_input_provenance(run),
        expected=_expected_outcome(
            comparison=comparison,
            expected=expected,
            description=description,
            default_description=f"Added from run {run.id}.",
            citations=citations,
        ),
        metadata=metadata,
    )


def benchmark_case_from_input(
    resolved: ResolvedInput,
    *,
    comparison: OutcomeComparison,
    expected: JsonValue,
    description: str | None = None,
    citations: CitationExpectation | None = None,
) -> BenchmarkCase:
    """Return a new benchmark case of one resolved input, such as a file's (ADR 0117).

    The case holds the resolved value and its provenance, and expects the
    given value under the given comparison. A blank or absent description
    becomes one naming where the input was read from, and the case metadata
    records it.

    Raises:
        BenchmarkCaseSourceError: The expected value is not a valid JSON
            Schema for a schema comparison.
    """

    provenance = resolved.provenance
    source = (
        provenance.uri
        if provenance is not None and provenance.uri is not None
        else "an inline input"
    )
    metadata: dict[str, JsonValue] = (
        {SOURCE_URI_METADATA_KEY: provenance.uri}
        if provenance is not None and provenance.uri is not None
        else {}
    )

    return _case(
        input=resolved.value,
        input_provenance=provenance,
        expected=_expected_outcome(
            comparison=comparison,
            expected=expected,
            description=description,
            default_description=f"Added from {source}.",
            citations=citations,
        ),
        metadata=metadata,
    )


def _case(
    **fields: object,
) -> BenchmarkCase:
    """Return one new case, refusing one the case model refuses.

    Raises:
        BenchmarkCaseSourceError: The case's provenance names content its
            input is not the handle of.
    """

    try:
        return BenchmarkCase.model_validate(fields)
    except ValidationError as exc:
        raise BenchmarkCaseSourceError(
            str(exc.errors()[0]["msg"]).removeprefix("Value error, ")
        ) from exc


def _expected_outcome(
    *,
    comparison: OutcomeComparison,
    expected: JsonValue,
    description: str | None,
    default_description: str,
    citations: CitationExpectation | None,
) -> ExpectedOutcome:
    """Return the outcome a new case expects, describing it by default.

    Raises:
        BenchmarkCaseSourceError: The expected value is not a valid JSON
            Schema for a schema comparison.
    """

    if comparison is OutcomeComparison.SCHEMA:
        try:
            json_schema_validator(expected)
        except ValueError as exc:
            raise BenchmarkCaseSourceError(
                f"Expected value cannot be used with comparison 'schema': {exc}"
            ) from exc

    normalized_description = description.strip() if description is not None else ""

    return ExpectedOutcome(
        description=normalized_description or default_description,
        value=expected,
        comparison=comparison,
        citations=citations,
    )


__all__ = [
    "SOURCE_FEEDBACK_METADATA_KEY",
    "SOURCE_RUN_METADATA_KEY",
    "SOURCE_URI_METADATA_KEY",
    "BenchmarkCaseSourceError",
    "benchmark_case_from_input",
    "benchmark_case_from_run",
    "latest_corrected_output",
    "workflow_run_input",
    "workflow_run_input_provenance",
]
