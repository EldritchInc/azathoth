"""Resuming a production invocation that never completed (ADR 0105).

An invocation without a result was interrupted, or is still running. To
resume it, the production state it started from is found again: the
production revision current when the invocation was created, or, for a
workflow promoted before production revisions were recorded, the state
active now. Its run is the one its journal records; an invocation whose run
never journaled its start starts one now.
"""

from collections.abc import Sequence
from uuid import UUID

from azathoth.providers import LanguageModelRegistry, ModelCatalog, ModelPortfolio
from azathoth.tools import ToolImplementationResolver, ToolResolver
from azathoth.workflows.production import WorkflowProductionRevision, WorkflowProductionState
from azathoth.workflows.production_execution import complete_production_invocation
from azathoth.workflows.production_invocation import (
    ProductionInvocation,
    ProductionInvocationResult,
)
from azathoth.workflows.production_invocation_repository import ProductionInvocationRepository
from azathoth.workflows.production_invocation_run_repository import (
    ProductionInvocationRunRepository,
)
from azathoth.workflows.run_journal import RunJournalRepository
from azathoth.workflows.run_repository import WorkflowRunRepository
from azathoth.workflows.runner import WorkflowRunner


class ProductionInvocationResumeError(RuntimeError):
    """A production invocation cannot be resumed."""

    def __init__(
        self,
        invocation_id: UUID,
        message: str,
    ) -> None:
        super().__init__(message)
        self.invocation_id = invocation_id

    @classmethod
    def completed(
        cls,
        invocation_id: UUID,
    ) -> "ProductionInvocationResumeError":
        """Return the error for an invocation that already has its result."""

        return cls(invocation_id, f"Invocation {invocation_id} has already completed.")

    @classmethod
    def stateless(
        cls,
        invocation: ProductionInvocation,
    ) -> "ProductionInvocationResumeError":
        """Return the error for an invocation whose production state cannot be found."""

        return cls(
            invocation.id,
            f"Invocation {invocation.id} cannot be resumed: workflow "
            f"{invocation.workflow_id} has no production state it could have started from.",
        )


def starting_production_state(
    invocation: ProductionInvocation,
    *,
    revisions: Sequence[WorkflowProductionRevision],
    current: WorkflowProductionState | None,
) -> WorkflowProductionState | None:
    """Return the production state an invocation started from, if it can be found.

    It is the state of the last production revision of the invocation's
    workflow created no later than the invocation. Without one, it is the
    state active now, which a resume then checks against the revision the
    run's journal records.
    """

    started = [
        revision
        for revision in revisions
        if revision.workflow_id == invocation.workflow_id
        and revision.created_at <= invocation.created_at
    ]

    if started:
        return max(started, key=lambda revision: revision.created_at).state

    if current is not None and current.specification.metadata.id == invocation.workflow_id:
        return current

    return None


async def resume_production_invocation(
    *,
    invocation: ProductionInvocation,
    revisions: Sequence[WorkflowProductionRevision],
    current_state: WorkflowProductionState | None,
    catalog: ModelCatalog,
    registry: LanguageModelRegistry,
    runner: WorkflowRunner,
    journal: RunJournalRepository,
    run_repository: WorkflowRunRepository,
    invocation_repository: ProductionInvocationRepository,
    invocation_run_repository: ProductionInvocationRunRepository,
    tool_resolver: ToolResolver | None = None,
    tool_implementation_resolver: ToolImplementationResolver | None = None,
    portfolio: ModelPortfolio | None = None,
) -> ProductionInvocationResult:
    """Resume one incomplete invocation from the state it started from, and record its result.

    Its run is resumed from its journal under the same run ID; an invocation
    whose run never journaled its start runs from the beginning. `portfolio`,
    as it is now, supplies its models' declared data policies (ADR 0123).

    Raises:
        ProductionInvocationResumeError: The invocation already completed, or
            the state it started from cannot be found.
        RunResumeError: The run cannot be resumed with that state.
        RunLeaseHeldError: Another process holds the run's live lease.
        RunJournalError: The run stopped again before it finished.
    """

    if invocation_repository.result(invocation.id) is not None:
        raise ProductionInvocationResumeError.completed(invocation.id)

    state = starting_production_state(invocation, revisions=revisions, current=current_state)

    if state is None:
        raise ProductionInvocationResumeError.stateless(invocation)

    return await complete_production_invocation(
        invocation=invocation,
        state=state,
        catalog=catalog,
        registry=registry,
        runner=runner,
        run_repository=run_repository,
        invocation_repository=invocation_repository,
        invocation_run_repository=invocation_run_repository,
        tool_resolver=tool_resolver,
        tool_implementation_resolver=tool_implementation_resolver,
        resume_run_id=journal.invocation_run_id(invocation.id),
        portfolio=portfolio,
    )


__all__ = [
    "ProductionInvocationResumeError",
    "resume_production_invocation",
    "starting_production_state",
]
