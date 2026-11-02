"""Tests that an interrupted production invocation stays incomplete and resumes (ADR 0105)."""

import asyncio
from uuid import UUID

import pytest

from azathoth.context import Context
from azathoth.execution import ExecutionResult, StrategyExecutor
from azathoth.strategies import Strategy
from azathoth.workflows import (
    InMemoryProductionInvocationRepository,
    InMemoryProductionInvocationRunRepository,
    InMemoryRunJournalRepository,
    InMemoryWorkflowRunRepository,
    ProductionInvocationResult,
    ProductionInvocationSuccess,
    RunJournalError,
    RunResumeError,
    WorkflowRunner,
    complete_production_invocation,
    journal_resumes,
)
from tests.workflows.test_production_execution import (
    INVOCATION_ID,
    create_catalog,
    create_invocation,
    create_registry,
    create_state,
)
from tests.workflows.test_run_resume import Crash, CrashingJournal
from tests.workflows.test_runner_journal import (
    FIRST_STEP_ID,
    INITIAL_CONTEXT,
    FailingJournal,
    FlakyStrategy,
    candidate,
    step,
)


class CountingExecutor(StrategyExecutor):
    """Count executions, delegating each to the real executor."""

    def __init__(
        self,
    ) -> None:
        super().__init__()
        self.calls = 0

    async def execute(
        self,
        strategy: Strategy,
        context: Context,
    ) -> ExecutionResult:
        self.calls += 1

        return await super().execute(strategy, context)


class Repositories:
    """The in-memory repositories one invocation is recorded in."""

    def __init__(
        self,
    ) -> None:
        self.invocations = InMemoryProductionInvocationRepository()
        self.runs = InMemoryWorkflowRunRepository()
        self.invocation_runs = InMemoryProductionInvocationRunRepository()


def complete(
    repositories: Repositories,
    runner: WorkflowRunner,
    *,
    resume_run_id: UUID | None = None,
) -> ProductionInvocationResult:
    """Complete the test invocation with the given runner."""

    return asyncio.run(
        complete_production_invocation(
            invocation=create_invocation(),
            state=create_state(),
            catalog=create_catalog(),
            registry=create_registry(),
            runner=runner,
            run_repository=repositories.runs,
            invocation_repository=repositories.invocations,
            invocation_run_repository=repositories.invocation_runs,
            resume_run_id=resume_run_id,
        )
    )


def test_an_interrupted_invocation_records_no_result_and_resumes_to_one() -> None:
    repositories = Repositories()
    repositories.invocations.save(create_invocation())
    journal = CrashingJournal()
    journal.crash("attempt.finished")

    with pytest.raises(Crash):
        complete(repositories, WorkflowRunner(journal=journal))

    assert repositories.invocations.result(INVOCATION_ID) is None
    assert repositories.invocation_runs.get(INVOCATION_ID) is None

    run_id = journal.invocation_run_id(INVOCATION_ID)

    assert run_id is not None

    executor = CountingExecutor()

    result = complete(
        repositories,
        WorkflowRunner(executor=executor, journal=journal),
        resume_run_id=run_id,
    )

    assert isinstance(result, ProductionInvocationSuccess)
    assert repositories.invocations.result(INVOCATION_ID) == result
    assert executor.calls == 1

    association = repositories.invocation_runs.get(INVOCATION_ID)

    assert association is not None
    assert association.run_id == run_id

    run = repositories.runs.get(run_id)

    assert run is not None
    assert run.succeeded
    assert journal_resumes(journal.entries(run_id)) == 1


def test_a_run_finished_but_not_recorded_is_recorded_on_resume_without_running() -> None:
    repositories = Repositories()
    repositories.invocations.save(create_invocation())
    journal = InMemoryRunJournalRepository()

    first = complete(repositories, WorkflowRunner(journal=journal))

    run_id = journal.invocation_run_id(INVOCATION_ID)

    assert run_id is not None

    #
    # As if the process died after the run's journal finished but before
    # anything else was recorded.
    #
    unrecorded = Repositories()
    unrecorded.invocations.save(create_invocation())
    executor = CountingExecutor()

    result = complete(
        unrecorded,
        WorkflowRunner(executor=executor, journal=journal),
        resume_run_id=run_id,
    )

    assert result == first
    assert executor.calls == 0
    assert unrecorded.runs.get(run_id) == repositories.runs.get(run_id)


def test_resuming_a_run_already_recorded_records_it_once() -> None:
    repositories = Repositories()
    repositories.invocations.save(create_invocation())
    journal = InMemoryRunJournalRepository()

    complete(repositories, WorkflowRunner(journal=journal))

    run_id = journal.invocation_run_id(INVOCATION_ID)

    assert run_id is not None

    recorded = repositories.runs.get(run_id)
    association = repositories.invocation_runs.get(INVOCATION_ID)

    assert recorded is not None and association is not None

    again = Repositories()
    again.invocations.save(create_invocation())
    again.runs.save(recorded)
    again.invocation_runs.save(association)

    result = complete(again, WorkflowRunner(journal=journal), resume_run_id=run_id)

    assert isinstance(result, ProductionInvocationSuccess)


def test_a_run_whose_journal_fails_leaves_the_invocation_incomplete() -> None:
    repositories = Repositories()
    repositories.invocations.save(create_invocation())

    with pytest.raises(RunJournalError, match="refused attempt.finished"):
        complete(repositories, WorkflowRunner(journal=FailingJournal("attempt.finished")))

    assert repositories.invocations.result(INVOCATION_ID) is None


def test_a_run_that_cannot_be_resumed_leaves_the_invocation_incomplete() -> None:
    repositories = Repositories()
    repositories.invocations.save(create_invocation())
    journal = CrashingJournal()
    journal.crash("attempt.finished")

    with pytest.raises(Crash):
        asyncio.run(
            WorkflowRunner(journal=journal).run_recording_failures(
                candidate(step(FIRST_STEP_ID, FlakyStrategy())),
                INITIAL_CONTEXT,
            )
        )

    (other_run_id,) = journal.run_ids

    with pytest.raises(RunResumeError) as error:
        complete(repositories, WorkflowRunner(journal=journal), resume_run_id=other_run_id)

    assert str(error.value) == (
        f"Run {other_run_id} executes no invocation, not invocation {INVOCATION_ID}."
    )
    assert repositories.invocations.result(INVOCATION_ID) is None
