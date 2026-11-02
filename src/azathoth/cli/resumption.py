"""Resuming interrupted runs and invocations from the command line (ADR 0105).

`run resume` resumes a configured run, one started by `workflow run`, from
the specification revision it started from. `invocation resume` resumes a
production invocation from the production state it started from. Either
keeps its run's ID, and reports the finished run exactly as the command
that started it would have.
"""

import asyncio
import sys
from collections.abc import Sequence
from uuid import UUID

from azathoth.cli.bootstrap import load_runtime
from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.output_format import DEFAULT_WORKFLOW_OUTPUT_FORMAT, WorkflowOutputFormat
from azathoth.cli.persistence import repositories
from azathoth.cli.step_output import JsonLinesOutputWriter
from azathoth.cli.tracing import run_traced
from azathoth.cli.workflows import (
    report_configured_run,
    report_invocation_result,
    step_observer,
)
from azathoth.runtime import RuntimeEnvironment
from azathoth.telemetry import Telemetry
from azathoth.telemetry.invocations import traced_invocation
from azathoth.telemetry.runs import tracing_runner
from azathoth.workflows import (
    JournalRunStarted,
    ProductionInvocationResumeError,
    RunJournalEntry,
    WorkflowGenerationError,
    WorkflowRepository,
    WorkflowRun,
    WorkflowRunner,
    WorkflowSpecification,
    generate_workflow_candidate,
    journal_resumes,
    resume_production_invocation,
    run_started,
)


class ConfiguredRunResumeError(RuntimeError):
    """A configured run cannot be resumed from the command line."""

    @classmethod
    def invoked(
        cls,
        run_id: UUID,
        invocation_id: UUID,
    ) -> "ConfiguredRunResumeError":
        """Return the error for a run that executes a production invocation."""

        return cls(
            f"Run {run_id} executes invocation {invocation_id}; resume it with "
            f"azathoth invocation resume {invocation_id}."
        )

    @classmethod
    def finished(
        cls,
        run_id: UUID,
    ) -> "ConfiguredRunResumeError":
        """Return the error for a run already recorded as finished."""

        return cls(f"Run {run_id} has already finished.")

    @classmethod
    def unrevisioned(
        cls,
        run_id: UUID,
        workflow_id: UUID,
        revision: int,
    ) -> "ConfiguredRunResumeError":
        """Return the error for a run whose specification revision is gone."""

        return cls(
            f"Workflow {workflow_id} has no revision {revision} to resume run {run_id} with."
        )


def _started_specification(
    run_id: UUID,
    started: JournalRunStarted,
    *,
    runtime: RuntimeEnvironment,
    specifications: WorkflowRepository,
) -> WorkflowSpecification:
    """Return the specification revision a configured run started from.

    A run from before revisions resumes with the configured specification;
    the resume itself refuses it if that now has a revision.

    Raises:
        ConfiguredRunResumeError: The revision is no longer recorded, or the
            workflow of a run from before revisions is not configured.
    """

    workflow_id = started.workflow.id

    if started.workflow_revision is None:
        configured = runtime.workflows.get(workflow_id)

        if configured is None:
            raise ConfiguredRunResumeError(f"Workflow {workflow_id} is not configured.")

        return configured

    revision = specifications.revision(workflow_id, started.workflow_revision)

    if revision is None:
        raise ConfiguredRunResumeError.unrevisioned(
            run_id,
            workflow_id,
            started.workflow_revision,
        )

    return revision.specification


async def resume_configured_workflow(
    *,
    runtime: RuntimeEnvironment,
    run_id: UUID,
    entries: Sequence[RunJournalEntry],
    specifications: WorkflowRepository,
    runner: WorkflowRunner,
) -> tuple[WorkflowRun, WorkflowSpecification]:
    """Resume one configured run from the revision it started from.

    Returns the finished run and the specification it executed.

    Raises:
        ConfiguredRunResumeError: The run executes a production invocation, or
            its revision is gone.
        RunResumeError: The run has no journal, or cannot be resumed.
        RunLeaseHeldError: Another process holds the run's live lease.
        WorkflowGenerationError: No candidate could be generated.
    """

    started = run_started(run_id, entries)
    invocation_id = entries[0].invocation_id

    if invocation_id is not None:
        raise ConfiguredRunResumeError.invoked(run_id, invocation_id)

    specification = _started_specification(
        run_id,
        started,
        runtime=runtime,
        specifications=specifications,
    )

    candidate = generate_workflow_candidate(
        specification,
        runtime.models,
        runtime.language_models,
        portfolio=runtime.portfolio,
        tool_resolver=runtime.tool_resolver,
        tool_implementation_resolver=runtime.tool_implementation_resolver,
        revision=started.workflow_revision,
    )

    run = await runner.resume(candidate, run_id=run_id)

    return run, specification


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
                    runner=tracing_runner(
                        telemetry,
                        observer=step_observer(output, writer),
                        journal=stores.run_journal,
                        leases=stores.run_leases,
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
    )


__all__ = [
    "ConfiguredRunResumeError",
    "resume_configured_workflow",
    "resume_invocation",
    "resume_run",
]
