"""How the commands that execute workflows report what they executed.

`workflow run`, `workflow invoke`, `run resume`, `invocation resume` and a
keyed `workflow invoke` all report through these, so a resumed or replayed
run reads exactly like one that just ran.

Each ends, when what it printed holds restricted data, with the warning
that it does, on standard error (ADR 0123).
"""

import json
import sys
from uuid import UUID

from azathoth.cli.output_format import WorkflowOutputFormat
from azathoth.cli.rendering import (
    RESULT_RECORD_TYPE,
    OutputRecord,
    production_invocation_record,
    render_production_invocation_result,
    render_workflow_run,
    workflow_run_record,
)
from azathoth.cli.rendering.sensitivity import warn_if_restricted
from azathoth.cli.step_output import (
    JsonLinesOutputWriter,
    TextStepMessageWriter,
)
from azathoth.context import context_sensitivity
from azathoth.sensitivity import DEFAULT_SENSITIVITY, Sensitivity
from azathoth.workflows import (
    ProductionInvocationFailure,
    ProductionInvocationRepository,
    ProductionInvocationResult,
    WorkflowRun,
    WorkflowRunObserver,
    WorkflowSpecification,
)


def report_configured_run(
    run: WorkflowRun,
    *,
    specification: WorkflowSpecification | None,
    output: WorkflowOutputFormat,
    writer: JsonLinesOutputWriter | None,
    resumes: int = 0,
) -> int:
    """Print a finished configured run in its output format, returning the exit code.

    Text renders the run, naming how often it was resumed, and exits 0 when
    it succeeded. JSON Lines and result mode end with its result record, as
    the specification it executed declares it. A restricted run's report
    is followed by the warning that it holds restricted data (ADR 0123).
    """

    if output is not WorkflowOutputFormat.TEXT and specification is None:
        raise ValueError("A run reported as a record needs the specification it executed.")

    if output is WorkflowOutputFormat.TEXT:
        print(render_workflow_run(run, resumes=resumes))

        status = 0 if run.succeeded else 1
    else:
        assert specification is not None

        status = write_terminal_record(
            workflow_run_record(
                run,
                result=specification.result,
                steps=specification.steps,
            ),
            writer,
        )

    warn_if_restricted(context_sensitivity(run.initial_context), f"Run {run.id}")

    return status


def report_invocation_result(
    result: ProductionInvocationResult,
    *,
    output: WorkflowOutputFormat,
    writer: JsonLinesOutputWriter | None,
    sensitivity: Sensitivity = DEFAULT_SENSITIVITY,
) -> int:
    """Print an invocation's terminal result in its output format, returning the exit code.

    Text prints a success on stdout and a failure on stderr; JSON Lines and
    result mode end with its record. A failure exits 1. An invocation
    labelled restricted is followed by the warning that its output holds
    restricted data (ADR 0123).
    """

    if output is WorkflowOutputFormat.TEXT:
        rendered = render_production_invocation_result(
            result,
        )
        failed = isinstance(result, ProductionInvocationFailure)

        print(rendered, file=sys.stderr if failed else sys.stdout)

        status = 1 if failed else 0
    else:
        status = write_terminal_record(
            production_invocation_record(result),
            writer,
        )

    warn_if_restricted(sensitivity, f"Invocation {result.invocation_id}")

    return status


def invocation_sensitivity(
    repository: ProductionInvocationRepository,
    invocation_id: UUID,
) -> Sensitivity:
    """Return the label of a recorded invocation, internal when it is not recorded (ADR 0123)."""

    invocation = repository.get(invocation_id)

    if invocation is None:
        return DEFAULT_SENSITIVITY

    return context_sensitivity(invocation.initial_context)


def step_observer(
    output: WorkflowOutputFormat,
    writer: JsonLinesOutputWriter | None,
) -> WorkflowRunObserver | None:
    """Return the live step observer of one output format.

    JSON Lines streams step records to stdout through the given writer, text
    prints step messages to stderr, and result mode stays silent.
    """

    if output is WorkflowOutputFormat.JSONL:
        return writer

    if output is WorkflowOutputFormat.TEXT:
        return TextStepMessageWriter(sys.stderr)

    return None


def write_terminal_record(
    record: OutputRecord,
    writer: JsonLinesOutputWriter | None,
) -> int:
    """Write one terminal record in JSON Lines or result mode, returning the exit code.

    With a writer the record ends the JSON Lines stream. Without one, a result
    record prints only its value as JSON on stdout, and nothing when there is
    no declared result; an error record prints its message on stderr.
    """

    succeeded = record["type"] == RESULT_RECORD_TYPE

    if writer is not None:
        writer.write(record)

    elif not succeeded:
        print(
            record["message"],
            file=sys.stderr,
        )

    elif "value" in record:
        print(
            json.dumps(
                record["value"],
                ensure_ascii=False,
            )
        )

    return 0 if succeeded else 1


__all__ = [
    "invocation_sensitivity",
    "report_configured_run",
    "report_invocation_result",
    "step_observer",
    "write_terminal_record",
]
