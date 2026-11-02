"""Tests that an interrupted production invocation stays incomplete and resumes (ADR 0105)."""

import asyncio
from datetime import UTC, datetime, timedelta
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
    ProductionInvocation,
    ProductionInvocationResult,
    ProductionInvocationResumeError,
    ProductionInvocationSuccess,
    RunJournalError,
    RunResumeError,
    WorkflowProductionRevision,
    WorkflowRunner,
    complete_production_invocation,
    journal_resumes,
    resume_production_invocation,
    starting_production_state,
)
from tests.workflows.test_production_execution import (
    INVOCATION_ID,
    WORKFLOW_ID,
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


# The state an invocation started from


def revision_at(
    moment: datetime,
    specification_revision: int,
) -> WorkflowProductionRevision:
    """Return a production revision of the test workflow, created at a moment."""

    return WorkflowProductionRevision(
        state=create_state().model_copy(update={"specification_revision": specification_revision}),
        created_at=moment,
    )


def invocation_at(
    moment: datetime,
) -> ProductionInvocation:
    """Return the test invocation, created at a moment."""

    return create_invocation().model_copy(update={"created_at": moment})


NOON = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def test_an_invocation_started_from_the_last_revision_created_before_it() -> None:
    revisions = [
        revision_at(NOON - timedelta(hours=2), 1),
        revision_at(NOON - timedelta(hours=1), 2),
        revision_at(NOON + timedelta(hours=1), 3),
    ]

    state = starting_production_state(
        invocation_at(NOON),
        revisions=revisions,
        current=revisions[2].state,
    )

    assert state == revisions[1].state


def test_a_revision_created_at_the_same_moment_counts_as_before() -> None:
    revisions = [revision_at(NOON, 4)]

    assert starting_production_state(invocation_at(NOON), revisions=revisions, current=None) == (
        revisions[0].state
    )


def test_without_an_earlier_revision_the_state_active_now_is_tried() -> None:
    current = create_state()

    assert (
        starting_production_state(
            invocation_at(NOON),
            revisions=[revision_at(NOON + timedelta(hours=1), 3)],
            current=current,
        )
        == current
    )


def test_without_any_state_none_is_found() -> None:
    assert starting_production_state(invocation_at(NOON), revisions=(), current=None) is None


def test_an_invocation_with_a_result_cannot_be_resumed() -> None:
    repositories = Repositories()
    repositories.invocations.save(create_invocation())
    complete(repositories, WorkflowRunner(journal=InMemoryRunJournalRepository()))

    with pytest.raises(ProductionInvocationResumeError) as error:
        resume(repositories)

    assert str(error.value) == f"Invocation {INVOCATION_ID} has already completed."


def test_an_invocation_whose_state_is_gone_cannot_be_resumed() -> None:
    repositories = Repositories()
    repositories.invocations.save(create_invocation())

    with pytest.raises(ProductionInvocationResumeError) as error:
        resume(repositories, stateless=True)

    assert str(error.value) == (
        f"Invocation {INVOCATION_ID} cannot be resumed: workflow {WORKFLOW_ID} has no "
        "production state it could have started from."
    )


def test_an_invocation_whose_run_never_started_runs_from_the_beginning() -> None:
    repositories = Repositories()
    repositories.invocations.save(create_invocation())
    journal = InMemoryRunJournalRepository()

    result = resume(repositories, journal=journal)

    assert isinstance(result, ProductionInvocationSuccess)

    run_id = journal.invocation_run_id(INVOCATION_ID)

    assert run_id is not None
    assert journal_resumes(journal.entries(run_id)) == 0


def test_an_interrupted_invocation_resumes_from_the_state_it_started_from() -> None:
    repositories = Repositories()
    repositories.invocations.save(create_invocation())
    journal = CrashingJournal()
    journal.crash("attempt.finished")

    with pytest.raises(Crash):
        complete(repositories, WorkflowRunner(journal=journal))

    result = resume(repositories, journal=journal)

    run_id = journal.invocation_run_id(INVOCATION_ID)

    assert isinstance(result, ProductionInvocationSuccess)
    assert run_id is not None
    assert journal_resumes(journal.entries(run_id)) == 1


def resume(
    repositories: Repositories,
    *,
    journal: InMemoryRunJournalRepository | None = None,
    stateless: bool = False,
) -> ProductionInvocationResult:
    """Resume the test invocation, from the test state unless told otherwise."""

    store = journal if journal is not None else InMemoryRunJournalRepository()

    return asyncio.run(
        resume_production_invocation(
            invocation=create_invocation(),
            revisions=(),
            current_state=None if stateless else create_state(),
            catalog=create_catalog(),
            registry=create_registry(),
            runner=WorkflowRunner(journal=store),
            journal=store,
            run_repository=repositories.runs,
            invocation_repository=repositories.invocations,
            invocation_run_repository=repositories.invocation_runs,
        )
    )
