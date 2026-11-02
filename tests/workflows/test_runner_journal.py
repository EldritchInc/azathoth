"""Tests that the runner journals each run while it executes (ADR 0105)."""

import asyncio
from uuid import UUID

import pytest

from azathoth.context import Context, ContextEvent, LineageError
from azathoth.strategies import StrategyMetadata, StrategyOutcome
from azathoth.workflows import (
    InMemoryRunJournalRepository,
    JournalAttemptFinished,
    JournalAttemptStarted,
    JournalLayerCommitted,
    JournalRunFinished,
    JournalRunStarted,
    RunJournalEntry,
    RunJournalError,
    RunJournalPositionTakenError,
    WorkflowCandidate,
    WorkflowCandidateStep,
    WorkflowFailurePolicy,
    WorkflowMetadata,
    WorkflowRetryPolicy,
    WorkflowRun,
    WorkflowRunner,
    WorkflowStepRun,
    WorkflowStepStatus,
)

WORKFLOW_ID = UUID("c1100000-0000-4000-8000-000000000001")
FIRST_STEP_ID = UUID("c1100000-0000-4000-8000-000000000011")
SECOND_STEP_ID = UUID("c1100000-0000-4000-8000-000000000012")
LATER_STEP_ID = UUID("c1100000-0000-4000-8000-000000000013")
STRATEGY_ID = UUID("c1100000-0000-4000-8000-000000000021")
INVOCATION_ID = UUID("c1100000-0000-4000-8000-000000000031")


class FlakyStrategy:
    """Fail the first few attempts, then succeed, optionally waiting at a barrier."""

    def __init__(
        self,
        *,
        failures: int = 0,
        always_fail: bool = False,
        barrier: asyncio.Barrier | None = None,
    ) -> None:
        self._failures = failures
        self._always_fail = always_fail
        self._barrier = barrier
        self.calls = 0

    @property
    def metadata(self) -> StrategyMetadata:
        """Return strategy metadata."""

        return StrategyMetadata(
            id=STRATEGY_ID,
            name="Flaky step",
            description="Fail, then succeed.",
            version="1.0.0",
        )

    async def run(self, context: Context) -> StrategyOutcome:
        """Fail while failures remain, then succeed."""

        self.calls += 1

        if self._barrier is not None:
            await self._barrier.wait()

        if self._always_fail:
            raise RuntimeError("always fails")

        if self._failures > 0:
            self._failures -= 1
            raise RuntimeError("temporary failure")

        return StrategyOutcome(output=f"done {self.calls}")


def candidate(
    *steps: WorkflowCandidateStep,
) -> WorkflowCandidate:
    """Return a workflow of the given steps, at revision 3."""

    return WorkflowCandidate(
        metadata=WorkflowMetadata(
            id=WORKFLOW_ID,
            name="Journaled workflow",
            description="Record what each run does.",
            version="1.0.0",
        ),
        steps=steps,
        revision=3,
    )


def step(
    step_id: UUID,
    strategy: FlakyStrategy,
    *,
    depends_on: tuple[UUID, ...] = (),
    attempts: int = 1,
    failure_policy: WorkflowFailurePolicy = WorkflowFailurePolicy.FAIL_WORKFLOW,
) -> WorkflowCandidateStep:
    """Return one step."""

    return WorkflowCandidateStep(
        id=step_id,
        strategy=strategy,
        depends_on=depends_on,
        retry_policy=WorkflowRetryPolicy(max_attempts=attempts),
        failure_policy=failure_policy,
    )


INITIAL_CONTEXT = Context(
    events=(
        ContextEvent(
            event_type="workflow.input.received",
            payload={"input": {"text": "hello"}},
            producer="test",
        ),
    )
)


def run_journaled(
    workflow: WorkflowCandidate,
    *,
    invocation_id: UUID | None = None,
) -> tuple[WorkflowRun, tuple[RunJournalEntry, ...]]:
    """Run a workflow with a journal, and return the run and its journal."""

    journal = InMemoryRunJournalRepository()

    run = asyncio.run(
        WorkflowRunner(journal=journal).run_recording_failures(
            workflow,
            INITIAL_CONTEXT,
            invocation_id=invocation_id,
        )
    )

    return run, journal.entries(run.id)


