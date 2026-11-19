"""Resuming an interrupted configured run from its journal (ADRs 0105 and 0129).

A configured run, one started by `workflow run` or `runs.run`, resumes from
the specification revision it started from, under its own ID. The service
API and the command line resume through the same call, each reporting the
finished run its own way.
"""

from collections.abc import Sequence
from uuid import UUID

from azathoth.context import context_sensitivity
from azathoth.runtime import RuntimeEnvironment
from azathoth.workflows import (
    JournalRunStarted,
    RunJournalEntry,
    WorkflowRepository,
    WorkflowRun,
    WorkflowRunner,
    WorkflowSpecification,
    generate_workflow_candidate,
    run_started,
)


class ConfiguredRunResumeError(RuntimeError):
    """A configured run cannot be resumed, for a reason its message says.

    It finished, executes a production invocation, or its revision is gone.

    The service API raises `RunNotResumableError` with its message.
    """

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
        sensitivity=context_sensitivity(started.initial_context),
    )

    run = await runner.resume(candidate, run_id=run_id)

    return run, specification


__all__ = [
    "ConfiguredRunResumeError",
    "resume_configured_workflow",
]
