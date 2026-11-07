"""Tests that a step costs what the child runs it started cost (ADR 0117)."""

import asyncio
from uuid import UUID

import pytest

from azathoth.context import (
    Context,
    active_step_lineage,
    child_lineage,
    create_lineage_event,
)
from azathoth.strategies import (
    Strategy,
    StrategyExecutionMetrics,
    StrategyMetadata,
    StrategyOutcome,
)
from azathoth.workflows import (
    InMemoryRunChildRepository,
    InMemoryRunJournalRepository,
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowFailurePolicy,
    WorkflowMetadata,
    WorkflowRetryPolicy,
    WorkflowRun,
    WorkflowRunner,
    journaled_run_cost,
)

PARENT_ID = UUID("c16c0000-0000-4000-8000-000000000001")

CHILD_ID = UUID("c16c0000-0000-4000-8000-000000000002")

PARENT_STEP = UUID("c16c0000-0000-4000-8000-000000000003")

CHILD_STEP = UUID("c16c0000-0000-4000-8000-000000000004")


def metadata(
    identifier: UUID,
) -> StrategyMetadata:
    """Return a strategy's metadata."""

    return StrategyMetadata(id=identifier, name="cost", description="Cost.", version="1.0.0")


class Costing:
    """A strategy that costs a fixed amount, or states no cost, or no metrics."""

    def __init__(
        self,
        cost: float | None,
        *,
        metrics: bool = True,
    ) -> None:
        self._cost = cost
        self._metrics = metrics

    @property
    def metadata(self) -> StrategyMetadata:
        """Return the strategy's metadata."""

        return metadata(CHILD_STEP)

    async def run(
        self,
        context: Context,
    ) -> StrategyOutcome:
        """Return its cost."""

        return StrategyOutcome(
            output=1,
            metrics=StrategyExecutionMetrics(estimated_cost_usd=self._cost)
            if self._metrics
            else None,
        )


def workflow(
    identifier: UUID,
    step: UUID,
    strategy: Strategy,
    *,
    attempts: int = 1,
) -> WorkflowCandidate:
    """Return a one-step workflow."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=identifier, name="w", description="A workflow.", version="1.0.0"
        ),
        steps=(
            WorkflowCandidateStep(
                id=step,
                strategy=strategy,
                retry_policy=WorkflowRetryPolicy(max_attempts=attempts),
            ),
        ),
    )


class StartingChildren:
    """A strategy that starts child runs from its step, as `run_workflow` does."""

    def __init__(
        self,
        runner: WorkflowRunner,
        children: list[Costing],
        *,
        own: float | None = 0.0,
        fail_first: bool = False,
    ) -> None:
        self._runner = runner
        self._children = children
        self._own = own
        self._fail_first = fail_first
        self._attempts = 0

    @property
    def metadata(self) -> StrategyMetadata:
        """Return the strategy's metadata."""

        return metadata(PARENT_STEP)

    async def run(
        self,
        context: Context,
    ) -> StrategyOutcome:
        """Run each child under this step attempt's lineage; fail the first attempt if asked."""

        self._attempts += 1
        step = active_step_lineage()

        assert step is not None

        for child in self._children:
            await self._runner.run_recording_failures(
                workflow(CHILD_ID, CHILD_STEP, child),
                Context(events=(create_lineage_event(child_lineage(step, workflow_id=CHILD_ID)),)),
            )

        if self._fail_first and self._attempts == 1:
            self._children = []

            raise RuntimeError("Try again.")

        return StrategyOutcome(
            output=1,
            metrics=StrategyExecutionMetrics(estimated_cost_usd=self._own),
        )


def parent_cost(
    *children: Costing,
    own: float | None = 0.0,
    index: bool = True,
    fail_first: bool = False,
) -> float | None:
    """Run a parent whose step starts some children; return its step's cost."""

    journal = InMemoryRunJournalRepository()
    index_of_children = InMemoryRunChildRepository() if index else None
    runner = WorkflowRunner(journal=journal, children=index_of_children)
    run = asyncio.run(
        runner.run_recording_failures(
            workflow(
                PARENT_ID,
                PARENT_STEP,
                StartingChildren(runner, list(children), own=own, fail_first=fail_first),
                attempts=2,
            ),
            Context(),
        )
    )
    execution = run.steps[0].execution

    assert execution is not None
    assert execution.metrics is not None

    return execution.metrics.estimated_cost_usd


