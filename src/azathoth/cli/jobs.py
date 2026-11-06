"""Running job requests from the command line (ADR 0097)."""

import asyncio
import sys
from pathlib import Path
from typing import BinaryIO

from azathoth.cli.bootstrap import load_runtime
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.inputs import CLI_INPUT_POLICY
from azathoth.cli.lineage import parent_lineage
from azathoth.cli.parsing.jobs import STANDARD_INPUT_REQUEST
from azathoth.cli.persistence import repositories
from azathoth.cli.rendering.jobs import render_job_result
from azathoth.cli.tracing import run_traced
from azathoth.jobs import (
    JobError,
    JobErrorCode,
    JobRequestError,
    JobResult,
    JobStatus,
    parse_job_request,
    rejected_job_result,
    run_invoke_job,
    runtime_job_invoker,
    runtime_job_resumer,
)
from azathoth.telemetry import Telemetry
from azathoth.telemetry.invocations import traced_job, traced_job_invoker
from azathoth.telemetry.runs import tracing_runner


def run_job_request(
    source: str,
    *,
    stdin: BinaryIO | None = None,
) -> int:
    """Run one job request and print its result envelope as JSON.

    The request is read from a file, or from standard input when the source
    is `-`. Exactly one result envelope is printed on stdout, and nothing
    else; a request that cannot be read or decoded is printed as a rejected
    envelope. References are resolved under the CLI's policy, `file://` only.

    The database is opened only for a request that decodes, and the runtime
    is composed only when a workflow is actually invoked, so a replay, a
    conflict or a rejection needs no provider credentials.

    The command returns 0 when the job succeeded, and 1 otherwise.

    With tracing on, the job, the invocation it starts, its run and their
    steps are traced (ADR 0100). Tracing that cannot be configured prints
    its reason on stderr, prints no envelope and returns 1, before the
    request is even read.

    A job started by a step of another run records the lineage it was given
    in `AZATHOTH_LINEAGE` (ADR 0104). Lineage that is not valid, or a job
    nested too deeply, raises once the request is decoded, before anything is
    replayed, resolved or recorded, and no envelope is printed.

    A request whose key names an incomplete invocation resumes it once no
    process holds its run (ADR 0105), and prints its result as if it had
    just run; one still running prints the `incomplete` envelope.
    """

    return run_traced(
        lambda telemetry: _run_traced_job(
            source,
            stdin=stdin if stdin is not None else sys.stdin.buffer,
            telemetry=telemetry,
        )
    )


def _run_traced_job(
    source: str,
    *,
    stdin: BinaryIO,
    telemetry: Telemetry,
) -> int:
    """Run one job request inside its job span, and print its result envelope."""

    with traced_job(telemetry) as trace:
        result = _run(
            source,
            stdin=stdin,
            telemetry=telemetry,
        )

        trace.record(result)

    print(render_job_result(result))

    return 0 if result.status is JobStatus.SUCCEEDED else 1


def _run(
    source: str,
    *,
    stdin: BinaryIO,
    telemetry: Telemetry,
) -> JobResult:
    """Read, decode and run one job request."""

    try:
        content = _read_request(
            source,
            stdin=stdin,
        )
    except OSError as exc:
        return rejected_job_result(
            JobError(
                code=JobErrorCode.INVALID_REQUEST,
                message=f"Cannot read the job request {source}: {exc.strerror or exc}.",
            ),
            idempotency_key=None,
        )

    try:
        request = parse_job_request(content)
    except JobRequestError as exc:
        return rejected_job_result(
            exc.error,
            idempotency_key=exc.idempotency_key,
        )

    lineage = parent_lineage(request.workflow_id)

    configuration = CliRuntimeConfiguration.from_environment()

    stores = repositories(configuration)
    invocation_repository = stores.invocations
    runner = tracing_runner(
        telemetry,
        journal=stores.run_journal,
        leases=stores.run_leases,
        children=stores.run_children,
        content=stores.tool_content,
    )

    return asyncio.run(
        run_invoke_job(
            request,
            policy=CLI_INPUT_POLICY,
            store=stores.content,
            invocation_repository=invocation_repository,
            invoke=traced_job_invoker(
                telemetry,
                runtime_job_invoker(
                    lambda: load_runtime(configuration),
                    invocation_repository=invocation_repository,
                    run_repository=stores.runs,
                    invocation_run_repository=stores.invocation_runs,
                    runner=runner,
                    lineage=lineage,
                ),
            ),
            resume=runtime_job_resumer(
                lambda: load_runtime(configuration),
                invocation_repository=invocation_repository,
                run_repository=stores.runs,
                invocation_run_repository=stores.invocation_runs,
                revision_repository=stores.production_revisions,
                journal=stores.run_journal,
                runner=runner,
            ),
        )
    )


def _read_request(
    source: str,
    *,
    stdin: BinaryIO,
) -> bytes:
    """Return the raw bytes of one job request.

    Raises:
        OSError: The file cannot be read.
    """

    if source == STANDARD_INPUT_REQUEST:
        return stdin.read()

    return Path(source).read_bytes()


__all__ = [
    "run_job_request",
]
