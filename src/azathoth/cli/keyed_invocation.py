"""`workflow invoke --idempotency-key`: an invocation recorded under a key (ADR 0097, ADR 0105).

The invocation is run exactly as `job run` runs a request with that key: the
same request again replays its recorded result, or resumes it if it was
interrupted and nothing runs it any more; one still running, or a different
request under the same key, is refused. What it reports is what
`workflow invoke` reports, in the same output formats.

The standard composition tools give every child they start a key of their
step's attempt, so a parent that is resumed reuses, rather than repeats, the
children it already ran.
"""

import asyncio
import sys
from uuid import UUID

from pydantic import JsonValue

from azathoth.cli.bootstrap import load_runtime
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.inputs import CLI_INPUT_POLICY, WorkflowInputFile, input_file_source
from azathoth.cli.output_format import WorkflowOutputFormat
from azathoth.cli.persistence import repositories
from azathoth.cli.rendering import ERROR_RECORD_TYPE, OutputRecord
from azathoth.cli.reporting import (
    invocation_sensitivity,
    report_invocation_result,
    step_observer,
    write_terminal_record,
)
from azathoth.cli.step_output import JsonLinesOutputWriter
from azathoth.context import WorkflowLineage
from azathoth.inputs import InlineInput, InputSourceError
from azathoth.jobs import (
    InvokeJobRequest,
    JobResult,
    JobStatus,
    run_invoke_job,
    runtime_job_invoker,
    runtime_job_resumer,
)
from azathoth.sensitivity import Sensitivity
from azathoth.telemetry import Telemetry
from azathoth.telemetry.invocations import traced_job_invoker
from azathoth.telemetry.runs import tracing_runner


def keyed_request(
    *,
    workflow_id: UUID,
    payload: JsonValue | WorkflowInputFile,
    idempotency_key: str,
    sensitivity: Sensitivity | None = None,
) -> InvokeJobRequest:
    """Return the job request a keyed `workflow invoke` stands for.

    A label given to the input is part of the request, as a job envelope's
    input source names it (ADR 0123).

    Raises:
        InputSourceError: An input file's media type cannot be decided.
    """

    unlabelled = (
        input_file_source(payload)
        if isinstance(payload, WorkflowInputFile)
        else InlineInput(value=payload)
    )

    source = unlabelled.model_copy(update={"sensitivity": sensitivity})

    return InvokeJobRequest(
        kind="invoke",
        version=1,
        idempotency_key=idempotency_key,
        workflow_id=workflow_id,
        input=source,
    )


def unfinished_record(
    job: JobResult,
) -> OutputRecord:
    """Return the terminal error record of a keyed invocation that did not run to a result."""

    assert job.error is not None

    record: OutputRecord = {
        "type": ERROR_RECORD_TYPE,
        "code": job.error.code.value,
        "message": job.error.message,
    }

    if job.invocation_id is not None:
        record = {"type": ERROR_RECORD_TYPE, "invocation_id": str(job.invocation_id), **record}

    return record


def invoke_with_key(
    *,
    workflow_id: UUID,
    payload: JsonValue | WorkflowInputFile,
    idempotency_key: str,
    output: WorkflowOutputFormat,
    telemetry: Telemetry,
    lineage: WorkflowLineage | None,
    configuration: CliRuntimeConfiguration,
    sensitivity: Sensitivity | None = None,
) -> int:
    """Invoke one production workflow under a key, and report it as `workflow invoke` does.

    A replayed or resumed invocation reports its result like one that just
    ran. One still running, a key used for another request, and an input
    that cannot be resolved are each reported as an error record, or on
    stderr in text, and exit with status 1.
    """

    try:
        request = keyed_request(
            workflow_id=workflow_id,
            payload=payload,
            idempotency_key=idempotency_key,
            sensitivity=sensitivity,
        )
    except InputSourceError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    stores = repositories(configuration)
    writer = JsonLinesOutputWriter(sys.stdout) if output is WorkflowOutputFormat.JSONL else None
    runner = tracing_runner(
        telemetry,
        observer=step_observer(output, writer),
        journal=stores.run_journal,
        leases=stores.run_leases,
        children=stores.run_children,
        content=stores.tool_content,
    )

    job = asyncio.run(
        run_invoke_job(
            request,
            policy=CLI_INPUT_POLICY,
            store=stores.content,
            invocation_repository=stores.invocations,
            invoke=traced_job_invoker(
                telemetry,
                runtime_job_invoker(
                    lambda: load_runtime(configuration),
                    invocation_repository=stores.invocations,
                    run_repository=stores.runs,
                    invocation_run_repository=stores.invocation_runs,
                    runner=runner,
                    lineage=lineage,
                ),
            ),
            resume=runtime_job_resumer(
                lambda: load_runtime(configuration),
                invocation_repository=stores.invocations,
                run_repository=stores.runs,
                invocation_run_repository=stores.invocation_runs,
                revision_repository=stores.production_revisions,
                journal=stores.run_journal,
                runner=runner,
            ),
        )
    )

    if job.status in (JobStatus.SUCCEEDED, JobStatus.FAILED) and job.invocation_id is not None:
        result = stores.invocations.result(job.invocation_id)

        assert result is not None

        return report_invocation_result(
            result,
            output=output,
            writer=writer,
            sensitivity=invocation_sensitivity(stores.invocations, job.invocation_id),
        )

    record = unfinished_record(job)

    if output is WorkflowOutputFormat.TEXT:
        print(record["message"], file=sys.stderr)

        return 1

    return write_terminal_record(record, writer)


__all__ = [
    "invoke_with_key",
    "keyed_request",
    "unfinished_record",
]