def test_a_step_costs_its_own_work_and_every_child_it_started() -> None:
    assert parent_cost(Costing(0.25), Costing(0.5), own=0.125) == pytest.approx(0.875)


def test_a_step_that_started_no_child_costs_its_own_work() -> None:
    assert parent_cost(own=0.125) == 0.125


@pytest.mark.parametrize(
    "child",
    [
        pytest.param(Costing(None), id="no-cost"),
        pytest.param(Costing(None, metrics=False), id="no-metrics"),
    ],
)
def test_a_child_whose_cost_is_unknown_makes_its_steps_unknown(
    child: Costing,
) -> None:
    assert parent_cost(Costing(0.25), child) is None


def test_a_step_stating_no_cost_is_left_so() -> None:
    assert parent_cost(Costing(0.25), own=None) is None


def test_without_the_index_of_children_a_step_costs_what_it_said() -> None:
    assert parent_cost(Costing(0.25), own=0.125, index=False) == 0.125


def test_only_the_children_of_the_attempt_that_succeeded_count() -> None:
    assert parent_cost(Costing(0.25), own=0.125, fail_first=True) == 0.125


def test_a_runs_cost_is_what_its_committed_steps_cost() -> None:
    journal = InMemoryRunJournalRepository()

    def cost_of(
        strategy: Costing,
    ) -> float | None:
        run: WorkflowRun = asyncio.run(
            WorkflowRunner(journal=journal).run_recording_failures(
                workflow(CHILD_ID, CHILD_STEP, strategy), Context()
            )
        )

        return journaled_run_cost(journal, run.id)

    assert cost_of(Costing(0.25)) == 0.25
    assert cost_of(Costing(None)) is None
    assert cost_of(Costing(None, metrics=False)) is None


def test_a_run_never_journaled_costs_nothing() -> None:
    assert journaled_run_cost(InMemoryRunJournalRepository(), CHILD_ID) == 0.0


class Failing:
    """A strategy that always fails."""

    @property
    def metadata(self) -> StrategyMetadata:
        """Return the strategy's metadata."""

        return metadata(CHILD_STEP)

    async def run(
        self,
        context: Context,
    ) -> StrategyOutcome:
        """Fail."""

        raise RuntimeError("No.")


def test_a_child_step_that_failed_and_was_passed_over_costs_nothing() -> None:
    journal = InMemoryRunJournalRepository()
    run = asyncio.run(
        WorkflowRunner(journal=journal).run_recording_failures(
            WorkflowCandidate(
                metadata=WorkflowMetadata(
                    id=CHILD_ID, name="w", description="A workflow.", version="1.0.0"
                ),
                steps=(
                    WorkflowCandidateStep(
                        id=CHILD_STEP,
                        strategy=Failing(),
                        failure_policy=WorkflowFailurePolicy.CONTINUE,
                    ),
                    WorkflowCandidateStep(id=PARENT_STEP, strategy=Costing(0.25)),
                ),
            ),
            Context(),
        )
    )

    assert journaled_run_cost(journal, run.id) == 0.25


def test_only_the_step_that_started_a_child_costs_it() -> None:
    journal = InMemoryRunJournalRepository()
    runner = WorkflowRunner(journal=journal, children=InMemoryRunChildRepository())
    sibling = UUID("c16c0000-0000-4000-8000-000000000005")
    run = asyncio.run(
        runner.run_recording_failures(
            WorkflowCandidate(
                metadata=WorkflowMetadata(
                    id=PARENT_ID, name="w", description="A workflow.", version="1.0.0"
                ),
                steps=(
                    WorkflowCandidateStep(
                        id=PARENT_STEP,
                        strategy=StartingChildren(runner, [Costing(0.25)], own=0.0),
                    ),
                    WorkflowCandidateStep(
                        id=sibling,
                        strategy=Costing(0.125),
                        depends_on=(PARENT_STEP,),
                    ),
                ),
            ),
            Context(),
        )
    )
    costs = {
        step.step_id: step.execution.metrics.estimated_cost_usd
        for step in run.steps
        if step.execution is not None and step.execution.metrics is not None
    }

    assert costs == {PARENT_STEP: 0.25, sibling: 0.125}