def rebuilt(
    entries: tuple[RunJournalEntry, ...],
) -> WorkflowRun:
    """Rebuild a finished run from nothing but its journal."""

    started = entries[0].event
    finished = entries[-1].event

    assert isinstance(started, JournalRunStarted)
    assert isinstance(finished, JournalRunFinished)

    layers = [entry.event for entry in entries if isinstance(entry.event, JournalLayerCommitted)]

    return WorkflowRun(
        id=entries[0].run_id,
        workflow=started.workflow,
        workflow_revision=started.workflow_revision,
        steps=tuple(step for layer in layers for step in layer.steps),
        initial_context=started.initial_context,
        final_context=Context(
            events=(
                *started.initial_context.events,
                *(event for layer in layers for event in layer.events),
            )
        ),
        started_at=started.started_at,
        completed_at=finished.completed_at,
        halted=finished.halted,
        halting_step_id=finished.halting_step_id,
    )


def two_layers() -> WorkflowCandidate:
    """Return a workflow whose first step fails once, then a step after it."""

    return candidate(
        step(FIRST_STEP_ID, FlakyStrategy(failures=1), attempts=2),
        step(LATER_STEP_ID, FlakyStrategy(), depends_on=(FIRST_STEP_ID,)),
    )


# What a run journals


def test_a_runner_without_a_journal_records_none() -> None:
    run = asyncio.run(WorkflowRunner().run(two_layers(), INITIAL_CONTEXT))

    assert run.succeeded


def test_a_run_journals_its_start_attempts_layers_and_finish_in_order() -> None:
    run, entries = run_journaled(two_layers())

    assert [(entry.position, entry.event.type) for entry in entries] == [
        (1, "run.started"),
        (2, "attempt.started"),
        (3, "attempt.finished"),
        (4, "attempt.started"),
        (5, "attempt.finished"),
        (6, "layer.committed"),
        (7, "attempt.started"),
        (8, "attempt.finished"),
        (9, "layer.committed"),
        (10, "run.finished"),
    ]
    assert {entry.run_id for entry in entries} == {run.id}
    assert {entry.workflow_id for entry in entries} == {WORKFLOW_ID}
    assert {entry.invocation_id for entry in entries} == {None}


def test_every_entry_names_the_invocation_the_run_executes() -> None:
    _, entries = run_journaled(two_layers(), invocation_id=INVOCATION_ID)

    assert {entry.invocation_id for entry in entries} == {INVOCATION_ID}


def test_the_start_records_the_workflow_its_revision_and_initial_context() -> None:
    run, entries = run_journaled(two_layers())

    assert entries[0].event == JournalRunStarted(
        workflow=run.workflow,
        workflow_revision=3,
        initial_context=INITIAL_CONTEXT,
        started_at=run.started_at,
    )


def test_each_attempt_records_its_start_and_its_whole_attempt() -> None:
    run, entries = run_journaled(two_layers())

    first = run.steps[0]

    assert [entry.event for entry in entries[1:5]] == [
        JournalAttemptStarted(
            step_id=FIRST_STEP_ID,
            layer_index=0,
            attempt_number=1,
            started_at=first.attempts[0].started_at,
        ),
        JournalAttemptFinished(step_id=FIRST_STEP_ID, layer_index=0, attempt=first.attempts[0]),
        JournalAttemptStarted(
            step_id=FIRST_STEP_ID,
            layer_index=0,
            attempt_number=2,
            started_at=first.attempts[1].started_at,
        ),
        JournalAttemptFinished(step_id=FIRST_STEP_ID, layer_index=0, attempt=first.attempts[1]),
    ]
    assert first.attempts[0].failure is not None
    assert first.attempts[1].execution is not None


