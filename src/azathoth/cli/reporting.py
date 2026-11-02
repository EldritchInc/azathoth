"""How the commands that execute workflows report what they executed.

`workflow run`, `workflow invoke`, `run resume`, `invocation resume` and a
keyed `workflow invoke` all report through these, so a resumed or replayed
run reads exactly like one that just ran.
"""

import json
import sys

from azathoth.cli.output_format import WorkflowOutputFormat
from azathoth.cli.rendering import (
    RESULT_RECORD_TYPE,
    OutputRecord,
    production_invocation_record,
    render_production_invocation_result,
    render_workflow_run,
    workflow_run_record,
)
from azathoth.cli.step_output import (
    JsonLinesOutputWriter,
    TextStepMessageWriter,
)
from azathoth.workflows import (
    ProductionInvocationFailure,
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
    the specification it executed declares it.
    """

    if output is WorkflowOutputFormat.TEXT:
        print(render_workflow_run(run, resumes=resumes))

        return 0 if run.succeeded else 1

    if specification is None:
        raise ValueError("A run reported as a record needs the specification it executed.")

    record = workflow_run_record(
        run,
        result=specification.result,
        steps=specification.steps,
    )

    return write_terminal_record(
        record,
        writer,
    )


def report_invocation_result(
    result: ProductionInvocationResult,
    *,
    output: WorkflowOutputFormat,
    writer: JsonLinesOutputWriter | None,
) -> int:
    """Print an invocation's terminal result in its output format, returning the exit code.

    Text prints a success on stdout and a failure on stderr; JSON Lines and
    result mode end with its record. A failure exits 1.
    """

    if output is WorkflowOutputFormat.TEXT:
        rendered = render_production_invocation_result(
            result,
        )

        if isinstance(
            result,
            ProductionInvocationFailure,
        ):
            print(
                rendered,
                file=sys.stderr,
            )

            return 1

        print(rendered)

        return 0

    return write_terminal_record(
        production_invocation_record(result),
        writer,
    )


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
    "report_configured_run",
    "report_invocation_result",
    "step_observer",
    "write_terminal_record",
]
