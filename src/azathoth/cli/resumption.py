"""Resuming interrupted runs and invocations from the command line (ADR 0105).

`run resume` resumes a configured run, one started by `workflow run`, from
the specification revision it started from. `invocation resume` resumes a
production invocation from the production state it started from. Either
keeps its run's ID, and reports the finished run exactly as the command
that started it would have.
"""

import asyncio
import sys
from uuid import UUID

from azathoth.api.resuming import ConfiguredRunResumeError, resume_configured_workflow
from azathoth.cli.bootstrap import load_runtime
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.output_format import DEFAULT_WORKFLOW_OUTPUT_FORMAT, WorkflowOutputFormat
from azathoth.cli.persistence import repositories
from azathoth.cli.reporting import (
    report_configured_run,
    report_invocation_result,
    step_observer,
)
from azathoth.cli.step_output import JsonLinesOutputWriter
from azathoth.cli.tracing import run_traced
from azathoth.context import context_sensitivity
from azathoth.telemetry import Telemetry
from azathoth.telemetry.invocations import traced_invocation
from azathoth.telemetry.runs import tracing_runner
from azathoth.workflows import (
    ProductionInvocationResumeError,
    WorkflowGenerationError,
    journal_resumes,
    resume_production_invocation,
)


def resume_run(
    run_id: UUID,
    *,
    output: WorkflowOutputFormat = DEFAULT_WORKFLOW_OUTPUT_FORMAT,
) -> int:
    """Resume one interrupted configured run, persist it, and report it as `workflow run` does."""

    return run_traced(
        lambda telemetry: _resume_run(
            run_id,
            output=output,
            telemetry=telemetry,
        )
    )


def _resume_run(
    run_id: UUID,
    *,
    output: WorkflowOutputFormat,
    telemetry: Telemetry,
) -> int:
    """Resume one configured run, tracing it with the given telemetry."""

    configuration = CliRuntimeConfiguration.from_environment()
    stores = repositories(configuration)

    if stores.runs.get(run_id) is not None:
        print(str(ConfiguredRunResumeError.finished(run_id)), file=sys.stderr)

        return 1

    entries = stores.run_journal.entries(run_id)
    runtime = load_runtime(configuration)
    writer = JsonLinesOutputWriter(sys.stdout) if output is WorkflowOutputFormat.JSONL else None

    try:
        run, specification = asyncio.run(
            resume_configured_workflow(
                runtime=runtime,
                run_id=run_id,
                entries=entries,
                specifications=stores.workflows,
                runner=tracing_runner(
                    telemetry,
                    observer=step_observer(output, writer),
                    journal=stores.run_journal,
                    leases=stores.run_leases,
                    children=stores.run_children,
                    content=stores.tool_content,
                ),
            )
        )
    except (ConfiguredRunResumeError, WorkflowGenerationError) as exc:
        print(str(exc), file=sys.stderr)

        return 1

    if stores.runs.get(run.id) is None:
        stores.runs.save(run)

    return report_configured_run(
        run,
        specification=specification,
        output=output,
        writer=writer,
        resumes=journal_resumes(stores.run_journal.entries(run_id)),
    )


def resume_invocation(
    invocation_id: UUID,
    *,
    output: WorkflowOutputFormat = DEFAULT_WORKFLOW_OUTPUT_FORMAT,
) -> int:
    """Resume one incomplete production invocation and report it as `workflow invoke` does."""

    return run_traced(
        lambda telemetry: _resume_invocation(
            invocation_id,
            output=output,
            telemetry=telemetry,
        )
    )


def _resume_invocation(
    invocation_id: UUID,
    *,
    output: WorkflowOutputFormat,
    telemetry: Telemetry,
) -> int:
    """Resume one production invocation, tracing it with the given telemetry."""

    configuration = CliRuntimeConfiguration.from_environment()
    stores = repositories(configuration)

    invocation = stores.invocations.get(invocation_id)

    if invocation is None:
        print(f"Invocation {invocation_id} was not found.", file=sys.stderr)

        return 1

    if stores.invocations.result(invocation_id) is not None:
        print(str(ProductionInvocationResumeError.completed(invocation_id)), file=sys.stderr)

        return 1

    runtime = load_runtime(configuration)
    writer = JsonLinesOutputWriter(sys.stdout) if output is WorkflowOutputFormat.JSONL else None

    try:
        with traced_invocation(telemetry, workflow_id=invocation.workflow_id) as trace:
            result = asyncio.run(
                resume_production_invocation(
                    invocation=invocation,
                    revisions=stores.production_revisions.revisions_for_workflow(
                        invocation.workflow_id
                    ),
                    current_state=runtime.production_state(invocation.workflow_id),
                    catalog=runtime.models,
                    registry=runtime.language_models,
                    portfolio=runtime.portfolio,
                    runner=tracing_runner(
                        telemetry,
                        observer=step_observer(output, writer),
                        journal=stores.run_journal,
                        leases=stores.run_leases,
                        children=stores.run_children,
                        content=stores.tool_content,
                    ),
                    journal=stores.run_journal,
                    run_repository=stores.runs,
                    invocation_repository=stores.invocations,
                    invocation_run_repository=stores.invocation_runs,
                    tool_resolver=runtime.tool_resolver,
                    tool_implementation_resolver=runtime.tool_implementation_resolver,
                )
            )

            trace.record(result)
    except ProductionInvocationResumeError as exc:
        print(str(exc), file=sys.stderr)

        return 1

    return report_invocation_result(
        result,
        output=output,
        writer=writer,
        sensitivity=context_sensitivity(invocation.initial_context),
    )


__all__ = [
    "ConfiguredRunResumeError",
    "resume_configured_workflow",
    "resume_invocation",
    "resume_run",
]