def test_each_layer_records_its_steps_and_the_events_it_added() -> None:
    run, entries = run_journaled(two_layers())

    layers = [entry.event for entry in entries if isinstance(entry.event, JournalLayerCommitted)]

    assert [layer.layer_index for layer in layers] == [0, 1]
    assert [layer.steps for layer in layers] == [(run.steps[0],), (run.steps[1],)]
    assert all(layer.events for layer in layers)
    assert (
        *INITIAL_CONTEXT.events,
        *layers[0].events,
        *layers[1].events,
    ) == run.final_context.events


def test_the_finish_records_when_and_that_the_run_did_not_halt() -> None:
    run, entries = run_journaled(two_layers())

    assert entries[-1].event == JournalRunFinished(
        completed_at=run.completed_at,
        halted=False,
        halting_step_id=None,
    )


def test_a_finished_runs_journal_holds_the_whole_run() -> None:
    run, entries = run_journaled(two_layers())

    assert rebuilt(entries) == run


def test_a_halted_run_journals_its_halting_step_and_no_later_layer() -> None:
    run, entries = run_journaled(
        candidate(
            step(FIRST_STEP_ID, FlakyStrategy(always_fail=True)),
            step(LATER_STEP_ID, FlakyStrategy(), depends_on=(FIRST_STEP_ID,)),
        )
    )

    assert run.halted
    assert [entry.event.type for entry in entries] == [
        "run.started",
        "attempt.started",
        "attempt.finished",
        "layer.committed",
        "run.finished",
    ]
    assert entries[-1].event == JournalRunFinished(
        completed_at=run.completed_at,
        halted=True,
        halting_step_id=FIRST_STEP_ID,
    )
    assert rebuilt(entries) == run


def test_a_layer_records_every_step_its_failures_have_blocked() -> None:
    run, entries = run_journaled(
        candidate(
            step(
                FIRST_STEP_ID,
                FlakyStrategy(always_fail=True),
                failure_policy=WorkflowFailurePolicy.SKIP_DEPENDENTS,
            ),
            step(LATER_STEP_ID, FlakyStrategy(), depends_on=(FIRST_STEP_ID,)),
        )
    )

    layers = [entry.event for entry in entries if isinstance(entry.event, JournalLayerCommitted)]

    assert [layer.blocked_step_ids for layer in layers] == [
        (FIRST_STEP_ID,),
        (FIRST_STEP_ID, LATER_STEP_ID),
    ]
    assert layers[1].steps == (
        WorkflowStepRun(
            step_id=LATER_STEP_ID,
            layer_index=1,
            status=WorkflowStepStatus.SKIPPED,
        ),
    )
    assert layers[1].events == ()
    assert rebuilt(entries) == run


def test_concurrent_steps_journal_as_they_happen_and_commit_in_declared_order() -> None:
    barrier = asyncio.Barrier(2)

    run, entries = run_journaled(
        candidate(
            step(FIRST_STEP_ID, FlakyStrategy(barrier=barrier)),
            step(SECOND_STEP_ID, FlakyStrategy(barrier=barrier)),
        )
    )

    types = [entry.event.type for entry in entries]

    #
    # Both steps wait for each other, so both start before either finishes.
    #
    assert types == [
        "run.started",
        "attempt.started",
        "attempt.started",
        "attempt.finished",
        "attempt.finished",
        "layer.committed",
        "run.finished",
    ]

    layer = entries[5].event

    assert isinstance(layer, JournalLayerCommitted)
    assert [step_run.step_id for step_run in layer.steps] == [FIRST_STEP_ID, SECOND_STEP_ID]
    assert rebuilt(entries) == run


# When the journal cannot be recorded


class FailingJournal(InMemoryRunJournalRepository):
    """Record entries until one of a given type, which it refuses."""

    def __init__(
        self,
        refused: str,
    ) -> None:
        super().__init__()
        self._refused = refused

    def append(
        self,
        entry: RunJournalEntry,
    ) -> None:
        """Refuse the first entry of the refused type."""

        if entry.event.type == self._refused:
            raise RunJournalError(f"refused {self._refused}")

        super().append(entry)


@pytest.mark.parametrize(
    "refused",
    ["run.started", "attempt.started", "attempt.finished", "layer.committed", "run.finished"],
)
def test_an_entry_that_cannot_be_recorded_stops_the_run_with_its_error(
    refused: str,
) -> None:
    later = FlakyStrategy()

    with pytest.raises(RunJournalError) as error:
        asyncio.run(
            WorkflowRunner(journal=FailingJournal(refused)).run_recording_failures(
                candidate(
                    step(FIRST_STEP_ID, FlakyStrategy()),
                    step(LATER_STEP_ID, later, depends_on=(FIRST_STEP_ID,)),
                ),
                INITIAL_CONTEXT,
            )
        )

    assert str(error.value) == f"refused {refused}"

    if refused != "run.finished":
        assert later.calls == 0


def test_an_attempt_whose_finish_cannot_be_recorded_is_not_retried() -> None:
    strategy = FlakyStrategy()

    with pytest.raises(RunJournalError):
        asyncio.run(
            WorkflowRunner(journal=FailingJournal("attempt.finished")).run_recording_failures(
                candidate(step(FIRST_STEP_ID, strategy, attempts=3)),
                INITIAL_CONTEXT,
            )
        )

    assert strategy.calls == 1


def test_a_journal_failure_in_one_concurrent_step_cancels_its_sibling() -> None:
    class SlowStrategy(FlakyStrategy):
        async def run(self, context: Context) -> StrategyOutcome:
            self.calls += 1
            await asyncio.sleep(10)
            return StrategyOutcome(output="never")

    class RefuseFirstFinish(InMemoryRunJournalRepository):
        def append(self, entry: RunJournalEntry) -> None:
            if entry.event.type == "attempt.finished":
                raise RunJournalError("refused attempt.finished")

            super().append(entry)

    slow = SlowStrategy()

    with pytest.raises(RunJournalError, match="refused attempt.finished"):
        asyncio.run(
            asyncio.wait_for(
                WorkflowRunner(journal=RefuseFirstFinish()).run_recording_failures(
                    candidate(step(FIRST_STEP_ID, FlakyStrategy()), step(SECOND_STEP_ID, slow)),
                    INITIAL_CONTEXT,
                ),
                timeout=5,
            )
        )

    assert slow.calls == 1


class CompetingJournal(InMemoryRunJournalRepository):
    """Act as if another process records the same run from its second entry."""

    def append(
        self,
        entry: RunJournalEntry,
    ) -> None:
        """Record the entry; after the first, record a rival at position 2."""

        super().append(entry)

        if entry.position == 1:
            super().append(entry.model_copy(update={"position": 2}))


def test_a_second_writer_of_the_same_run_collides_instead_of_writing_over_it() -> None:
    journal = CompetingJournal()

    with pytest.raises(RunJournalPositionTakenError) as error:
        asyncio.run(
            WorkflowRunner(journal=journal).run_recording_failures(
                candidate(step(FIRST_STEP_ID, FlakyStrategy())),
                INITIAL_CONTEXT,
            )
        )

    run_id = error.value.run_id

    assert str(error.value) == f"Run {run_id} already records journal position 2."
    assert [entry.event.type for entry in journal.entries(run_id)] == [
        "run.started",
        "run.started",
    ]


class CountingJournal(InMemoryRunJournalRepository):
    """Count every entry recorded."""

    def __init__(
        self,
    ) -> None:
        super().__init__()
        self.appended = 0

    def append(
        self,
        entry: RunJournalEntry,
    ) -> None:
        """Record and count the entry."""

        self.appended += 1
        super().append(entry)


def test_a_run_refused_for_its_lineage_journals_nothing() -> None:
    journal = CountingJournal()
    context = Context(
        events=(
            ContextEvent.model_validate(
                {
                    "event_type": "workflow.lineage.received",
                    "payload": {"depth": 1},
                    "producer": "azathoth.lineage",
                }
            ),
        )
    )

    with pytest.raises(LineageError):
        asyncio.run(
            WorkflowRunner(journal=journal).run(
                candidate(step(FIRST_STEP_ID, FlakyStrategy())),
                context,
            )
        )

    assert journal.appended == 0
